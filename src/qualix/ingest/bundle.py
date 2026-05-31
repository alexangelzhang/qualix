"""Provider-neutral document ingest bundle contracts."""

from __future__ import annotations

import shutil
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, ClassVar
from urllib.parse import urlparse

from qualix.constants import (
    ENTERPRISE_DOCUMENT_DINGTALK_HOSTS,
    ENTERPRISE_DOCUMENT_DINGTALK_PROVIDER_ID,
    ENTERPRISE_DOCUMENT_LARK_HOSTS,
    ENTERPRISE_DOCUMENT_LARK_PROVIDER_ID,
)
from qualix.exceptions import IngestError
from qualix.json_utils import save_json


@dataclass(frozen=True)
class IngestAsset:
    path: str
    kind: str = "file"
    source_url: str = ""


@dataclass(frozen=True)
class IngestBundle:
    source: str
    provider_id: str
    output_dir: Path
    plain_text_path: Path
    blocks_path: Path | None = None
    source_map_path: Path | None = None
    assets_dir: Path | None = None
    assets: list[IngestAsset] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def write_manifest(self) -> Path:
        manifest_path = self.output_dir / "manifest.json"
        save_json(manifest_path, self.to_manifest())
        return manifest_path

    def to_manifest(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "generated_at": datetime.now().isoformat(),
            "source": self.source,
            "provider_id": self.provider_id,
            "plain_text_path": str(self.plain_text_path),
            "blocks_path": str(self.blocks_path) if self.blocks_path else "",
            "source_map_path": str(self.source_map_path) if self.source_map_path else "",
            "assets_dir": str(self.assets_dir) if self.assets_dir else "",
            "assets": [asset.__dict__ for asset in self.assets],
            "metadata": self.metadata,
        }


class DocumentSourceProvider(ABC):
    provider_id: str

    @abstractmethod
    def can_handle(self, source: str) -> bool:
        """Return whether this provider can ingest the source."""

    @abstractmethod
    def ingest(self, source: str, output_dir: Path) -> IngestBundle:
        """Ingest the source into output_dir and return a bundle."""


class LocalFileProvider(DocumentSourceProvider):
    provider_id = "local-file"
    _SUPPORTED_SUFFIXES: ClassVar[set[str]] = {".md", ".markdown", ".txt", ".html", ".htm"}

    def can_handle(self, source: str) -> bool:
        path = Path(source).expanduser()
        return path.is_file() and path.suffix.lower() in self._SUPPORTED_SUFFIXES

    def ingest(self, source: str, output_dir: Path) -> IngestBundle:
        path = Path(source).expanduser().resolve()
        output_dir.mkdir(parents=True, exist_ok=True)
        plain_text_path = output_dir / "plain_text.md"
        if path.resolve() != plain_text_path.resolve():
            shutil.copyfile(path, plain_text_path)

        source_map_path = output_dir / "source_map.json"
        save_json(
            source_map_path,
            {
                "schema_version": 1,
                "provider_id": self.provider_id,
                "source": str(path),
                "segments": [
                    {
                        "segment_id": "SRC-001",
                        "source": str(path),
                        "target": str(plain_text_path),
                    }
                ],
            },
        )
        bundle = IngestBundle(
            source=str(path),
            provider_id=self.provider_id,
            output_dir=output_dir,
            plain_text_path=plain_text_path,
            source_map_path=source_map_path,
            metadata={"original_suffix": path.suffix.lower()},
        )
        bundle.write_manifest()
        return bundle


class EnterpriseUrlProvider(DocumentSourceProvider):
    provider_id = "enterprise-url"

    def can_handle(self, source: str) -> bool:
        return self._platform(source) != ""

    def ingest(self, source: str, output_dir: Path) -> IngestBundle:
        platform = self._platform(source)
        if platform == "dingtalk":
            provider_id = ENTERPRISE_DOCUMENT_DINGTALK_PROVIDER_ID
            guidance = (
                "DingTalk document ingest is recognized but no connector is configured yet. "
                "Use a local browser export or register a DingTalk provider that writes the standard IngestBundle."
            )
        elif platform == "lark":
            provider_id = ENTERPRISE_DOCUMENT_LARK_PROVIDER_ID
            guidance = (
                "Lark/Feishu document ingest is optional and must use a personal token for documents you can access. "
                "Set QUALIX_LARK_USER_TOKEN or use a local export; Qualix will not start OAuth automatically."
            )
        else:
            raise ValueError(f"Unsupported enterprise document source: {source}")

        raise IngestError(f"{provider_id}: {guidance} Source: {source}")

    def _platform(self, source: str) -> str:
        parsed = urlparse(source)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            return ""
        host = parsed.netloc.lower().split(":", maxsplit=1)[0]
        if self._host_matches(host, ENTERPRISE_DOCUMENT_DINGTALK_HOSTS):
            return "dingtalk"
        if self._host_matches(host, ENTERPRISE_DOCUMENT_LARK_HOSTS):
            return "lark"
        return ""

    @staticmethod
    def _host_matches(host: str, suffixes: tuple[str, ...]) -> bool:
        return any(host == suffix or host.endswith(f".{suffix}") for suffix in suffixes)
