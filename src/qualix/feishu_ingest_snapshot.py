"""Snapshot helpers for feishu ingest regression replay."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from qualix.ingest.feishu.auth import load_larkkit, parse_feishu_url
from qualix.ingest.feishu.crawler import crawl_documents
from qualix.json_utils import dump_json_str, load_json_strict, save_json

if TYPE_CHECKING:
    from pathlib import Path

SNAPSHOT_FILES = (
    "ingest.json",
    "asset_manifest.json",
    "dependency_graph.json",
    "aggregate_ingest.json",
    "plain_text.txt",
)

VOLATILE_KEYS = {
    "generated_at",
}

NORMALIZED_PATH_KEYS = {
    "path",
    "output_dir",
    "dependency_graph_path",
    "aggregate_plain_text_path",
    "ingest_path",
    "plain_text_path",
    "asset_manifest_path",
    "raw_blocks_path",
}


def build_snapshot_case_name(url: str, case_name: str | None) -> str:
    if case_name:
        return case_name
    doc_type, token = parse_feishu_url(url)
    return f"{doc_type}_{token}"


def _normalize_value(value: Any) -> Any:
    if isinstance(value, dict):
        normalized: dict[str, Any] = {}
        for key, item in value.items():
            if key in VOLATILE_KEYS:
                continue
            if key in NORMALIZED_PATH_KEYS:
                normalized[key] = "<normalized>"
                continue
            normalized[key] = _normalize_value(item)
        return normalized
    if isinstance(value, list):
        return [_normalize_value(item) for item in value]
    return value


def normalize_snapshot_bundle(bundle: dict[str, Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    for name, payload in bundle.items():
        if name.endswith(".json"):
            normalized[name] = _normalize_value(payload)
        else:
            normalized[name] = payload
    return normalized


def collect_snapshot_bundle(output_dir: Path) -> dict[str, Any]:
    bundle: dict[str, Any] = {}
    for filename in SNAPSHOT_FILES:
        path = output_dir / filename
        if not path.exists():
            continue
        if filename.endswith(".json"):
            bundle[filename] = load_json_strict(path)
        else:
            bundle[filename] = path.read_text(encoding="utf-8")
    return bundle


def save_snapshot(snapshot_dir: Path, case_name: str, bundle: dict[str, Any]) -> Path:
    case_dir = snapshot_dir / case_name
    case_dir.mkdir(parents=True, exist_ok=True)
    for name, payload in bundle.items():
        path = case_dir / name
        if name.endswith(".json"):
            save_json(path, payload, sort_keys=True)
        else:
            path.write_text(str(payload), encoding="utf-8")
    return case_dir


def load_snapshot(snapshot_dir: Path, case_name: str) -> dict[str, Any]:
    case_dir = snapshot_dir / case_name
    if not case_dir.exists():
        raise FileNotFoundError(f"Snapshot case not found: {case_name}")

    bundle: dict[str, Any] = {}
    for path in sorted(case_dir.iterdir()):
        if not path.is_file():
            continue
        if path.suffix == ".json":
            bundle[path.name] = load_json_strict(path)
        else:
            bundle[path.name] = path.read_text(encoding="utf-8")
    return bundle


def assert_snapshot_case(
    snapshot_dir: Path,
    case_name: str,
    actual_bundle: dict[str, Any],
    *,
    update: bool,
) -> None:
    normalized_actual = normalize_snapshot_bundle(actual_bundle)
    if update:
        save_snapshot(snapshot_dir, case_name, normalized_actual)
        return

    expected_bundle = load_snapshot(snapshot_dir, case_name)
    if expected_bundle != normalized_actual:
        raise AssertionError(
            f"Snapshot mismatch for case: {case_name}\n"
            f"expected={dump_json_str(expected_bundle, sort_keys=True)}\n"
            f"actual={dump_json_str(normalized_actual, sort_keys=True)}"
        )


def run_feishu_snapshot_case(
    url: str,
    output_dir: Path,
    *,
    prefer_user_token: bool = True,
    download_images: bool = True,
    save_raw_blocks: bool = False,
    asset_retries: int = 2,
    include_raw_image_keys: bool = True,
    recursive_mentions: bool = True,
    canonicalize_mentions: bool = True,
    max_depth: int = 3,
    max_docs: int = 30,
) -> dict[str, Any]:
    feishu_client_cls, get_code_language = load_larkkit()
    output_dir.mkdir(parents=True, exist_ok=True)
    client = feishu_client_cls()
    crawl_documents(
        client=client,
        get_code_language=get_code_language,
        root_url=url,
        output_dir=output_dir,
        prefer_user_token=prefer_user_token,
        download_images=download_images,
        save_raw_blocks=save_raw_blocks,
        asset_retries=max(asset_retries, 0),
        include_raw_image_keys=include_raw_image_keys,
        recursive_mentions=recursive_mentions,
        canonicalize_mentions=canonicalize_mentions,
        max_depth=max(max_depth, 0),
        max_docs=max(max_docs, 1),
    )
    return collect_snapshot_bundle(output_dir)
