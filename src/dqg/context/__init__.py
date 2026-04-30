"""context package — facade for backward-compatible imports.

After the sub-package split, old import paths like
``from dqg.context.context_loader import load_context``
still work via lazy sys.modules aliases.
"""

from __future__ import annotations

from dqg.compat import install_module_aliases

_ALIASES: dict[str, str] = {
    # loading/
    "dqg.context.bootstrap_context": "dqg.context.loading.bootstrap_context",
    "dqg.context.context_loader": "dqg.context.loading.context_loader",
    "dqg.context.doc_summary": "dqg.context.loading.doc_summary",
    "dqg.context.evidence_renderer": "dqg.context.loading.evidence_renderer",
    "dqg.context.file_snapshot": "dqg.context.loading.file_snapshot",
    "dqg.context.upstream_collector": "dqg.context.loading.upstream_collector",
    # chunking/
    "dqg.context.chunk_processor": "dqg.context.chunking.chunk_processor",
    "dqg.context.chunk_summarizer": "dqg.context.chunking.chunk_summarizer",
    "dqg.context.context_compressor": "dqg.context.chunking.context_compressor",
    "dqg.context.prompt_compressor": "dqg.context.chunking.prompt_compressor",
    "dqg.context.summarize_text": "dqg.context.chunking.summarize_text",
    # analysis/
    "dqg.context.assert_semantic_mapper": "dqg.context.analysis.assert_semantic_mapper",
    "dqg.context.code_skeleton": "dqg.context.analysis.code_skeleton",
    "dqg.context.java_ast_analyzer": "dqg.context.analysis.java_ast_analyzer",
    "dqg.context.weak_assert_analysis": "dqg.context.analysis.weak_assert_analysis",
    "dqg.context.weak_assert_context": "dqg.context.analysis.weak_assert_context",
}

install_module_aliases(_ALIASES, __name__)
