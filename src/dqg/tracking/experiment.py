"""自动化 Skill 迭代实验引擎.

借鉴 Karpathy 的 autoresearch：
- 固定 benchmark case 作为评估基准
- Agent 自动修改 skill prompt → 跑 benchmark → judge 打分 → 接受/拒绝
- 实验日志记录每次迭代的 prompt diff、分数、决策

用法:
    dqg experiment <phase> --cycles 10 --benchmark <case_id>
"""

from __future__ import annotations

import hashlib
from datetime import datetime
from pathlib import Path
from types import MappingProxyType
from typing import Any, Final

from dqg.constants import BUG_CASE_RELEVANCE_SEED_LIMIT
from dqg.core.state_machine import PHASE_DEFS
from dqg.json_utils import load_json
from dqg.services.phase_service import read_relevance_excerpt
from dqg.store import get_experiment_summary, insert_experiment, query_experiments
from dqg.tracking.case_selector import render_relevant_cases_for_prompt

# Phase → skill 文件映射
_PHASE_SKILL_MAP: Final = MappingProxyType(
    {
        "Q01": "skills/requirement-structuring/SKILL.md",
        "Q04": "skills/tech-coverage-audit.md",
        "Q03": "skills/tech-quality-review.md",
        "Q06": "skills/unit-test-audit.md",
        "Q07": "skills/code-review.md",
    }
)


def _hash_content(content: str) -> str:
    return hashlib.sha256(content.encode()).hexdigest()[:12]


