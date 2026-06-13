"""Guard Precision Dashboard — independent page for guard FP/FN tracking."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import streamlit as st

from qualix.constants import GUARD_EVENT_FILENAME, PHASE_DIR_MAP
from qualix.log import get_logger

from .constants import OUTPUT_DIR

log = get_logger(__name__)

_FP_ANNOTATION_FILENAME = "_fp_annotations.jsonl"


def _collect_guard_events(output_dir: Path) -> list[dict[str, Any]]:
    """Collect all _rationalization_guard.jsonl events across projects and phases."""
    events: list[dict[str, Any]] = []
    if not output_dir.exists():
        return events
    for project_dir in output_dir.iterdir():
        if not project_dir.is_dir():
            continue
        for phase_suffix in PHASE_DIR_MAP.values():
            internal = project_dir / phase_suffix / "_internal"
            guard_file = internal / GUARD_EVENT_FILENAME
            if not guard_file.exists():
                guard_file = project_dir / phase_suffix / GUARD_EVENT_FILENAME
            if not guard_file.exists():
                continue
            try:
                for line in guard_file.read_text(encoding="utf-8").splitlines():
                    if not line.strip():
                        continue
                    obj = json.loads(line)
                    obj.setdefault("_project", project_dir.name)
                    obj.setdefault("_phase", phase_suffix)
                    events.append(obj)
            except Exception:
                log.debug("Failed to read %s", guard_file, exc_info=True)
    return events


def _load_annotations(output_dir: Path) -> dict[str, str]:
    """Load existing FP/FN annotations keyed by event_id."""
    annotations: dict[str, str] = {}
    for project_dir in output_dir.iterdir():
        if not project_dir.is_dir():
            continue
        ann_file = project_dir / _FP_ANNOTATION_FILENAME
        if not ann_file.exists():
            continue
        try:
            for line in ann_file.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                obj = json.loads(line)
                if "event_id" in obj and "label" in obj:
                    annotations[obj["event_id"]] = obj["label"]
        except Exception:
            log.debug("Failed to read annotations %s", ann_file, exc_info=True)
    return annotations


def _save_annotation(output_dir: Path, project: str, event_id: str, label: str) -> None:
    """Append an annotation entry."""
    import datetime

    ann_file = output_dir / project / _FP_ANNOTATION_FILENAME
    entry = json.dumps(
        {
            "event_id": event_id,
            "label": label,
            "annotated_at": datetime.datetime.now(tz=datetime.UTC).isoformat(),
        },
        ensure_ascii=False,
    )
    try:
        ann_file.parent.mkdir(parents=True, exist_ok=True)
        with ann_file.open("a", encoding="utf-8") as f:
            f.write(entry + "\n")
    except Exception:
        log.warning("Failed to write annotation to %s", ann_file, exc_info=True)


def _page_guard_precision() -> None:
    st.header("Guard Precision")
    st.caption(
        "Track false-positive and false-negative rates for rationalization and overcorrection guards. "
        "Annotate HARD_BLOCK events to build a labeled dataset."
    )

    from qualix.reporting.guard_precision_report import build_guard_precision_summary

    summary = build_guard_precision_summary(OUTPUT_DIR)
    generated_at = summary.get("generated_at", "—")
    files_read = summary.get("guardrail_files_read", 0)
    st.caption(f"Guardrail result files: {files_read} · Generated: {generated_at}")

    # --- Section 1: Summary table ---
    st.subheader("Guard Summary")
    by_guard = summary.get("by_guard") or {}
    if by_guard:
        import pandas as pd

        rows = []
        for guard_name, counts in sorted(by_guard.items()):
            total = counts.get("pass", 0) + counts.get("fail", 0) + counts.get("blocked", 0)
            fail_rate = (counts.get("fail", 0) + counts.get("blocked", 0)) / max(total, 1)
            rows.append(
                {
                    "guard": guard_name,
                    "pass": counts.get("pass", 0),
                    "fail": counts.get("fail", 0),
                    "blocked": counts.get("blocked", 0),
                    "triggered": counts.get("triggered", 0),
                    "fail_rate": f"{fail_rate:.1%}",
                }
            )
        df = pd.DataFrame(rows)
        st.dataframe(df, use_container_width=True, hide_index=True)
    else:
        st.info("No guard data found. Run some phases with a code repository to generate guard events.")

    # --- Section 2: HARD_BLOCK annotation workflow ---
    st.subheader("HARD_BLOCK Annotation")
    st.caption(
        "Label recent HARD_BLOCK events as 'correct_block' (true positive) or "
        "'false_positive' to measure guard precision over time."
    )

    events = _collect_guard_events(OUTPUT_DIR)
    hard_blocks = [e for e in events if e.get("verdict") == "HARD_BLOCK" or e.get("status") == "GUARD_EXHAUSTED"]
    recent_blocks = sorted(hard_blocks, key=lambda e: e.get("timestamp", ""), reverse=True)[:20]

    if not recent_blocks:
        st.info("No HARD_BLOCK events found. Events are written to `_rationalization_guard.jsonl` during phase execution.")
    else:
        annotations = _load_annotations(OUTPUT_DIR)
        for i, event in enumerate(recent_blocks):
            event_id = event.get("event_id", f"evt-{i}")
            project = event.get("_project", "unknown")
            phase = event.get("_phase", "")
            guard_name = event.get("guard_name", event.get("guard", "unknown"))
            ts = event.get("timestamp", "")[:19]
            existing_label = annotations.get(event_id, "")

            label_display = f" [{existing_label}]" if existing_label else ""
            with st.expander(f"{ts} · {project}/{phase} · {guard_name}{label_display}", expanded=False):
                st.json({k: v for k, v in event.items() if not k.startswith("_")})
                col1, col2 = st.columns(2)
                with col1:
                    if st.button("✓ Correct block", key=f"tp_{event_id}_{i}"):
                        _save_annotation(OUTPUT_DIR, project, event_id, "correct_block")
                        st.success("Annotated as correct block")
                with col2:
                    if st.button("✗ False positive", key=f"fp_{event_id}_{i}"):
                        _save_annotation(OUTPUT_DIR, project, event_id, "false_positive")
                        st.warning("Annotated as false positive")

    # --- Section 3: Weekly Markdown report link ---
    st.subheader("Weekly Report")
    from qualix.reporting.guard_precision_report import _guard_precision_doc_path_default

    md_path = _guard_precision_doc_path_default()
    if md_path.is_file():
        with st.expander("View full Markdown report", expanded=False):
            st.markdown(md_path.read_text(encoding="utf-8"))
        st.caption(f"Report path: `{md_path}`")
    else:
        st.info(
            f"No weekly report found at `{md_path}`. "
            "Run `python -m qualix.reporting.guard_precision_report` to generate one."
        )
