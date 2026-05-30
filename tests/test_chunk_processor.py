from __future__ import annotations

import qualix.context.chunk_processor as chunk_processor
from qualix.context.context_loader import ContextChunk


def test_split_large_chunk_reuses_token_cache_for_duplicate_paragraphs(monkeypatch) -> None:
    calls: list[str] = []

    def fake_estimate_tokens(text: str) -> int:
        calls.append(text)
        return len(text)

    monkeypatch.setattr(chunk_processor, "estimate_tokens", fake_estimate_tokens)

    repeated_para = "重复段落内容"
    chunk = ContextChunk(
        source="Phase X 报告",
        content="\n\n".join([repeated_para, repeated_para, repeated_para]),
        token_estimate=999,
        priority=1,
    )

    result = chunk_processor._split_large_chunk(chunk, max_tokens=8)

    assert [c.content for c in result] == [repeated_para, repeated_para, repeated_para]
    assert calls.count(repeated_para) == 1


def test_compact_chunk_reuses_token_cache_across_compaction_steps(monkeypatch) -> None:
    calls: list[str] = []

    def fake_estimate_tokens(text: str) -> int:
        calls.append(text)
        return len(text)

    monkeypatch.setattr(chunk_processor, "estimate_tokens", fake_estimate_tokens)

    repeated_para = "重复压缩段落"
    content = "\n\n".join([repeated_para, repeated_para, repeated_para])
    chunk = ContextChunk(
        source="Phase X 文档",
        content=content,
        token_estimate=len(content),
        priority=2,
    )

    result = chunk_processor._compact_chunk(chunk, target_tokens=4)

    assert result.source.endswith("(compressed)") or result.source.endswith("(hard-truncated)")
    assert calls.count(repeated_para) == 1
    assert result.content
    assert result.token_estimate == 4
