from __future__ import annotations

from dqg.cache.image_cache import save_image_semantic, search_image_semantics
from dqg.text_utils import build_fts_query, build_fts_query_tokens, text_query_has_signal, tokenize_chinese


def test_tokenize_chinese_does_not_cross_punctuation_boundaries() -> None:
    tokens = tokenize_chinese("权限，校验")
    parts = tokens.split()

    assert "权限" in parts
    assert "校验" in parts
    assert "权限校" not in parts
    assert "限校" not in parts


def test_tokenize_chinese_splits_identifiers_and_keeps_whole_token() -> None:
    tokens = tokenize_chinese("camelCase snake_case kebab-case id123")
    parts = tokens.split()

    assert "camelcase" in parts
    assert "camel" in parts
    assert "case" in parts
    assert "snake_case" in parts
    assert "snake" in parts
    assert "kebab-case" in parts
    assert "kebab" in parts
    assert "id123" in parts


def test_build_fts_query_prefers_longer_signals() -> None:
    tokens = build_fts_query_tokens("权限，校验")
    query = build_fts_query("权限，校验", mode="AND")

    assert "权限" in tokens
    assert "校验" in tokens
    assert query
    assert '"权限"' in query


def test_text_query_has_signal_detects_real_match_only() -> None:
    assert text_query_has_signal("权限校验", "需要权限校验和拦截")
    assert not text_query_has_signal("权限校验", "库存同步异常")


def test_search_image_semantics_uses_shared_fts_query_builder(tmp_path) -> None:
    output_dir = tmp_path / "output"

    save_image_semantic(
        output_dir,
        "demo",
        "Q01",
        {
            "filename": "board.png",
            "kind": "board",
            "description": "权限校验状态机",
            "related_reqs": ["REQ-001"],
            "section_context": "权限校验",
        },
    )
    save_image_semantic(
        output_dir,
        "demo",
        "Q01",
        {
            "filename": "other.png",
            "kind": "image",
            "description": "库存同步流程",
            "related_reqs": ["REQ-002"],
            "section_context": "库存同步",
        },
    )

    results = search_image_semantics(output_dir, "权限，校验", project_id="demo")

    assert len(results) == 1
    assert results[0]["filename"] == "board.png"
