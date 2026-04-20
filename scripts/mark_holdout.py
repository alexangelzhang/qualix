#!/usr/bin/env python3
"""批量给 case.json 添加 holdout 字段.

规则：
- 80% 训练集 (holdout: false)，20% 验证集 (holdout: true)
- 每个 phase 目录独立分配，确保每个 phase 至少有 1 个 holdout
- severity=critical 的 case 优先留在训练集
- 使用固定 seed 确保可复现
- 已有 holdout 字段的 case 不重新分配
"""

import json
import random
from collections import defaultdict
from pathlib import Path

CASES_DIR = Path("regression/failure-library/cases")
SEED = 42
HOLDOUT_RATIO = 0.2


def main() -> None:
    random.seed(SEED)

    # 按 phase 目录分组
    by_phase: dict[str, list[Path]] = defaultdict(list)
    for case_file in sorted(CASES_DIR.rglob("case.json")):
        phase_dir = case_file.parent.parent.name  # e.g. phaseA
        by_phase[phase_dir].append(case_file)

    total = 0
    holdout_count = 0
    skipped = 0

    for phase_dir, files in sorted(by_phase.items()):
        # 分离已标记和未标记的 cases
        unmarked: list[tuple[Path, dict]] = []
        already_marked = 0
        for f in files:
            data = json.loads(f.read_text(encoding="utf-8"))
            if "holdout" in data:
                already_marked += 1
                skipped += 1
            else:
                unmarked.append((f, data))

        if not unmarked:
            print(f"  {phase_dir}: {len(files)} cases, all already marked, skipped")
            continue

        # 按 severity 分组：critical 优先留训练集
        critical = [(f, d) for f, d in unmarked if d.get("severity") == "critical"]
        non_critical = [(f, d) for f, d in unmarked if d.get("severity") != "critical"]

        # 计算 holdout 数量（至少 1 个，从 non-critical 中选）
        target_holdout = max(1, int(len(unmarked) * HOLDOUT_RATIO))

        # 从 non-critical 中随机选 holdout
        random.shuffle(non_critical)
        holdout_from_nc = min(target_holdout, len(non_critical))

        # 如果 non-critical 不够，从 critical 中补（但尽量避免）
        holdout_from_crit = max(0, target_holdout - holdout_from_nc)

        phase_holdout = 0
        for i, (f, data) in enumerate(non_critical):
            data["holdout"] = i < holdout_from_nc
            f.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            if data["holdout"]:
                phase_holdout += 1

        random.shuffle(critical)
        for i, (f, data) in enumerate(critical):
            data["holdout"] = i < holdout_from_crit
            f.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            if data["holdout"]:
                phase_holdout += 1

        total += len(unmarked)
        holdout_count += phase_holdout
        print(f"  {phase_dir}: {len(unmarked)} marked ({phase_holdout} holdout, {len(unmarked) - phase_holdout} training), {already_marked} already marked")

    print(f"\nTotal: {total} newly marked, {holdout_count} holdout ({holdout_count/max(total,1):.0%}), {skipped} skipped")


if __name__ == "__main__":
    main()
