"""Provider-neutral document ingest bundle contracts."""

from __future__ import annotations

import shutil
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, ClassVar

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
