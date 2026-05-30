from __future__ import annotations

import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from qualix.ingest.common import REQUEST_TIMEOUT_SECONDS
from qualix.ingest.error_strategy import (
    build_actionable_guidance,
    classify_error,
    derive_final_error_type,
    map_failure_category,
)


_RE_UNSAFE_FILENAME = re.compile(r"[^A-Za-z0-9._-]+")


def sanitize_filename(raw: str) -> str:
    value = _RE_UNSAFE_FILENAME.sub("_", raw).strip("._")
    return value or "asset"


def guess_ext(name: str, default_ext: str = ".png") -> str:
    ext = Path(name).suffix.lower()
    if ext in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}:
        return ext
    return default_ext


def save_stream_to_file(response: Any, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    with open(target, "wb") as file:
        for chunk in response.iter_content(chunk_size=8192):
            if chunk:
                file.write(chunk)


def download_image_by_raw_key(
    client: Any,
    image_key: str,
    target: Path,
    use_user_token: bool,
) -> None:
    url = f"{client.BASE_URL}/im/v1/images/{image_key}"
    headers = client._get_headers(use_user_token)  # type: ignore[attr-defined]
    response = client._session.get(  # type: ignore[attr-defined]
        url,
        headers=headers,
        stream=True,
        timeout=REQUEST_TIMEOUT_SECONDS,
    )

    if response.status_code == 401:
        raise RuntimeError("[401] access_token expired or invalid")
    if response.status_code == 403:
        raise RuntimeError("[403] permission denied for image key")

    content_type = response.headers.get("content-type", "")
    if content_type.startswith("application/json"):
        data = response.json()
        code = int(data.get("code", 0) or 0)
        if code != 0:
            msg = str(data.get("msg", ""))
            raise RuntimeError(f"[{code}] {msg}")
        download_url = str((data.get("data") or {}).get("download_url", "") or "")
        if not download_url:
            raise RuntimeError("image_key_download_url_missing")
        response = client._session.get(  # type: ignore[attr-defined]
            download_url,
            stream=True,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )

    response.raise_for_status()
    save_stream_to_file(response, target)


def download_one_asset(
    client: Any,
    kind: str,
    token: str,
    target: Path,
    use_user_token: bool,
) -> None:
    if kind == "image":
        client.download_media(token, str(target), use_user_token=use_user_token)
        return
    if kind == "board":
        client.download_whiteboard_image(token, str(target), use_user_token=use_user_token)
        return
    if kind == "mindnote":
        client.download_mindnote_image(token, str(target), use_user_token=use_user_token)
        return
    if kind == "image_raw_key":
        download_image_by_raw_key(client, token, target, use_user_token=use_user_token)
        return
    raise RuntimeError("unsupported_kind")


def attempt_download_asset(
    client: Any,
    kind: str,
    token: str,
    target: Path,
    prefer_user_token: bool,
    retries: int,
) -> dict[str, Any]:
    attempts: list[dict[str, Any]] = []
    mode_order = [prefer_user_token, not prefer_user_token]

    if kind == "image_raw_key":
        mode_order = [False, True]

    for use_user_token in mode_order:
        local_try = 0
        while local_try <= max(retries, 0):
            local_try += 1
            try:
                download_one_asset(
                    client=client,
                    kind=kind,
                    token=token,
                    target=target,
                    use_user_token=use_user_token,
                )
                return {
                    "status": "downloaded",
                    "error": "",
                    "error_type": "",
                    "failure_category": "",
                    "use_user_token": use_user_token,
                    "attempts": attempts,
                    "guidance": [],
                }
            except Exception as exc:  # pragma: no cover
                err = str(exc)
                err_type = classify_error(err)
                attempts.append(
                    {
                        "attempt": len(attempts) + 1,
                        "local_retry": local_try,
                        "use_user_token": use_user_token,
                        "error": err,
                        "error_type": err_type,
                    }
                )

                if err_type == "auth_expired_or_invalid" and use_user_token:
                    try:
                        client.refresh_user_access_token()
                        attempts.append(
                            {
                                "attempt": len(attempts) + 1,
                                "local_retry": local_try,
                                "use_user_token": use_user_token,
                                "error": "",
                                "error_type": "token_refreshed",
                                "note": "refresh_user_access_token_success",
                            }
                        )
                    except Exception as refresh_exc:  # pragma: no cover
                        attempts.append(
                            {
                                "attempt": len(attempts) + 1,
                                "local_retry": local_try,
                                "use_user_token": use_user_token,
                                "error": str(refresh_exc),
                                "error_type": "token_refresh_failed",
                            }
                        )

                if err_type in {
                    "permission_denied",
                    "user_access_token_not_supported",
                    "not_found",
                    "unsupported_kind",
                    "invalid_request_param",
                }:
                    break

                if local_try <= retries:
                    time.sleep(0.2)

    if kind == "image":
        try:
            download_image_by_raw_key(client, token, target, use_user_token=False)
            attempts.append(
                {
                    "attempt": len(attempts) + 1,
                    "local_retry": 1,
                    "use_user_token": False,
                    "error": "",
                    "error_type": "fallback_im_v1_images_success",
                }
            )
            return {
                "status": "downloaded",
                "error": "",
                "error_type": "",
                "failure_category": "",
                "use_user_token": False,
                "attempts": attempts,
                "guidance": [],
            }
        except Exception as fallback_exc:  # pragma: no cover
            attempts.append(
                {
                    "attempt": len(attempts) + 1,
                    "local_retry": 1,
                    "use_user_token": False,
                    "error": str(fallback_exc),
                    "error_type": classify_error(str(fallback_exc)),
                    "note": "fallback_im_v1_images_failed",
                }
            )

    last_error = attempts[-1]["error"] if attempts else "download_failed_without_attempt"
    final_error_type = derive_final_error_type(attempts)
    return {
        "status": "failed",
        "error": last_error,
        "error_type": final_error_type,
        "failure_category": map_failure_category(final_error_type),
        "use_user_token": None,
        "attempts": attempts,
        "guidance": build_actionable_guidance(kind, final_error_type, attempts),
    }


def append_raw_image_key_assets(
    assets: list[dict[str, Any]],
    raw_image_keys: list[str],
) -> list[dict[str, Any]]:
    seen: set[tuple[str, str]] = {(str(a.get("kind", "")), str(a.get("token", ""))) for a in assets}
    merged = list(assets)

    for image_key in raw_image_keys:
        key = ("image_raw_key", image_key)
        if key in seen:
            continue
        seen.add(key)
        merged.append(
            {
                "kind": "image_raw_key",
                "token": image_key,
                "name": image_key,
                "alt": "",
                "block_id": "",
                "section_path": "RAW_CONTENT_IMAGES",
                "source_block_ids": [],
                "source": "raw_content",
            }
        )

    return merged


def _prepare_asset_task(
    idx: int,
    asset: dict[str, Any],
    output_dir: Path,
) -> dict[str, Any]:
    """Prepare asset metadata and target path without downloading."""
    kind = str(asset.get("kind", "") or "")
    token = str(asset.get("token", "") or "")
    name = str(asset.get("name", "") or "")

    if kind in {"image", "image_raw_key"}:
        ext = guess_ext(name, ".png")
        prefix = "image_raw" if kind == "image_raw_key" else "image"
        filename = sanitize_filename(f"{prefix}_{token}{ext}")
    elif kind == "board":
        filename = sanitize_filename(f"board_{token}.png")
    elif kind == "mindnote":
        filename = sanitize_filename(f"mindnote_{token}.png")
    else:
        filename = sanitize_filename(f"asset_{token}.bin")

    target = output_dir / filename
    return {
        "asset_index": idx,
        "kind": kind,
        "token": token,
        "name": name,
        "section_path": asset.get("section_path", ""),
        "source": asset.get("source", "block"),
        "source_block_ids": asset.get("source_block_ids", []),
        "path": str(target),
        "target": target,
        "status": "pending",
        "error": "",
        "error_type": "",
        "failure_category": "",
        "use_user_token": None,
        "attempts": [],
        "guidance": [],
    }


def _download_single(
    client: Any,
    task: dict[str, Any],
    prefer_user_token: bool,
    retries: int,
) -> dict[str, Any]:
    """Download a single asset (thread-safe). Returns result dict."""
    result = {k: v for k, v in task.items() if k != "target"}
    target: Path = task["target"]

    if target.exists():
        result["status"] = "cached"
        return result

    outcome = attempt_download_asset(
        client=client,
        kind=task["kind"],
        token=task["token"],
        target=target,
        prefer_user_token=prefer_user_token,
        retries=retries,
    )
    result.update(outcome)
    return result


_DEFAULT_DOWNLOAD_WORKERS = 8


def download_assets(
    client: Any,
    assets: list[dict[str, Any]],
    output_dir: Path,
    prefer_user_token: bool,
    retries: int,
    max_workers: int = _DEFAULT_DOWNLOAD_WORKERS,
) -> list[dict[str, Any]]:
    output_dir.mkdir(parents=True, exist_ok=True)

    tasks = [_prepare_asset_task(idx, asset, output_dir) for idx, asset in enumerate(assets, start=1)]

    if not tasks:
        return []

    workers = min(max_workers, len(tasks))
    results: list[dict[str, Any]] = [{}] * len(tasks)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        future_to_idx = {
            pool.submit(_download_single, client, task, prefer_user_token, retries): i
            for i, task in enumerate(tasks)
        }
        for future in as_completed(future_to_idx):
            idx = future_to_idx[future]
            results[idx] = future.result()

    return results
