from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse, urlunparse

from qualix.log import get_logger

log = get_logger(__name__)

if TYPE_CHECKING:
    from collections.abc import Callable


def load_larkkit() -> tuple[Any, Callable[[int], str]]:
    try:
        from larkkit.core.client import FeishuClient  # type: ignore
        from larkkit.core.constants import get_code_language  # type: ignore

        return FeishuClient, get_code_language
    except Exception:
        log.warning("Failed to load larkkit FeishuClient", exc_info=True)

    uv_site_root = Path.home() / ".local/share/uv/tools/larkkit/lib"
    candidates = sorted(uv_site_root.glob("python*/site-packages"), reverse=True)
    for path in candidates:
        path_str = str(path)
        if path_str not in sys.path:
            sys.path.insert(0, path_str)
        try:
            from larkkit.core.client import FeishuClient  # type: ignore
            from larkkit.core.constants import get_code_language  # type: ignore

            return FeishuClient, get_code_language
        except Exception:
            log.debug("larkkit import failed from %s, trying next", path_str)
            continue

    raise RuntimeError("无法导入 larkkit。请先安装并确保可用，例如执行 `larkkit version`。")


def parse_feishu_url(url: str) -> tuple[str, str]:
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        raise ValueError(f"URL 非法: {url}")

    parts = [p for p in parsed.path.split("/") if p]
    if len(parts) < 2:
        raise ValueError(f"无法从 URL 提取文档 token: {url}")

    head = parts[0].lower()
    token = parts[1]

    if head == "wiki":
        return "wiki", token
    if head in {"docx", "docs", "document"}:
        return "docx", token
    raise ValueError(f"暂不支持的飞书链接类型: /{head}/")


def parse_feishu_reference_url(url: str) -> tuple[str, str]:
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        raise ValueError(f"URL 非法: {url}")

    parts = [p for p in parsed.path.split("/") if p]
    if len(parts) < 2:
        raise ValueError(f"无法从 URL 提取 token: {url}")

    head = parts[0].lower()
    token = parts[1]

    if head == "wiki":
        return "wiki", token
    if head in {"docx", "docs", "document"}:
        return "docx", token
    if head in {"sheets", "sheet"}:
        return "sheets", token
    if head in {"base", "bitable"}:
        return "bitable", token
    raise ValueError(f"暂不支持的飞书引用类型: /{head}/")


def normalize_url(url: str) -> str:
    parsed = urlparse(url)
    cleaned = parsed._replace(params="", query="", fragment="")
    return urlunparse(cleaned)


def call_with_token_fallback(
    action: Callable[[bool], Any],
    prefer_user_token: bool,
) -> tuple[Any, bool]:
    attempts = [prefer_user_token, not prefer_user_token]
    last_error: Exception | None = None
    for use_user_token in attempts:
        try:
            return action(use_user_token), use_user_token
        except Exception as exc:  # pragma: no cover
            err_str = str(exc).lower()
            last_error = exc
            # 如果是 user token 过期，尝试刷新后重试一次
            if use_user_token and ("401" in err_str or "expired" in err_str or "invalid" in err_str):
                # token 过期，fallback 到 tenant token 会在下一轮尝试
                continue
            # 如果是 user_access_token_not_supported，直接跳到 tenant token
            if "99991668" in err_str or "user access token not support" in err_str:
                continue
    if last_error is not None:
        raise last_error
    raise RuntimeError("内部错误：未执行任何 token 请求")


def resolve_input_doc(
    client: Any,
    input_url: str,
    prefer_user_token: bool,
) -> dict[str, Any]:
    doc_type, token = parse_feishu_url(input_url)

    resolved = {
        "input_type": doc_type,
        "input_token": token,
        "resolved_doc_type": "docx",
        "resolved_doc_id": token,
        "wiki_node": None,
    }

    if doc_type == "wiki":
        try:
            node_info, node_use_user_token = call_with_token_fallback(
                lambda use_user_token: client.get_wiki_node_info(token, use_user_token=use_user_token),
                prefer_user_token,
            )
        except Exception as exc:
            err_str = str(exc).lower()
            if "403" in err_str or "permission" in err_str or "无权限" in str(exc):
                raise RuntimeError(
                    f"Wiki 节点无权限访问 (token={token})。\n"
                    "  排查步骤:\n"
                    "  1. 在浏览器确认当前账号可打开该 Wiki 链接\n"
                    "  2. 执行 `uvx larkkit auth status` 检查 token 状态\n"
                    "  3. 如果使用 tenant token，确认应用已被添加到该知识空间\n"
                    "  4. 尝试切换 token 类型: --prefer-tenant-token 或 --prefer-user-token"
                ) from exc
            if "401" in err_str or "expired" in err_str:
                raise RuntimeError(
                    f"Wiki 节点访问 token 已过期 (token={token})。\n  执行 `uvx larkkit auth refresh` 刷新后重试。"
                ) from exc
            raise

        if not node_info:
            raise RuntimeError(
                f"Wiki 节点返回空 (token={token})，可能无权限或链接失效。\n"
                "  排查步骤:\n"
                "  1. 在浏览器确认该 Wiki 链接可正常打开\n"
                "  2. 执行 `uvx larkkit auth status` 检查授权状态\n"
                "  3. 尝试 --prefer-tenant-token 或 --prefer-user-token 切换 token 类型"
            )

        obj_type = node_info.get("obj_type", "")
        obj_token = node_info.get("obj_token", "")
        if obj_type == "bitable" and obj_token:
            resolved["resolved_doc_type"] = "bitable"
            resolved["resolved_doc_id"] = obj_token
            resolved["wiki_node"] = node_info
            resolved["wiki_resolve_use_user_token"] = node_use_user_token
        elif obj_type == "docx" and obj_token:
            resolved["resolved_doc_id"] = obj_token
            resolved["wiki_node"] = node_info
            resolved["wiki_resolve_use_user_token"] = node_use_user_token
        elif not obj_token:
            raise RuntimeError(f"Wiki 节点 obj_token 为空: obj_type={obj_type}。\n  可能无权限或链接失效。")
        else:
            raise RuntimeError(
                f"Wiki 节点类型不支持: obj_type={obj_type}, obj_token={obj_token}。\n"
                "  当前支持 docx 和 bitable 类型的 Wiki 节点。"
            )

    return resolved
