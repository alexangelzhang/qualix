"""context package — facade for backward-compatible imports.

After the sub-package split, old import paths like
``from qualix.context.context_loader import load_context``
still work via lazy sys.modules aliases.
"""

from __future__ import annotations

from qualix.compat import install_module_aliases

_ALIASES: dict[str, str] = {
    # loading/
    "qualix.context.bootstrap_context": "qualix.context.loading.bootstrap_context",
    "qualix.context.context_loader": "qualix.context.loading.context_loader",
    "qualix.context.doc_summary": "qualix.context.loading.doc_summary",
    "qualix.context.evidence_renderer": "qualix.context.loading.evidence_renderer",
    "qualix.context.file_snapshot": "qualix.context.loading.file_snapshot",
    "qualix.context.upstream_collector": "qualix.context.loading.upstream_collector",
    # chunking/
    "qualix.context.chunk_processor": "qualix.context.chunking.chunk_processor",
    "qualix.context.chunk_summarizer": "qualix.context.chunking.chunk_summarizer",
    "qualix.context.context_compressor": "qualix.context.chunking.context_compressor",
    "qualix.context.prompt_compressor": "qualix.context.chunking.prompt_compressor",
    "qualix.context.summarize_text": "qualix.context.chunking.summarize_text",
    # analysis/
    "qualix.context.assert_semantic_mapper": "qualix.context.analysis.assert_semantic_mapper",
    "qualix.context.code_skeleton": "qualix.context.analysis.code_skeleton",
    "qualix.context.java_ast_analyzer": "qualix.context.analysis.java_ast_analyzer",
    "qualix.context.weak_assert_analysis": "qualix.context.analysis.weak_assert_analysis",
    "qualix.context.weak_assert_context": "qualix.context.analysis.weak_assert_context",
}

install_module_aliases(_ALIASES, __name__)
