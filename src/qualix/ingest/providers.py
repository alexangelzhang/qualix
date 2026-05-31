"""Provider registry for Q01 document ingest."""

from __future__ import annotations

from pathlib import Path

from qualix.ingest.bundle import DocumentSourceProvider, EnterpriseUrlProvider, IngestBundle, LocalFileProvider


def default_document_providers() -> list[DocumentSourceProvider]:
    return [LocalFileProvider(), EnterpriseUrlProvider()]


def ingest_document(
    source: str,
    output_dir: Path,
    providers: list[DocumentSourceProvider] | None = None,
) -> IngestBundle:
    for provider in providers or default_document_providers():
        if provider.can_handle(source):
            return provider.ingest(source, output_dir)
    raise ValueError(f"No document ingest provider can handle source: {source}")
