"""Agent: 模型无关的 Agent，支持主模型+备用模型自动切换."""

from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from dqg.agents.llm_backends import LLMBackend, LLMConfig, create_backend
from dqg.constants import AGENT_EVIDENCE_EXCERPT_LIMIT, AGENT_EVIDENCE_TOTAL_LIMIT
from dqg.json_utils import dump_json_compact, dump_json_str
from dqg.log import get_logger
from dqg.store import get_connection

log = get_logger(__name__)

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path


@dataclass
class AgentMessage:
    role: str  # system / user / assistant
    content: str


@dataclass
class AgentResult:
    agent_name: str
    role: str
    status: str  # success / failed / fallback
    content: str = ""
    model_used: str = ""
    duration_seconds: float = 0
    token_usage: dict[str, int] = field(default_factory=dict)
    error: str = ""
    output_files: list[str] = field(default_factory=list)
    cache_hit: bool = False
    cached: bool = False
    trajectory: list[dict[str, str]] = field(default_factory=list)
    prompt_hash: str = ""
    # P0 可观测性：低频采样写入 telemetry（见 telemetry_payload）
    telemetry_prompt_excerpt: str = ""
    telemetry_response_excerpt: str = ""


def extract_llm_call(result: AgentResult) -> dict[str, Any]:
    """Extract LLM call telemetry from an AgentResult."""
    out: dict[str, Any] = {
        "agent_name": result.agent_name,
        "agent_role": result.role,
        "model_id": result.model_used,
        "prompt_hash": result.prompt_hash,
        "input_tokens": result.token_usage.get("input_tokens", 0),
        "output_tokens": result.token_usage.get("output_tokens", 0),
        "cache_creation_input_tokens": result.token_usage.get("cache_creation_input_tokens", 0),
        "cache_read_input_tokens": result.token_usage.get("cache_read_input_tokens", 0),
        "cache_hit": result.cache_hit,
        "duration_seconds": round(result.duration_seconds, 2),
        "status": result.status,
    }
    pex = getattr(result, "telemetry_prompt_excerpt", "") or ""
    rex = getattr(result, "telemetry_response_excerpt", "") or ""
    if pex:
        out["prompt_excerpt"] = pex
    if rex:
        out["response_excerpt"] = rex
    return out


_PRUNED_TOOL_PLACEHOLDER = "[旧工具输出已清理以节省 context]"
_TOOL_RESULT_TAG_RE = re.compile(r"<tool_result\s+name=\".*?\">\n.*?\n</tool_result>", re.DOTALL)


