"""Qualix Feishu/Lark client.

Reads Qualix-owned auth config from environment variables or
``~/.qualix/auth/lark.ini``. Missing credentials keep the caller in no-op mode.
"""

from __future__ import annotations

import urllib.error
import urllib.request
from typing import Any

from qualix.feishu.auth_config import load_lark_auth_config
from qualix.json_utils import dump_json_str, parse_json_str

_FEISHU_API = "https://open.feishu.cn/open-apis"


def _get_user_token() -> str | None:
    """Return the configured Lark user token, if present."""
    return load_lark_auth_config().user_token or None


def _get_user_email() -> str:
    """Return the configured user email, if present."""
    return load_lark_auth_config().email


def is_logged_in() -> bool:
    """检测是否已有可用的 user_token."""
    return bool(_get_user_token())


def _http_post(url: str, body: dict, headers: dict | None = None) -> dict:
    """简单 HTTP POST，返回解析后的 JSON."""
    data = dump_json_str(body, indent=None).encode()
    req_headers = {"Content-Type": "application/json; charset=utf-8"}
    if headers:
        req_headers.update(headers)
    req = urllib.request.Request(url, data=data, headers=req_headers, method="POST")
    with urllib.request.urlopen(req, timeout=15) as resp:
        return parse_json_str(resp.read())


def bitable_create_record(
    base_token: str,
    table_id: str,
    fields: dict[str, Any],
) -> str | None:
    """新增 bitable 记录，返回 record_id，失败返回 None."""
    user_token = _get_user_token()
    if not user_token:
        return None

    url = f"{_FEISHU_API}/bitable/v1/apps/{base_token}/tables/{table_id}/records"
    try:
        resp = _http_post(
            url,
            {"fields": fields},
            headers={"Authorization": f"Bearer {user_token}"},
        )
        if resp.get("code") == 0:
            return resp.get("data", {}).get("record", {}).get("record_id")
        return None
    except Exception:
        return None


def bitable_list_records(
    base_token: str,
    table_id: str,
    page_size: int = 100,
) -> list[dict[str, Any]]:
    """查询 bitable 记录列表，返回所有记录的 fields 列表."""
    user_token = _get_user_token()
    if not user_token:
        return []

    records = []
    page_token = None
    while True:
        url = f"{_FEISHU_API}/bitable/v1/apps/{base_token}/tables/{table_id}/records?page_size={page_size}"
        if page_token:
            url += f"&page_token={page_token}"
        try:
            req = urllib.request.Request(
                url,
                headers={"Authorization": f"Bearer {user_token}"},
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = parse_json_str(resp.read())
            if data.get("code") != 0:
                break
            items = data.get("data", {}).get("items", [])
            for item in items:
                raw_fields = item.get("fields", {})
                normalized = {}
                for k, v in raw_fields.items():
                    if isinstance(v, dict) and "text" in v:
                        normalized[k] = v["text"]
                    elif isinstance(v, list) and v and isinstance(v[0], dict) and "text" in v[0]:
                        normalized[k] = "".join(i.get("text", "") for i in v)
                    else:
                        normalized[k] = v
                records.append(normalized)
            if not data.get("data", {}).get("has_more"):
                break
            page_token = data.get("data", {}).get("page_token")
        except Exception:
            break
    return records
