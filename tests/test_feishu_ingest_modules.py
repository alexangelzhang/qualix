"""Tests for modularized feishu ingest components."""

from qualix.ingest.error_strategy import classify_error, derive_final_error_type, map_failure_category
from qualix.ingest.feishu.asset_downloader import append_raw_image_key_assets
from qualix.ingest.feishu.auth import normalize_url, parse_feishu_reference_url, parse_feishu_url
from qualix.ingest.feishu.crawler import collect_mention_docs
from qualix.ingest.feishu.mention_graph import resolve_mention_target


def test_parse_feishu_url_docx_and_wiki() -> None:
    assert parse_feishu_url("https://example.feishu.cn/docx/AAA123") == ("docx", "AAA123")
    assert parse_feishu_url("https://example.feishu.cn/wiki/BBB456") == ("wiki", "BBB456")


def test_parse_feishu_reference_url_supports_sheet_and_bitable() -> None:
    assert parse_feishu_reference_url("https://example.feishu.cn/sheets/SSS111") == ("sheets", "SSS111")
    assert parse_feishu_reference_url("https://example.feishu.cn/base/BASE222") == ("bitable", "BASE222")


def test_normalize_url_strips_query_and_fragment() -> None:
    assert normalize_url("https://example.feishu.cn/docx/AAA123?a=1#x") == "https://example.feishu.cn/docx/AAA123"


def test_error_strategy_basics() -> None:
    assert classify_error("[403] no permission") == "permission_denied"
    assert map_failure_category("permission_denied") == "permission_or_scope"
    attempts = [
        {"error_type": "token_refreshed"},
        {"error_type": "network_error"},
        {"error_type": "permission_denied"},
    ]
    assert derive_final_error_type(attempts) == "permission_denied"


def test_append_raw_image_key_assets_deduplicates() -> None:
    assets = [{"kind": "image", "token": "img_existing"}]
    merged = append_raw_image_key_assets(assets, ["img_existing", "img_new"])
    keys = {(item["kind"], item["token"]) for item in merged}
    assert ("image", "img_existing") in keys
    assert ("image_raw_key", "img_new") in keys
    assert ("image_raw_key", "img_existing") in keys
    assert len(merged) == 3


def test_resolve_mention_target_token_only() -> None:
    mention = {"token": "DOC_1", "obj_type": "22"}
    url, ref_type, token, reason = resolve_mention_target(mention, "https", "example.feishu.cn")
    assert url == "https://example.feishu.cn/docx/DOC_1"
    assert ref_type == "docx"
    assert token == "DOC_1"
    assert reason == "token_only_docx_guess"


def test_collect_mention_docs() -> None:
    blocks = [
        {
            "block_id": "b1",
            "block_type": 2,
            "text": {
                "elements": [
                    {
                        "mention_doc": {
                            "token": "TOKEN_1",
                            "url": "https://example.feishu.cn/docx/TOKEN_1",
                            "title": "Doc",
                            "obj_type": "22",
                        }
                    }
                ]
            },
        }
    ]
    docs = collect_mention_docs(blocks)
    assert len(docs) == 1
    assert docs[0]["token"] == "TOKEN_1"