class Agent:
    """模型无关的 Agent，支持主模型+备用模型自动切换."""

    def __init__(
        self,
        name: str,
        role: str,
        system_prompt: str,
        model: LLMConfig | None = None,
        tools: list[Callable] | None = None,
        output_dir: Path | None = None,
    ):
        self.name = name
        self.role = role
        self.system_prompt = system_prompt
        self.model = model or LLMConfig()
        self.tools = tools or []
        self.output_dir = output_dir
        self._backend: LLMBackend | None = None
        self._fallback_backend: LLMBackend | None = None

    def _init_backends(self) -> None:
        if not self._backend:
            self._backend = create_backend(self.model.primary, self.model.primary_api_key)
        if not self._fallback_backend and self.model.fallback and self.model.fallback_api_key:
            self._fallback_backend = create_backend(self.model.fallback, self.model.fallback_api_key)

    def _build_system_content(self) -> str:
        """组装最终 system prompt（含工具说明）。"""
        system_content = self.system_prompt
        if self.tools:
            tool_docs = ["\n\n# 可用工具 (Available Tools)"]
            tool_docs.append(
                "你可以使用以下 XML 格式调用工具。系统会自动执行并用 <tool_result> 返回结果。每次回复最多调用一个工具。"
            )
            tool_docs.append('调用格式示例：\n<tool_call name="tool_name">\n{"param1": "value"}\n</tool_call>')
            for tool in self.tools:
                doc = tool.__doc__ or "No description."
                tool_docs.append(f"## 工具: {tool.__name__}\n{doc}")
            system_content += "\n".join(tool_docs)
        return system_content

    def _read_excerpt(self, path: Path, limit: int) -> str:
        """只读取受限摘录，避免把整份文件直接塞入 prompt."""
        if not path.exists():
            return ""
        try:
            text = path.read_text(encoding="utf-8").strip()
        except OSError:
            return ""
        if not text:
            return ""
        if len(text) > limit:
            return text[:limit] + "\n...(截断)"
        return text

    def _build_file_bundle(self, files: list[Path] | None) -> str:
        """Build file excerpt bundle with dedup and budget limits."""
        if not files:
            return ""
        blocks: list[str] = []
        seen: set[str] = set()
        used = 0
        for f in files:
            key = str(f)
            if key in seen or not f.exists():
                continue
            seen.add(key)
            remaining = AGENT_EVIDENCE_TOTAL_LIMIT - used
            if remaining <= 0:
                break
            excerpt = self._read_excerpt(f, min(AGENT_EVIDENCE_EXCERPT_LIMIT, remaining))
            if not excerpt:
                continue
            blocks.append(f"## 文件: {f.name}\n\n{excerpt}")
            used += len(excerpt)
        return "\n\n---\n\n".join(blocks)

    def _build_context_payload(self, context_files: list[Path] | None) -> str:
        """将上下文文件整理为稳定 evidence bundle，供 cache key 和 prompt 使用。"""
        return self._build_file_bundle(context_files)

    def _cache_key_payload(
        self, backend_name: str, system_content: str, context_payload: str, user_message: str
    ) -> str:
        payload = {
            "backend": backend_name,
            "system_prompt": system_content,
            "context_payload": context_payload,
            "user_message": user_message,
            "temperature": self.model.temperature,
            "max_tokens": self.model.max_tokens,
        }
        return dump_json_compact(payload)

    def _cache_lookup(
        self,
        backend_name: str,
        system_content: str,
        context_payload: str,
        user_message: str,
    ) -> AgentResult | None:
        if not self.output_dir:
            return None

        payload_json = self._cache_key_payload(backend_name, system_content, context_payload, user_message)
        query_hash = hashlib.sha256(payload_json.encode("utf-8")).hexdigest()

        with get_connection(self.output_dir) as conn:
            row = conn.execute(
                "SELECT result_json FROM query_cache WHERE query_hash = ? AND result_type = ?",
                (query_hash, "agent_result"),
            ).fetchone()

        if not row:
            return None

        try:
            cached = json.loads(row["result_json"])
        except (json.JSONDecodeError, TypeError, KeyError):
            return None

        return AgentResult(
            agent_name=cached.get("agent_name", self.name),
            role=cached.get("role", self.role),
            status=cached.get("status", "success"),
            content=cached.get("content", ""),
            model_used=cached.get("model_used", backend_name),
            duration_seconds=0,
            token_usage=cached.get("token_usage", {}),
            error=cached.get("error", ""),
            output_files=cached.get("output_files", []),
            cache_hit=True,
            cached=True,
        )

    def _cache_store(
        self,
        backend_name: str,
        system_content: str,
        context_payload: str,
        user_message: str,
        result: AgentResult,
    ) -> None:
        if not self.output_dir:
            return

        payload_json = self._cache_key_payload(backend_name, system_content, context_payload, user_message)
        query_hash = hashlib.sha256(payload_json.encode("utf-8")).hexdigest()
        cached_payload = {
            "agent_name": result.agent_name,
            "role": result.role,
            "status": result.status,
            "content": result.content,
            "model_used": result.model_used,
            "token_usage": result.token_usage,
            "error": result.error,
            "output_files": result.output_files,
        }

        with get_connection(self.output_dir) as conn:
            conn.execute(
                """INSERT INTO query_cache (query_hash, query_text, result_type, result_json, created_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(query_hash) DO UPDATE SET
                    query_text=excluded.query_text,
                    result_type=excluded.result_type,
                    result_json=excluded.result_json,
                    created_at=excluded.created_at,
                    hit_count=0,
                    last_hit_at=NULL""",
                (query_hash, payload_json, "agent_result", dump_json_str(cached_payload, indent=None), time.time()),
            )

    def _build_dynamic_payload(self, dynamic_context_files: list[Path] | None) -> str:
        """将动态上下文文件整理为 evidence bundle（不缓存，每次迭代可变）。"""
        return self._build_file_bundle(dynamic_context_files)

    def _cache_key_components(
        self,
        backend_name: str,
        context_files: list[Path] | None,
        user_message: str,
        dynamic_context_files: list[Path] | None = None,
    ) -> tuple[str, str, str, str, str]:
        system_content = self._build_system_content()
        context_payload = self._build_context_payload(context_files)
        dynamic_payload = self._build_dynamic_payload(dynamic_context_files)
        # Cache key includes dynamic content so different dynamic inputs don't collide
        combined_context = context_payload + dynamic_payload
        payload_json = self._cache_key_payload(backend_name, system_content, combined_context, user_message)
        return system_content, context_payload, dynamic_payload, combined_context, payload_json

    def run(
        self,
        user_message: str,
        context_files: list[Path] | None = None,
        dynamic_context_files: list[Path] | None = None,
        *,
        telemetry_span: dict[str, Any] | None = None,
    ) -> AgentResult:
        """执行 Agent 任务，失败自动切换备用模型."""
        self._init_backends()
        start = time.time()
        system_content, context_payload, dynamic_payload, combined_context, payload_json = self._cache_key_components(
            self._backend.name(), context_files, user_message, dynamic_context_files
        )

        # Compute prompt fingerprint for observability
        prompt_hash = hashlib.sha256(payload_json.encode("utf-8")).hexdigest()[:16]

        cached_result = self._cache_lookup(self._backend.name(), system_content, combined_context, user_message)
        if cached_result is not None:
            cached_result.prompt_hash = prompt_hash
            return cached_result
        if self._fallback_backend:
            cached_result = self._cache_lookup(
                self._fallback_backend.name(), system_content, combined_context, user_message
            )
            if cached_result is not None:
                cached_result.prompt_hash = prompt_hash
                return cached_result

        messages = []
        if system_content and system_content.strip():
            messages.append({"role": "system", "content": system_content, "cache_control": True})
        if context_payload:
            messages.append({"role": "user", "content": context_payload, "cache_control": True})
        if dynamic_payload:
            messages.append({"role": "user", "content": dynamic_payload})
        messages.append({"role": "user", "content": user_message})

        total_input_tokens = 0
        total_output_tokens = 0
        total_cache_creation = 0
        total_cache_read = 0
        final_content = ""
        model_used = None
        saw_tool_call = False
        raw_trajectory: list[dict[str, str]] = [dict(m) for m in messages]  # 保存初始 messages 快照

        # Tool-Calling Loop
        max_turns = 10
        for turn in range(max_turns):
            # Prune old tool results to save context (keep only the latest)
            if turn > 0:
                for i, msg in enumerate(messages):
                    if (
                        msg["role"] == "user"
                        and _TOOL_RESULT_TAG_RE.search(msg["content"])
                        and i < len(messages) - 2  # 保留最近一轮的工具结果
                    ):
                        msg["content"] = _PRUNED_TOOL_PLACEHOLDER

            # 尝试主模型
            try:
                content, usage = self._backend.chat(
                    messages, max_tokens=self.model.max_tokens, temperature=self.model.temperature
                )
                model_used = self._backend.name()
            except Exception as e:
                primary_error = str(e)
                # 尝试备用模型
                if self._fallback_backend:
                    try:
                        content, usage = self._fallback_backend.chat(
                            messages, max_tokens=self.model.max_tokens, temperature=self.model.temperature
                        )
                        model_used = self._fallback_backend.name()
                    except Exception as e2:
                        return AgentResult(
                            agent_name=self.name,
                            role=self.role,
                            status="failed",
                            duration_seconds=time.time() - start,
                            error=f"Primary: {primary_error}; Fallback: {e2}",
                        )
                else:
                    return AgentResult(
                        agent_name=self.name,
                        role=self.role,
                        status="failed",
                        duration_seconds=time.time() - start,
                        error=f"Primary failed: {primary_error}; No fallback configured",
                    )

            # 更新 Tokens
            total_input_tokens += usage.get("input_tokens", 0)
            total_output_tokens += usage.get("output_tokens", 0)
            total_cache_creation += usage.get("cache_creation_input_tokens", 0)
            total_cache_read += usage.get("cache_read_input_tokens", 0)
            final_content += content + "\n\n"

            # 解析 tool_call（仅当 Agent 有注册工具时才处理）
            if not self.tools:
                # 无工具注册，直接结束（忽略模型输出的 tool_call 幻觉）
                break
            match = re.search(r"<tool_call\s+name=\"(.*?)\">(.*?)</tool_call>", content, re.DOTALL)
            if not match:
                # 没有工具调用，结束任务
                break

            saw_tool_call = True

            tool_name = match.group(1).strip()
            args_str = match.group(2).strip()

            tool_func = next((t for t in self.tools if t.__name__ == tool_name), None)
            if not tool_func:
                tool_result = f"Error: Tool '{tool_name}' not found."
            else:
                try:
                    args_dict = json.loads(args_str) if args_str else {}
                    tool_result = str(tool_func(**args_dict))
                except Exception as e:
                    tool_result = f"Error executing {tool_name}: {e}"

            messages.append({"role": "assistant", "content": content})
            messages.append(
                {"role": "user", "content": f'<tool_result name="{tool_name}">\n{tool_result}\n</tool_result>'}
            )
            # 记录原始 trajectory（pruning 前）
            raw_trajectory.append({"role": "assistant", "content": content})
            raw_trajectory.append(
                {"role": "user", "content": f'<tool_result name="{tool_name}">\n{tool_result}\n</tool_result>'}
            )

        # 最终 assistant 回复加入 trajectory
        if final_content.strip():
            raw_trajectory.append({"role": "assistant", "content": final_content.strip()})

        from dqg.reporting.telemetry_payload import (
            build_prompt_preview,
            maybe_sample_agent_payload,
            read_telemetry_span,
            telemetry_payload_max_chars,
        )

        fc = final_content.strip()
        prompt_ex, resp_ex = maybe_sample_agent_payload(messages, fc)

        # Review fix #1: prompt 版本库存储从采样率解耦 —— 全量去重存储，
        # 采样只影响 telemetry excerpt。UNIQUE(prompt_hash, content_hash)
        # 保证相同内容不会重复入库，体积可控。
        if self.output_dir:
            try:
                from dqg.store.prompt_versions import record_prompt_snapshot

                prompt_max, _ = telemetry_payload_max_chars()
                prompt_full = build_prompt_preview(messages, prompt_max)
                trace_run_id = read_telemetry_span(telemetry_span, "trace_run_id")
                record_prompt_snapshot(
                    self.output_dir,
                    prompt_hash=prompt_hash,
                    prompt_text=prompt_full,
                    agent_name=self.name,
                    agent_role=self.role,
                    trace_run_id=trace_run_id,
                )
            except Exception:
                log.debug("prompt_versions snapshot skipped", exc_info=True)

        result = AgentResult(
            agent_name=self.name,
            role=self.role,
            status="success" if not self._fallback_backend or model_used == self._backend.name() else "fallback",
            content=fc,
            model_used=model_used or self.model.primary,
            duration_seconds=time.time() - start,
            token_usage={
                "input_tokens": total_input_tokens,
                "output_tokens": total_output_tokens,
                "cache_creation_input_tokens": total_cache_creation,
                "cache_read_input_tokens": total_cache_read,
            },
            cache_hit=False,
            cached=False,
            trajectory=raw_trajectory,
            prompt_hash=prompt_hash,
            telemetry_prompt_excerpt=prompt_ex,
            telemetry_response_excerpt=resp_ex,
        )

        if not saw_tool_call:
            self._cache_store(result.model_used, system_content, combined_context, user_message, result)

        return result