def generate_experiment_prompt(
    output_dir: Path,
    phase_id: str,
    cycle: int,
    benchmark_case: str = "",
    max_history: int = 5,
) -> str | None:
    """生成实验 prompt，指导 agent 修改 skill 并评估.

    Returns:
        实验 prompt 文本
    """
    phase_def = PHASE_DEFS.get(phase_id)
    if not phase_def:
        return None

    skill_file = _PHASE_SKILL_MAP.get(phase_id)
    if not skill_file:
        return None

    skill_path = Path(skill_file)
    if not skill_path.exists():
        return None

    current_content = skill_path.read_text(encoding="utf-8")
    current_hash = _hash_content(current_content)
    relevance_seed = read_relevance_excerpt(skill_path, BUG_CASE_RELEVANCE_SEED_LIMIT)

    # 获取历史实验记录
    history = query_experiments(output_dir, skill_file=skill_file, limit=max_history)
    rejected_history = [h for h in history if not h.get("accepted")]

    # 获取 bug 案例库中该 Phase 的相关案例
    bug_cases_md = render_relevant_cases_for_prompt(phase_id, relevance_seed, max_cases=8)

    lines = [
        f"# Skill 迭代实验 — Phase {phase_id} (Cycle {cycle})",
        "",
        f"你是一个 skill prompt 优化专家。你的任务是改进 `{skill_file}` 的规则，",
        "使其在 benchmark 上获得更高的 judge 分数。",
        "",
        "## 实验规则",
        "",
        f"1. 只修改 `{skill_file}` 这一个文件，不动其他文件",
        "2. 每次只做一个有针对性的改动（不要大规模重写）",
        "3. 改动必须基于证据（bug 案例、历史实验结果）",
        "4. 改完后跑 benchmark 评估，用 judge 打分",
        "5. 分数提升 → 接受改动；分数下降或持平 → 回滚",
        "",
        "## 当前 Skill 信息",
        "",
        f"- 文件: `{skill_file}`",
        f"- 内容 hash: `{current_hash}`",
        f"- 长度: {len(current_content)} 字符",
        "",
    ]

    # 历史实验
    if history:
        lines.extend(
            [
                "## 历史实验记录",
                "",
                "| Cycle | Score | Delta | 结果 | 原因 |",
                "|-------|-------|-------|------|------|",
            ]
        )
        for h in history:
            accepted = "接受" if h.get("accepted") else "拒绝"
            score = h.get("judge_score", "?")
            delta = h.get("delta", 0)
            delta_str = f"+{delta:.1f}" if delta and delta > 0 else f"{delta:.1f}" if delta else "—"
            reason = h.get("reason", "")[:40]
            lines.append(f"| {h.get('cycle', '?')} | {score} | {delta_str} | {accepted} | {reason} |")
        lines.append("")

        if rejected_history:
            lines.extend(
                [
                    "### 失败的改动（避免重复）",
                    "",
                ]
            )
            for h in rejected_history[:3]:
                diff = h.get("prompt_diff", "")[:200]
                lines.append(f"- Cycle {h.get('cycle')}: {h.get('reason', '')} (diff: {diff}...)")
            lines.append("")

    # Bug 案例作为改进方向
    if bug_cases_md:
        lines.extend(
            [
                "## 待解决的 Bug 案例（改进方向）",
                "",
                bug_cases_md,
                "",
            ]
        )

    exp_dir = f"output/.dqg/experiments/cycle_{cycle:03d}"

    # Benchmark 说明
    lines.extend(
        [
            "## 实验沙箱",
            "",
            f"**重要：不要直接修改原文件 `{skill_file}`！**",
            "",
            f"实验在沙箱目录 `{exp_dir}/` 中进行：",
            f"- 原始副本: `{exp_dir}/{Path(skill_file).name}`（从原文件复制）",
            f"- 修改后版本: `{exp_dir}/{Path(skill_file).name}` （在副本上修改）",
            "",
            "只有实验通过人工确认后，才会合并到原文件。",
            "",
            "## 实验步骤",
            "",
            "### Step 1: 准备沙箱",
            "```bash",
            f"mkdir -p {exp_dir}",
            f"cp {skill_file} {exp_dir}/",
            "```",
            "",
            "### Step 2: 分析改进方向",
            f"读取 `{exp_dir}/{Path(skill_file).name}`，结合上面的 bug 案例和历史实验，",
            "选择一个具体的改进点。优先修复高频 bug 模式。",
            "",
            "### Step 3: 修改 Skill（在沙箱中）",
            f"编辑 `{exp_dir}/{Path(skill_file).name}`，做一个有针对性的改动。",
            f"原文件 `{skill_file}` 保持不变。",
            "",
            "### Step 4: 评估",
        ]
    )

    if benchmark_case:
        lines.append(f"使用 benchmark case `{benchmark_case}` 评估改动效果：")
        lines.append(f"1. `dqg-run {benchmark_case} execute {phase_id}`")
        lines.append(f"2. `dqg-run {benchmark_case} finalize {phase_id}`")
        lines.append(f"3. `dqg-run {benchmark_case} judge {phase_id}`")
        lines.append("4. 读取 `_judge_result.json` 获取分数")
    else:
        lines.append("使用 judge 评估改动效果：")
        lines.append(f"1. 对最近的项目执行 `dqg-run <project> judge {phase_id}`")
        lines.append("2. 读取 `_judge_result.json` 获取分数")

    lines.extend(
        [
            "",
            "### Step 5: 决策",
            "",
            "将实验结果记录到以下 JSON 文件：",
            "",
            f"`output/.dqg/experiment_{phase_id.replace('.', '')}_{cycle:03d}.json`",
            "",
            "```json",
            "{",
            f'  "experiment_id": "exp-{phase_id.replace(".", "")}-{cycle:03d}",',
            f'  "skill_file": "{skill_file}",',
            f'  "phase_id": "{phase_id}",',
            f'  "cycle": {cycle},',
            f'  "benchmark_case": "{benchmark_case}",',
            '  "prompt_diff": "改动的简要描述",',
            '  "prompt_hash": "改动后的 hash",',
            '  "baseline_score": null,',
            '  "judge_score": null,',
            '  "delta": null,',
            '  "accepted": false,',
            '  "reason": "接受/拒绝的原因",',
            f'  "started_at": "{datetime.now().isoformat()}",',
            '  "finished_at": null',
            "}",
            "```",
            "",
            "**决策规则：**",
            "- `judge_score > baseline_score` → 标记 `accepted: true`",
            "- `judge_score <= baseline_score` → 标记 `accepted: false`",
            "- 无论接受还是拒绝，都要填写 `reason`",
            "",
            "### Step 6: 合并（仅当 accepted=true 且人工确认后）",
            "",
            "**不要自动合并！** 等人工确认后执行：",
            "```bash",
            f"cp {exp_dir}/{Path(skill_file).name} {skill_file}",
            "```",
        ]
    )

    return "\n".join(lines)


