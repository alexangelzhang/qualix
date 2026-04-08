#!/usr/bin/env python3
"""迁移 output 目录到新结构.

将每个 phase 目录下的文件分类到：
  - ingest/     飞书 ingest 产物
  - _internal/  过程文件（_ 开头）
  - 根目录      正式产物（保持不动）

用法:
  python3 scripts/migrate_output_structure.py [--dry-run] [output_dir]

默认 output_dir 为 ./output
"""

import argparse
import shutil
import sys
from pathlib import Path

INGEST_FILES = {
    "ingest.json",
    "plain_text.txt",
    "plain_text_summary.md",
    "plain_text_v1.txt",
    "blocks.raw.json",
    "asset_manifest.json",
    "aggregate_ingest.json",
    "aggregate_plain_text.txt",
    "dependency_graph.json",
}

INGEST_DIRS = {"assets", "docs"}

# 正式产物不移动
FORMAL_FILES = {
    "phase_a_report.md",
    "phase_a_structured.json",
    "tech_design_coverage_review.md",
    "phase_a5_structured.json",
    "tech_design_quality_review.md",
    "phase_a6_structured.json",
    "eut_matrix.md",
    "phase_b_structured.json",
    "ut_audit_report.md",
    "phase_c_structured.json",
    "review_report.md",
    "phase_d_structured.json",
    "tech_design.md",
    "image_semantics.md",
    "image_semantics.json",
}

PHASE_DIRS = {"phaseA", "phaseA5", "phaseA6", "phaseB", "phaseC", "phaseD"}


def is_phase_dir(path: Path) -> bool:
    """判断是否是 phase 目录（支持带项目名前缀的旧格式）."""
    name = path.name
    for pd in PHASE_DIRS:
        if name == pd or name.endswith(f"_{pd}"):
            return True
    return False


def migrate_phase_dir(phase_dir: Path, dry_run: bool) -> int:
    """迁移单个 phase 目录，返回移动文件数."""
    moved = 0
    ingest_subdir = phase_dir / "ingest"
    internal_subdir = phase_dir / "_internal"

    for item in sorted(phase_dir.iterdir()):
        name = item.name

        # 跳过已经是子目录的
        if name in ("ingest", "_internal"):
            continue

        if item.is_dir():
            if name in INGEST_DIRS:
                dest = ingest_subdir / name
                print(f"  [DIR ] {item} → {dest}")
                if not dry_run:
                    ingest_subdir.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(item), str(dest))
                moved += 1
        elif item.is_file():
            if name in FORMAL_FILES:
                continue  # 正式产物不动
            elif name in INGEST_FILES:
                dest = ingest_subdir / name
                print(f"  [INGEST] {item.name} → ingest/{name}")
                if not dry_run:
                    ingest_subdir.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(item), str(dest))
                moved += 1
            elif name.startswith("_"):
                dest = internal_subdir / name
                print(f"  [INTERNAL] {item.name} → _internal/{name}")
                if not dry_run:
                    internal_subdir.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(item), str(dest))
                moved += 1
            else:
                print(f"  [SKIP] {item.name} (未分类，保持原位)")

    return moved


def migrate_output(output_dir: Path, dry_run: bool) -> None:
    if not output_dir.exists():
        print(f"ERROR: output 目录不存在: {output_dir}")
        sys.exit(1)

    total_moved = 0
    for project_dir in sorted(output_dir.iterdir()):
        if not project_dir.is_dir() or project_dir.name.startswith("."):
            continue
        for phase_dir in sorted(project_dir.iterdir()):
            if not phase_dir.is_dir():
                continue
            if not is_phase_dir(phase_dir):
                continue
            print(f"\n{phase_dir.relative_to(output_dir)}/")
            moved = migrate_phase_dir(phase_dir, dry_run)
            total_moved += moved
            if moved == 0:
                print("  (已是新结构，无需迁移)")

    print(f"\n{'[DRY RUN] ' if dry_run else ''}共移动 {total_moved} 个文件/目录")


def main():
    parser = argparse.ArgumentParser(description="迁移 output 目录到新结构")
    parser.add_argument("output_dir", nargs="?", default="output", help="output 目录路径（默认 ./output）")
    parser.add_argument("--dry-run", action="store_true", help="只打印将要移动的文件，不实际执行")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    if args.dry_run:
        print("=== DRY RUN 模式，不实际移动文件 ===\n")

    migrate_output(output_dir, args.dry_run)


if __name__ == "__main__":
    main()
