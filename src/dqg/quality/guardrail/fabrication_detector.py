"""编造检测 — 交叉验证报告中提到的接口/类/方法是否在代码库中存在.

检测逻辑：
1. 从报告和结构化 JSON 中提取 Java 标识符（类名、方法名、字段名）
2. 在 code_symbols 表中查询是否存在
3. 不存在且无法在代码仓库文件中 grep 到的，标记为疑似编造

前置条件：
- code_symbols 表已被 index_java_repo() 索引过（execute 阶段触发）
- 或者 _inputs.json 中有 code_repo 路径可供 grep fallback

注册为 PhaseGuardrail（WARNING 级别）。
"""

from __future__ import annotations

import re
from pathlib import Path

from dqg.log import get_logger

from .guardrail import (
    GuardrailContext,
    GuardrailLevel,
    GuardrailResult,
    PhaseGuardrail,
)

log = get_logger(__name__)

# Java 标识符模式：大驼峰类名、小驼峰方法名
_JAVA_CLASS_PATTERN = re.compile(
    r"\b([A-Z][a-zA-Z0-9]{2,}(?:Service|Controller|Repository|Gateway|Manager|Handler|Impl|DTO|VO|DO|Entity|Enum|Factory|Builder|Adapter|Proxy|Listener|Config|Util|Helper|Provider|Extension|Ability|Step))\b"
)
_JAVA_METHOD_PATTERN = re.compile(
    r"\b([a-z][a-zA-Z0-9]{2,}(?:Order|Payment|User|Account|Item|Record|Status|Type|Info|Data|Result|Response|Request|Param|Query|Command|Event))\b"
)
# 更通用的方法调用模式: xxx.methodName(
_METHOD_CALL_PATTERN = re.compile(r"(\w+)\.([a-z]\w{2,})\s*\(")
# 字段引用: getFieldName/setFieldName/isFieldName — 纯 camelCase，不含 _ 和中文
_FIELD_PATTERN = re.compile(r"\b(?:get|set|is)([A-Z][a-zA-Z0-9]+)\b(?![_一-鿿])")


def _extract_java_identifiers(text: str) -> dict[str, set[str]]:
    """从文本中提取 Java 标识符."""
    identifiers: dict[str, set[str]] = {
        "class": set(),
        "method": set(),
    }

    # 提取类名
    for m in _JAVA_CLASS_PATTERN.finditer(text):
        identifiers["class"].add(m.group(1))

    # 提取方法调用
    for m in _METHOD_CALL_PATTERN.finditer(text):
        identifiers["method"].add(m.group(2))

    # 提取 getter/setter 暗示的字段
    for m in _FIELD_PATTERN.finditer(text):
        identifiers["method"].add(f"get{m.group(1)}")

    return identifiers


def _check_symbols_in_db(output_dir: Path, identifiers: dict[str, set[str]]) -> set[str]:
    """在 code_symbols 表中查询哪些标识符存在."""
    found: set[str] = set()
    try:
        from dqg.store.core import get_connection

        with get_connection(output_dir) as conn:
            # 检查是否有索引数据
            count = conn.execute("SELECT COUNT(*) FROM code_symbols").fetchone()[0]
            if count == 0:
                return set()  # 无索引数据，跳过检测

            for name in identifiers.get("class", set()):
                row = conn.execute(
                    "SELECT 1 FROM code_symbols WHERE symbol_name = ? AND symbol_type = 'class' LIMIT 1",
                    (name,),
                ).fetchone()
                if row:
                    found.add(name)

            for name in identifiers.get("method", set()):
                row = conn.execute(
                    "SELECT 1 FROM code_symbols WHERE symbol_name = ? AND symbol_type = 'method' LIMIT 1",
                    (name,),
                ).fetchone()
                if row:
                    found.add(name)
    except Exception:
        log.debug("code_symbols 查询失败", exc_info=True)

    return found