def write_experiment_prompt(
    output_dir: Path,
    phase_id: str,
    cycle: int,
    benchmark_case: str = "",
) -> Path | None:
    """生成实验 prompt 并写入."""
    prompt = generate_experiment_prompt(output_dir, phase_id, cycle, benchmark_case)
    if not prompt:
        return None

    dqg_dir = output_dir / ".dqg"
    dqg_dir.mkdir(parents=True, exist_ok=True)
    path = dqg_dir / f"experiment_{phase_id.replace('.', '')}_{cycle:03d}_prompt.md"
    path.write_text(prompt, encoding="utf-8")
    return path


def load_experiment_result(
    output_dir: Path,
    phase_id: str,
    cycle: int,
) -> dict[str, Any] | None:
    """加载实验结果 JSON."""
    path = output_dir / ".dqg" / f"experiment_{phase_id.replace('.', '')}_{cycle:03d}.json"
    if not path.exists():
        return None
    return load_json(path)


def persist_experiment_result(
    output_dir: Path,
    phase_id: str,
    cycle: int,
) -> dict[str, Any] | None:
    """读取实验结果并持久化到 SQLite."""
    result = load_experiment_result(output_dir, phase_id, cycle)
    if not result:
        return None

    insert_experiment(output_dir, result)
    return result


def format_experiment_log(output_dir: Path, skill_file: str) -> str:
    """格式化实验日志."""
    summary = get_experiment_summary(output_dir, skill_file)
    experiments = query_experiments(output_dir, skill_file=skill_file, limit=20)

    lines = [
        f"Skill 实验日志 — {skill_file}",
        f"  总实验: {summary['total_experiments']} | "
        f"接受: {summary['accepted_count']} ({summary['acceptance_rate']:.0%}) | "
        f"最高分: {summary['best_score']}",
        "",
    ]

    if experiments:
        lines.append(f"{'Cycle':>5} {'Score':>6} {'Delta':>7} {'Result':>6} {'Reason'}")
        lines.append("-" * 60)
        for e in reversed(experiments):
            accepted = "OK" if e.get("accepted") else "SKIP"
            score = e.get("judge_score", "?")
            delta = e.get("delta")
            delta_str = f"+{delta:.1f}" if delta and delta > 0 else f"{delta:.1f}" if delta else "—"
            reason = e.get("reason", "")[:30]
            lines.append(f"{e.get('cycle', '?'):>5} {score:>6} {delta_str:>7} {accepted:>6} {reason}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI handler
# ---------------------------------------------------------------------------


def cmd_experiment(args, output_dir: Path) -> int:
    """实验命令处理."""
    phase_id = args.phase
    skill_file = _PHASE_SKILL_MAP.get(phase_id)
    if not skill_file:
        print(f"  Phase {phase_id} 不支持自动实验", file=__import__("sys").stderr)
        return 1

    action = getattr(args, "exp_action", "start")

    if action == "log":
        print(format_experiment_log(output_dir, skill_file))
        return 0

    if action == "persist":
        cycle = getattr(args, "cycle", 1)
        result = persist_experiment_result(output_dir, phase_id, cycle)
        if result:
            accepted = "接受" if result.get("accepted") else "拒绝"
            print(f"  实验 Cycle {cycle} 已记录: {accepted} (score: {result.get('judge_score')})")
        else:
            print(f"  未找到 Cycle {cycle} 的实验结果")
        return 0

    # start: 生成实验 prompt
    cycle = getattr(args, "cycle", 1)
    benchmark = getattr(args, "benchmark", "")

    # 自动确定 cycle 号
    existing = query_experiments(output_dir, skill_file=skill_file, limit=1)
    if existing and cycle <= existing[0].get("cycle", 0):
        cycle = existing[0]["cycle"] + 1

    path = write_experiment_prompt(output_dir, phase_id, cycle, benchmark)
    if not path:
        print("  生成实验 prompt 失败", file=__import__("sys").stderr)
        return 1

    print(f"\n  Skill 迭代实验 — Phase {phase_id}, Cycle {cycle}")
    print(f"  Skill: {skill_file}")
    print(f"  实验 prompt: {path}")
    print("\n  请用 AI IDE 读取该文件执行实验")
    print(f"  完成后: dqg experiment {phase_id} persist --cycle {cycle}")
    print(f"  查看日志: dqg experiment {phase_id} log")
    return 0
