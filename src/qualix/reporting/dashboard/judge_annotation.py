"""Judge result annotation UI — label judge issues as correct / over-strict / missed."""

from __future__ import annotations

import datetime
import json
from pathlib import Path
from typing import Any

import streamlit as st

from qualix.constants import PHASE_DIR_MAP
from qualix.json_utils import load_json
from qualix.log import get_logger

from .cache import _cached_projects
from .constants import OUTPUT_DIR

log = get_logger(__name__)

_ANNOTATION_FILENAME = "_judge_annotations.jsonl"


def _load_judge_results(output_dir: Path) -> list[dict[str, Any]]:
    results = []
    for project_dir in sorted(output_dir.iterdir()):
        if not project_dir.is_dir():
            continue
        for phase_id, phase_suffix in PHASE_DIR_MAP.items():
            internal = project_dir / phase_suffix / "_internal"
            judge_path = internal / "_judge_result.json"
            if not judge_path.exists():
                judge_path = project_dir / phase_suffix / "_judge_result.json"
            if not judge_path.exists():
                continue
            try:
                data = load_json(judge_path)
                if data is None:
                    continue
                results.append(
                    {
                        "project": project_dir.name,
                        "phase": phase_id,
                        "verdict": data.get("verdict", "—"),
                        "overall_score": data.get("overall_score"),
                        "issues": data.get("issues", []),
                        "judged_at": data.get("judged_at", ""),
                        "_path": str(judge_path),
                    }
                )
            except Exception:
                log.debug("Failed to load judge result %s", judge_path, exc_info=True)
    return results


def _load_all_annotations(output_dir: Path) -> dict[str, str]:
    annotations: dict[str, str] = {}
    for project_dir in output_dir.iterdir():
        if not project_dir.is_dir():
            continue
        ann_file = project_dir / _ANNOTATION_FILENAME
        if not ann_file.exists():
            continue
        try:
            for line in ann_file.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                obj = json.loads(line)
                if "issue_key" in obj and "label" in obj:
                    annotations[obj["issue_key"]] = obj["label"]
        except Exception:
            log.debug("Failed to read annotations %s", ann_file, exc_info=True)
    return annotations


def _save_annotation(output_dir: Path, project: str, issue_key: str, label: str) -> None:
    ann_file = output_dir / project / _ANNOTATION_FILENAME
    entry = json.dumps(
        {
            "issue_key": issue_key,
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


def _page_judge_annotation() -> None:
    st.header("Judge Annotation")
    st.caption(
        "Label judge issues to measure judge precision over time. "
        "Annotations are stored locally in `_judge_annotations.jsonl` per project."
    )

    projects = _cached_projects()
    if not projects:
        st.info("No project data found.")
        return

    all_results = _load_judge_results(OUTPUT_DIR)
    annotations = _load_all_annotations(OUTPUT_DIR)

    # Summary metrics
    total_issues = sum(len(r["issues"]) for r in all_results)
    labeled = len(annotations)
    unlabeled = total_issues - labeled
    c1, c2, c3 = st.columns(3)
    c1.metric("Total issues", total_issues)
    c2.metric("Labeled", labeled)
    c3.metric("Unlabeled", unlabeled)

    st.divider()

    # Filter
    filter_pid = st.selectbox("Filter by project", ["All", *projects], key="ja_filter")
    show_only_unlabeled = st.checkbox("Show only unlabeled issues", value=True, key="ja_unlabeled")

    for result in all_results:
        if filter_pid != "All" and result["project"] != filter_pid:
            continue
        issues = result.get("issues") or []
        if not issues:
            continue

        project = result["project"]
        phase = result["phase"]
        score = result.get("overall_score")
        score_str = f"{score:.1f}/5" if score is not None else "—"
        ts = result.get("judged_at", "")[:19]

        with st.expander(
            f"{project} / {phase} — {result['verdict']} ({score_str}) — {len(issues)} issues — {ts}",
            expanded=False,
        ):
            for i, issue in enumerate(issues):
                issue_key = f"{project}_{phase}_{i}_{issue.get('dimension','')}"
                existing = annotations.get(issue_key, "")
                if show_only_unlabeled and existing:
                    continue

                dim = issue.get("dimension", "")
                sev = issue.get("severity", "")
                desc = issue.get("description", "")[:200]
                label_badge = f" [{existing}]" if existing else ""

                st.markdown(f"**{dim}** ({sev}){label_badge}: {desc}")

                col1, col2, col3 = st.columns(3)
                with col1:
                    if st.button("✓ Correct", key=f"correct_{issue_key}_{i}"):
                        _save_annotation(OUTPUT_DIR, project, issue_key, "correct")
                        st.success("Labeled as correct")
                with col2:
                    if st.button("⚠ Over-strict", key=f"strict_{issue_key}_{i}"):
                        _save_annotation(OUTPUT_DIR, project, issue_key, "over_strict")
                        st.warning("Labeled as over-strict")
                with col3:
                    if st.button("✗ Missed", key=f"missed_{issue_key}_{i}"):
                        _save_annotation(OUTPUT_DIR, project, issue_key, "missed")
                        st.error("Labeled as missed")

                st.markdown("---")
