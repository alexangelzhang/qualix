from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from qualix.ingest.feishu.auth import normalize_url, parse_feishu_reference_url, resolve_input_doc


def resolve_mention_target(
    mention: dict[str, Any],
    default_scheme: str,
    default_host: str,
) -> tuple[str, str, str, str]:
    mention_url = str(mention.get("url", "") or "").strip()
    mention_token = str(mention.get("token", "") or "").strip()
    mention_obj_type = str(mention.get("obj_type", "") or "").strip()

    if mention_url:
        normalized = normalize_url(mention_url)
        try:
            ref_type, token = parse_feishu_reference_url(normalized)
            return normalized, ref_type, token, "ok"
        except Exception as exc:
            return "", "", "", f"unsupported_mention_url:{exc}"

    if mention_token:
        if mention_obj_type and mention_obj_type != "22":
            return "", "", "", f"unsupported_obj_type:{mention_obj_type}"
        synthetic_url = f"{default_scheme}://{default_host}/docx/{mention_token}"
        return synthetic_url, "docx", mention_token, "token_only_docx_guess"

    return "", "", "", "missing_url_and_token"


def canonicalize_mention_target(
    client: Any,
    target_url: str,
    target_type: str,
    target_token: str,
    prefer_user_token: bool,
) -> tuple[str, str, str]:
    if target_type not in {"docx", "wiki"}:
        return target_url, f"{target_type}:{target_token}", "not_doc_like"

    try:
        resolved = resolve_input_doc(client, target_url, prefer_user_token)
        doc_id = str(resolved.get("resolved_doc_id", "") or "").strip()
        if not doc_id:
            return target_url, f"{target_type}:{target_token}", "canonicalize_missing_doc_id"

        parsed = urlparse(target_url)
        scheme = parsed.scheme or "https"
        host = parsed.netloc
        if not host:
            return target_url, f"docx:{doc_id}", "canonicalize_no_host"

        canonical_url = f"{scheme}://{host}/docx/{doc_id}"
        canonical_key = f"docx:{doc_id}"
        if canonical_key == f"{target_type}:{target_token}":
            return canonical_url, canonical_key, "already_canonical"

        return canonical_url, canonical_key, f"canonicalized_from_{target_type}"
    except Exception as exc:  # pragma: no cover
        return target_url, f"{target_type}:{target_token}", f"canonicalize_failed:{exc}"
