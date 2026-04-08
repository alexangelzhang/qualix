from __future__ import annotations

import re
from typing import Any


def classify_error(err: str) -> str:
    s = (err or "").lower()

    if "unsupported_kind" in s:
        return "unsupported_kind"
    if "99991668" in s or "user access token not support" in s:
        return "user_access_token_not_supported"
    if "234001" in s or "invalid request param" in s:
        return "invalid_request_param"
    if "[401]" in s or " 401" in s or ("token" in s and ("expired" in s or "invalid" in s)):
        return "auth_expired_or_invalid"
    if "[403]" in s or "无权限" in err or "permission" in s:
        return "permission_denied"
    if "[404]" in s or " 404" in s or "not found" in s or "不存在" in err:
        return "not_found"
    if "timeout" in s or "timed out" in s or "network" in s or "connection" in s:
        return "network_error"
    return "unknown_error"


ERROR_TYPE_PRIORITY = [
    "unsupported_kind",
    "permission_denied",
    "auth_expired_or_invalid",
    "not_found",
    "network_error",
    "invalid_request_param",
    "user_access_token_not_supported",
    "unknown_error",
]


def extract_attempt_error_codes(attempts: list[dict[str, Any]]) -> list[str]:
    codes: list[str] = []
    for row in attempts:
        msg = str(row.get("error", "") or "")
        for code in re.findall(r"\[(\d{3,8})\]", msg):
            if code not in codes:
                codes.append(code)
    return codes


def derive_final_error_type(attempts: list[dict[str, Any]]) -> str:
    if not attempts:
        return "unknown_error"

    observed = [
        str(a.get("error_type", "") or "")
        for a in attempts
        if str(a.get("error_type", "") or "") not in {"", "token_refreshed", "token_refresh_failed"}
    ]
    if not observed:
        return str(attempts[-1].get("error_type", "unknown_error") or "unknown_error")

    for error_type in ERROR_TYPE_PRIORITY:
        if error_type in observed:
            return error_type
    return observed[-1]


def map_failure_category(error_type: str) -> str:
    if error_type in {"permission_denied", "user_access_token_not_supported"}:
        return "permission_or_scope"
    if error_type == "auth_expired_or_invalid":
        return "authentication"
    if error_type == "network_error":
        return "network"
    if error_type in {"not_found", "invalid_request_param"}:
        return "resource_or_param"
    if error_type == "unsupported_kind":
        return "unsupported"
    return "unknown"


def build_actionable_guidance(
    kind: str,
    error_type: str,
    attempts: list[dict[str, Any]],
) -> list[str]:
    guidance: list[str] = []
    tried_user = any(bool(a.get("use_user_token")) for a in attempts)
    tried_tenant = any(not bool(a.get("use_user_token")) for a in attempts)
    codes = extract_attempt_error_codes(attempts)

    if error_type == "auth_expired_or_invalid":
        guidance.append("刷新 user_access_token 后重试；必要时重新执行飞书 OAuth 授权。")
        guidance.append("如果是 tenant token 失效，确认应用密钥配置可用并重试。")
        guidance.append("可执行：`uvx larkkit auth status`，异常时执行 `uvx larkkit auth refresh`。")

    if error_type == "user_access_token_not_supported":
        guidance.append("该资源接口不支持 user_access_token，请优先使用 tenant_access_token。")
        guidance.append("可执行：重试命令追加 `--prefer-tenant-token`。")

    if error_type == "invalid_request_param":
        if kind == "image_raw_key":
            guidance.append("raw_content 中提取的 img_v3 key 可能不是可下载图片 key（或已失效），可保留为线索但不应替代 block image token。")
            guidance.append("建议以 `kind=image` 的 block token 下载为主，raw key 仅作补充兜底。")
        else:
            guidance.append("请求参数可能与资源类型不匹配，请核对 token 类型与下载接口是否一致。")

    if error_type == "permission_denied":
        guidance.append("先在浏览器确认当前账号可直接打开该文档/资源，排除资源本身无权限。")
        if kind in {"image", "image_raw_key", "mindnote"}:
            guidance.append("请在飞书开放平台为应用开通文档读取与媒体下载相关权限，并确保该文档空间已授权给应用。")
        if kind == "board":
            guidance.append("请确认应用具备白板导出图片权限（whiteboard download as image）。")
        if not tried_tenant:
            guidance.append("尚未尝试 tenant_access_token，建议重试：`--prefer-tenant-token`。")
        if not tried_user:
            guidance.append("尚未尝试 user_access_token，建议重试：`--prefer-user-token`。")
        guidance.append("可执行：`uvx larkkit auth status` 检查授权状态，必要时执行 `uvx larkkit auth refresh`。")

    if error_type == "network_error":
        guidance.append("检查网络连通性或代理配置后重试；可适当增加重试次数。")
    if error_type == "not_found":
        guidance.append("确认资源 token 仍有效，且资源未被删除或替换。")
    if codes:
        guidance.append(f"本次失败命中错误码: {', '.join(codes)}。")
    if not guidance:
        guidance.append("请查看 attempts 明细中的错误码并按权限/鉴权/网络三类逐项排查。")
    return guidance
