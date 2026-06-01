#!/usr/bin/env python3
"""Compare LLMs on the Qualix Q06 audit task.

Usage:
    python run_benchmark.py --model anthropic/claude-sonnet-4-6
    python run_benchmark.py --model openai/gpt-4o
    python run_benchmark.py --model google/gemini-2.5-pro

The script reads the case inputs, asks the model to produce structured Q06
findings as JSON, then compares against the golden findings and writes a
report to `results/`. It does not depend on Qualix internal modules — only
the official SDK for the provider you target.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

THIS_DIR = Path(__file__).resolve().parent

# --------------------------------------------------------------------------- #
# Prompt template
# --------------------------------------------------------------------------- #

Q06_SYSTEM_PROMPT = """You are a senior test-quality reviewer performing a Q06 audit.

Your job: given a PRD, source code, a test suite, and a list of semantic
expectations (SE) extracted from the PRD, identify which SEs are NOT
adequately covered by the test suite — even if the tests pass.

You must report concrete, actionable findings. Vague restatements ("tests
should cover idempotency") are not acceptable. Each finding must cite a
specific value, line, or behavior that is missing or wrong.

Return STRICT JSON only. No prose, no markdown, no code fences.
"""

Q06_USER_PROMPT_TEMPLATE = """## PRD
```
{prd}
```

## Source code
```
{source}
```

## Test suite
```
{tests}
```

## Semantic expectations to check
{se_list}

## Task
Produce a JSON object with this exact shape:

{{
  "findings": [
    {{
      "id": "F-1",
      "severity": "high" | "medium" | "low",
      "type": "<short snake_case category, e.g. boundary_missing, idempotency_uncovered, schema_incomplete, rejection_uncovered>",
      "related_se": ["SE-XXX", ...],
      "description": "<one or two sentences describing what is missing>",
      "evidence": "<concrete pointer: line, value, or behavior in the test or source code>"
    }}
  ]
}}

Rules:
- Every finding MUST cite at least one related SE id from the list above, OR
  set related_se to [] if the gap is real but does not map to any listed SE.
- Do NOT invent SE ids that are not in the list.
- Output ONLY the JSON object. Nothing before, nothing after.
"""

# --------------------------------------------------------------------------- #
# Provider dispatch
# --------------------------------------------------------------------------- #


def call_anthropic(model: str, system: str, user: str, temperature: float) -> str:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not set. Export it before running:\n"
            "    export ANTHROPIC_API_KEY=sk-ant-..."
        )
    try:
        import anthropic  # type: ignore
    except ImportError as exc:
        raise RuntimeError(
            "The `anthropic` package is not installed. Install it with:\n"
            "    pip install anthropic"
        ) from exc

    client = anthropic.Anthropic(api_key=api_key)
    resp = client.messages.create(
        model=model,
        max_tokens=4096,
        temperature=temperature,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    parts: list[str] = []
    for block in resp.content:
        text = getattr(block, "text", None)
        if text:
            parts.append(text)
    return "".join(parts)


def call_openai(model: str, system: str, user: str, temperature: float) -> str:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "OPENAI_API_KEY is not set. Export it before running:\n"
            "    export OPENAI_API_KEY=sk-..."
        )
    try:
        from openai import OpenAI  # type: ignore
    except ImportError as exc:
        raise RuntimeError(
            "The `openai` package is not installed. Install it with:\n"
            "    pip install openai"
        ) from exc

    client = OpenAI(api_key=api_key)
    resp = client.chat.completions.create(
        model=model,
        temperature=temperature,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        response_format={"type": "json_object"},
    )
    return resp.choices[0].message.content or ""


def call_google(model: str, system: str, user: str, temperature: float) -> str:
    api_key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "GOOGLE_API_KEY (or GEMINI_API_KEY) is not set. Export it before running:\n"
            "    export GOOGLE_API_KEY=..."
        )
    try:
        import google.generativeai as genai  # type: ignore
    except ImportError as exc:
        raise RuntimeError(
            "The `google-generativeai` package is not installed. Install it with:\n"
            "    pip install google-generativeai"
        ) from exc

    genai.configure(api_key=api_key)
    model_obj = genai.GenerativeModel(
        model_name=model,
        system_instruction=system,
    )
    resp = model_obj.generate_content(
        user,
        generation_config={
            "temperature": temperature,
            "response_mime_type": "application/json",
        },
    )
    return resp.text or ""


PROVIDERS = {
    "anthropic": call_anthropic,
    "openai": call_openai,
    "google": call_google,
}


def dispatch(model_spec: str, system: str, user: str, temperature: float) -> str:
    if "/" not in model_spec:
        raise ValueError(
            f"--model must be in the form provider/model, got: {model_spec!r}"
        )
    provider, model = model_spec.split("/", 1)
    if provider not in PROVIDERS:
        raise ValueError(
            f"Unknown provider {provider!r}. Supported: {sorted(PROVIDERS)}"
        )
    return PROVIDERS[provider](model, system, user, temperature)


# --------------------------------------------------------------------------- #
# Case loading
# --------------------------------------------------------------------------- #


def load_case(case_id: str) -> dict[str, Any]:
    case_dir = THIS_DIR / case_id
    if not case_dir.is_dir():
        raise FileNotFoundError(f"Case directory not found: {case_dir}")
    inputs = case_dir / "inputs"
    golden = case_dir / "golden" / "findings.json"
    return {
        "case_id": case_id,
        "case_dir": case_dir,
        "prd": (inputs / "prd.md").read_text(encoding="utf-8"),
        "source": (inputs / "source_code.py").read_text(encoding="utf-8"),
        "tests": (inputs / "test_code.py").read_text(encoding="utf-8"),
        "golden": json.loads(golden.read_text(encoding="utf-8")),
    }


def format_se_list(se_index: list[dict[str, str]]) -> str:
    lines = []
    for se in se_index:
        lines.append(f"- {se['se_id']}: {se['description']}")
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Output parsing + scoring
# --------------------------------------------------------------------------- #


def extract_json(text: str) -> dict[str, Any]:
    """Tolerant JSON extractor: strips markdown fences if a model adds them."""
    stripped = text.strip()
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", stripped, re.DOTALL)
    if fence:
        stripped = fence.group(1).strip()
    return json.loads(stripped)


def normalize_finding(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(raw.get("id", "")),
        "severity": str(raw.get("severity", "")).lower(),
        "type": str(raw.get("type", "")).lower(),
        "related_se": [str(s).upper() for s in raw.get("related_se", []) or []],
        "description": str(raw.get("description", "")),
        "evidence": str(raw.get("evidence", "")),
    }


def is_match(model_finding: dict[str, Any], golden_finding: dict[str, Any]) -> bool:
    """Type-equality OR SE-overlap, per scoring_notes in the golden file."""
    if (
        model_finding["type"]
        and model_finding["type"] == golden_finding.get("type", "").lower()
    ):
        return True
    model_ses = set(model_finding["related_se"])
    golden_ses = set(golden_finding.get("related_se", []) or [])
    return bool(model_ses and golden_ses and (model_ses & golden_ses))


def score(
    raw_findings: list[dict[str, Any]], golden: dict[str, Any]
) -> dict[str, Any]:
    findings = [normalize_finding(f) for f in raw_findings]
    golden_findings = golden["findings"]

    matched = []
    used_golden_ids: set[str] = set()
    extra: list[dict[str, Any]] = []

    for mf in findings:
        hit = None
        for gf in golden_findings:
            if gf["id"] in used_golden_ids:
                continue
            if is_match(mf, gf):
                hit = gf
                used_golden_ids.add(gf["id"])
                break
        if hit:
            matched.append({"model": mf, "golden_id": hit["id"]})
        else:
            extra.append(mf)

    missed = [gf for gf in golden_findings if gf["id"] not in used_golden_ids]

    tp = len(matched)
    total_reports = len(findings)
    total_golden = len(golden_findings)
    precision = tp / total_reports if total_reports else 0.0
    recall = tp / total_golden if total_golden else 0.0

    return {
        "matched": matched,
        "missed_golden": missed,
        "extra": extra,
        "scores": {
            "true_positives": tp,
            "total_reports": total_reports,
            "total_golden": total_golden,
            "precision": round(precision, 3),
            "recall": round(recall, 3),
        },
    }


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #


def build_user_prompt(case: dict[str, Any]) -> str:
    return Q06_USER_PROMPT_TEMPLATE.format(
        prd=case["prd"],
        source=case["source"],
        tests=case["tests"],
        se_list=format_se_list(case["golden"]["se_index"]),
    )


def safe_filename(model_spec: str) -> str:
    return model_spec.replace("/", "-").replace(":", "-")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--model",
        required=True,
        help="provider/model, e.g. anthropic/claude-sonnet-4-6, openai/gpt-4o, google/gemini-2.5-pro",
    )
    parser.add_argument("--case", default="expense-approval")
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument(
        "--out",
        default=None,
        help="Override output path (default: results/<provider>-<model>-<timestamp>.json)",
    )
    args = parser.parse_args()

    try:
        case = load_case(args.case)
    except FileNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    user_prompt = build_user_prompt(case)
    prompt_hash = hashlib.sha256(
        (Q06_SYSTEM_PROMPT + "\n---\n" + user_prompt).encode("utf-8")
    ).hexdigest()

    print(f"[run_benchmark] model     : {args.model}")
    print(f"[run_benchmark] case      : {args.case}")
    print(f"[run_benchmark] temp      : {args.temperature}")
    print(f"[run_benchmark] prompt sha: {prompt_hash[:12]}...")

    try:
        raw_text = dispatch(args.model, Q06_SYSTEM_PROMPT, user_prompt, args.temperature)
    except RuntimeError as exc:
        print(f"\n[run_benchmark] cannot run: {exc}", file=sys.stderr)
        return 3
    except ValueError as exc:
        print(f"\n[run_benchmark] bad arguments: {exc}", file=sys.stderr)
        return 2

    try:
        parsed = extract_json(raw_text)
    except json.JSONDecodeError as exc:
        print(
            f"\n[run_benchmark] model returned non-JSON output ({exc}).\n"
            f"--- raw output (first 1000 chars) ---\n{raw_text[:1000]}",
            file=sys.stderr,
        )
        return 4

    raw_findings = parsed.get("findings") or []
    if not isinstance(raw_findings, list):
        print(
            f"\n[run_benchmark] expected `findings` to be a list, got {type(raw_findings).__name__}",
            file=sys.stderr,
        )
        return 4

    scored = score(raw_findings, case["golden"])

    timestamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    report = {
        "model": args.model,
        "case_id": args.case,
        "timestamp_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "temperature": args.temperature,
        "prompt_hash": f"sha256:{prompt_hash}",
        "raw_findings": [normalize_finding(f) for f in raw_findings],
        **scored,
    }

    if args.out:
        out_path = Path(args.out)
        if not out_path.is_absolute():
            out_path = THIS_DIR / out_path
    else:
        out_path = THIS_DIR / "results" / f"{safe_filename(args.model)}-{timestamp}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    s = scored["scores"]
    print(
        f"\n[run_benchmark] precision={s['precision']} recall={s['recall']} "
        f"tp={s['true_positives']}/{s['total_golden']} reports={s['total_reports']}"
    )
    print(f"[run_benchmark] wrote {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
