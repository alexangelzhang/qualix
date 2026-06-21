"""Locate EUT-scoped evidence candidates in code repositories."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def cmd_locate(args: argparse.Namespace, output_dir: Path) -> int:
    from qualix.commands.cli_json import cli_envelope, cli_json_mode, print_cli_json
    from qualix.locator import RipgrepLocator

    json_mode = cli_json_mode(args)
    project_id: str = args.project_id
    raw_code_repo = getattr(args, "code_repo", "") or ""
    code_repos = [p.strip() for p in raw_code_repo.split(",") if p.strip()]
    errors: list[str] = []

    if not code_repos:
        errors.append("missing --code-repo; locate is read-only and requires at least one repository path")
    for repo in code_repos:
        if not Path(repo).expanduser().is_dir():
            errors.append(f"code repo is not a directory: {repo}")
    if not (getattr(args, "query", "") or "").strip():
        errors.append("missing --query")

    if errors:
        if json_mode:
            print_cli_json(
                cli_envelope(
                    command="locate",
                    project_id=project_id,
                    success=False,
                    exit_code=2,
                    phase_id=getattr(args, "phase", ""),
                    errors=errors,
                )
            )
        else:
            for error in errors:
                print(f"  ERROR: {error}", file=sys.stderr)
        return 2

    citations = RipgrepLocator().locate(
        query=args.query,
        code_repos=code_repos,
        phase=args.phase,
        se_id=getattr(args, "se_id", "") or "",
        eut_id=args.eut_id,
        limit=max(getattr(args, "limit", 10), 0),
        context_lines=max(getattr(args, "context_lines", 2), 0),
    )

    citation_payload = [c.model_dump(mode="json") for c in citations]
    if json_mode:
        print_cli_json(
            cli_envelope(
                command="locate",
                project_id=project_id,
                success=True,
                exit_code=0,
                phase_id=args.phase,
                extra={
                    "locator": "ripgrep",
                    "contract": "candidate_evidence_only",
                    "eut_id": args.eut_id,
                    "se_id": getattr(args, "se_id", "") or "",
                    "citations": citation_payload,
                },
            )
        )
        return 0

    print(f"Evidence candidates for {args.eut_id} ({len(citations)}):")
    for citation in citations:
        print(f"  - {citation.reference()} [{citation.kind}] {citation.reason}")
    return 0