def _grep_fallback(code_repo: Path, names: set[str]) -> set[str]:
    """在代码仓库中 grep 查找标识符（fallback）.

    用 subprocess grep -rl 全量扫描，比 rglob+read_text 快一个数量级，
    避免 rglob[:200] 在大型 monorepo 中错过目标类。
    """
    import shutil
    import subprocess

    found: set[str] = set()
    if not code_repo.exists() or not names:
        return found

    grep_bin = shutil.which("grep")
    if not grep_bin:
        # 没有 grep（极少见），退回 rglob 有限扫描
        for f in list(code_repo.rglob("*.java"))[:200]:
            try:
                content = f.read_text(encoding="utf-8", errors="ignore")
                for name in list(names):
                    if name in content:
                        found.add(name)
                        names.discard(name)
                if not names:
                    break
            except Exception:
                continue
        return found

    for name in list(names):
        try:
            res = subprocess.run(
                [grep_bin, "-r", "-l", "--include=*.java", "-F", name, str(code_repo)],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if res.returncode == 0 and res.stdout.strip():
                found.add(name)
                names.discard(name)
        except Exception:
            continue

    return found


# 常见框架类/方法白名单（不应被标记为编造）
_WHITELIST = frozenset(
    {
        # Spring
        "RestController",
        "RequestMapping",
        "GetMapping",
        "PostMapping",
        "Autowired",
        "Service",
        "Component",
        "Repository",
        "Configuration",
        "Transactional",
        "Cacheable",
        "Async",
        "Scheduled",
        # Java 标准库
        "BigDecimal",
        "ArrayList",
        "HashMap",
        "Optional",
        "CompletableFuture",
        "StringBuilder",
        "IOException",
        "RuntimeException",
        "IllegalArgumentException",
        # Lombok
        "Builder",
        "Data",
        "Getter",
        "Setter",
        "AllArgsConstructor",
        # 测试
        "MockBean",
        "InjectMocks",
        "BeforeEach",
        "AfterEach",
        # 通用后缀类（太常见，误报率高）
        "BaseService",
        "BaseController",
        "BaseEntity",
        "BaseDTO",
        "AbstractService",
        "AbstractHandler",
    }
)


class FabricationDetectorGuardrail(PhaseGuardrail):
    """检测报告中提到的接口/类/方法是否在代码库中存在."""

    name = "fabrication_detector"
    level = GuardrailLevel.WARNING

    def check(self, ctx: GuardrailContext) -> list[GuardrailResult]:
        # 只对涉及代码的 Phase 检测
        if ctx.phase_id not in ("Q03", "Q04", "Q05", "Q06", "Q07"):
            return []

        # 提取标识符
        text = ctx.report_content or ""
        if not text:
            return []

        identifiers = _extract_java_identifiers(text)
        all_names = identifiers.get("class", set()) | identifiers.get("method", set())

        # 过滤白名单
        all_names -= _WHITELIST
        if not all_names:
            return []

        # 在 code_symbols 表中查询
        found_in_db = _check_symbols_in_db(ctx.output_dir, identifiers)

        # 未找到的尝试 grep fallback（支持多 repo）
        not_found = all_names - found_in_db
        if not_found:
            code_repos = self._get_code_repos(ctx)
            for code_repo in code_repos:
                if not not_found:
                    break
                found_in_grep = _grep_fallback(code_repo, not_found.copy())
                not_found -= found_in_grep

        if not not_found:
            return []

        # 只有超过一定比例才告警（避免索引不全导致大量误报）
        total = len(all_names)
        not_found_ratio = len(not_found) / max(total, 1)

        # code_symbols 表为空（业务仓库未索引）：避免误报，静默跳过
        if not found_in_db and not_found_ratio > 0.8:
            return []

        # DB 有数据时阈值收紧到 20%（减少漏报）；无索引数据时保持 30% 兜底
        threshold = 0.2 if found_in_db else 0.3
        if not_found_ratio < threshold:
            return []

        samples = sorted(not_found)[:10]
        return [
            GuardrailResult(
                guardrail_name=self.name,
                passed=False,
                level=GuardrailLevel.WARNING,
                message=(
                    f"疑似编造: 报告中 {len(not_found)}/{total} 个 Java 标识符在代码库中未找到 "
                    f"({not_found_ratio:.0%}): {', '.join(samples)}"
                ),
                details=[f"not_found={samples}", f"ratio={not_found_ratio:.2f}"],
            )
        ]

    def _get_code_repos(self, ctx: GuardrailContext) -> list[Path]:
        """从本 Phase 的 _inputs.json 获取 code_repo 路径列表；
        若当前 Phase 没有，则回退扫所有已有 Phase 的 _inputs.json 取并集。

        场景：用户可能只在 Q01/Q05 传过 --code-repo，到 Q06 execute 忘了传，
        但 code_repos 对整个 project 都是同一组——应该能被复用而不是因缺失而跳过校验。
        """
        try:
            from dqg.core.state_machine import PHASE_DEFS, internal_dir
            from dqg.json_utils import load_json

            def _read(phase_id: str) -> list[str]:
                phase_def = PHASE_DEFS.get(phase_id)
                if not phase_def:
                    return []
                int_dir = internal_dir(ctx.output_dir, ctx.project_id, phase_def)
                inputs_path = int_dir / "_inputs.json"
                if not inputs_path.exists():
                    return []
                data = load_json(inputs_path)
                if not data:
                    return []
                code_repos = data.get("code_repos", [])
                if not code_repos and data.get("code_repo"):
                    code_repos = [data["code_repo"]]
                return code_repos

            collected: list[str] = _read(ctx.phase_id)
            if not collected:
                for pid in PHASE_DEFS:
                    if pid == ctx.phase_id:
                        continue
                    found = _read(pid)
                    if found:
                        collected = found
                        break

            repos: list[Path] = []
            for r in collected:
                repo = Path(r)
                if repo.exists() and repo not in repos:
                    repos.append(repo)
            return repos
        except Exception:
            log.debug("inputs.json 读取失败", exc_info=True)
        return []
