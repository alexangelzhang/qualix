"""dqg-run: Pipeline 执行入口.

用法:
    dqg-run <project_id> execute <phase>     # 启动 Phase
    dqg-run <project_id> finalize <phase>    # 校验产物并提交 review
    dqg-run <project_id> approve <phase>     # 人工确认通过
    dqg-run <project_id> skip <phase>        # 跳过 Phase
    dqg-run <project_id> status              # 查看状态看板
    dqg-run <project_id> next                # 显示下一步可执行的 Phase
    dqg-run <project_id> log                 # 查看执行记录

Phase ID: Q01-Q07（旧 ID A/A.3/A.5/A.6/B/C/D 仍兼容）
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from dqg.constants import (
    DEFAULT_ADAPTIVE_JUDGE_MODELS,
    DEFAULT_FALLBACK_MODEL,
    DEFAULT_JUDGE_MODEL,
    DEFAULT_PRIMARY_MODEL,
)


def _build_parser() -> argparse.ArgumentParser:
    """构建 CLI 参数解析器."""
    parser = argparse.ArgumentParser(description="研发质量门禁 Pipeline Runner")
    parser.add_argument("project_id", help="项目 ID")
    parser.add_argument("--base-dir", default=".", help="项目根目录")
    parser.add_argument(
        "--profile",
        default=None,
        help="技术栈 profile（默认 java-ddd-tmf）",
    )

    sub = parser.add_subparsers(dest="command", required=True)

    # execute
    p_exec = sub.add_parser("execute", help="启动 Phase")
    p_exec.add_argument("phase", help="Phase ID (Q01-Q07)")
    p_exec.add_argument("--model", "-m", default=None, help="模型名称（自动计算 token budget）")
    p_exec.add_argument("--code-repo", default=None, help="代码仓库路径（Phase C/D 增量分析用）")
    p_exec.add_argument("--base-branch", default="master", help="基线分支（默认 master）")
    p_exec.add_argument("--feature-branch", default="HEAD", help="特性分支（默认 HEAD）")

    # finalize
    p_fin = sub.add_parser("finalize", help="校验产物并提交 review")
    p_fin.add_argument("phase", help="Phase ID")

    # approve
    p_app = sub.add_parser("approve", help="人工确认通过")
    p_app.add_argument("phase", help="Phase ID")
    p_app.add_argument("--comment", "-c", default="", help="审批备注")
    p_app.add_argument("--force", action="store_true", help="Judge 评分不达标时强制通过")

    # skip
    p_skip = sub.add_parser("skip", help="跳过 Phase")
    p_skip.add_argument("phase", help="Phase ID")
    p_skip.add_argument("--comment", "-c", default="", help="跳过原因")

    # reset
    p_reset = sub.add_parser("reset", help="重置 Phase 到 not_started（允许重新执行）")
    p_reset.add_argument("phase", help="Phase ID")
    p_reset.add_argument("--clean", action="store_true", help="直接删除产出物（默认归档到 _archive/）")
    p_reset.add_argument("--cascade", action="store_true", help="级联重置所有下游 Phase")

    # status
    sub.add_parser("status", help="查看状态看板")

    # next
    sub.add_parser("next", help="显示下一步可执行的 Phase")

    # log
    sub.add_parser("log", help="查看执行记录")

    # startup (JSON output for AI)
    sub.add_parser("startup", help="输出 JSON 状态 + 菜单（供 AI 解析）")

    # detail
    p_detail = sub.add_parser("detail", help="展示已完成 Phase 的产物摘要")
    p_detail.add_argument("phase", help="Phase ID")

    # auto
    p_auto = sub.add_parser("auto", help="全自动推进 pipeline（每个 Phase 暂停等 approve）")
    p_auto.add_argument("--model", "-m", default=None, help="模型名称")
    p_auto.add_argument("--skip", nargs="*", default=[], help="跳过指定 Phase（如 Q03）")

    # judge
    p_judge = sub.add_parser("judge", help="查看/触发 Phase 质量评审")
    p_judge.add_argument("phase", help="Phase ID")

    # critique
    p_critique = sub.add_parser("critique", help="Self-Critique: 自我批评并修正")
    p_critique.add_argument("phase", help="Phase ID")

    # preference
    p_pref = sub.add_parser("preference", help="RLAIF: 比较 v1 vs v2 偏好")
    p_pref.add_argument("phase", help="Phase ID")

    # golden
    p_golden = sub.add_parser("golden", help="Golden sample: 保存/对比标杆")
    p_golden.add_argument("phase", help="Phase ID")
    p_golden.add_argument("--save", action="store_true", help="将当前产物保存为 golden sample")

    # orchestrate
    p_orch = sub.add_parser("orchestrate", help="Multi-Agent: 生成 Worker/Judge/Critique prompt")
    p_orch.add_argument("phase", help="Phase ID")
    p_orch.add_argument("--plan", action="store_true", help="显示执行计划")

    # agent-run
    p_arun = sub.add_parser("agent-run", help="Multi-Agent Phase 2: 真独立 Agent 执行")
    p_arun.add_argument("phase", help="Phase ID")
    p_arun.add_argument("--primary", default=DEFAULT_PRIMARY_MODEL, help="主模型")
    p_arun.add_argument("--fallback", default=DEFAULT_FALLBACK_MODEL, help="备用模型")
    p_arun.add_argument("--judge-model", default=DEFAULT_JUDGE_MODEL, help="Judge 模型")

    # adaptive
    p_adapt = sub.add_parser("adaptive", help="Multi-Agent Phase 3: 自适应循环 + 多 Judge 投票")
    p_adapt.add_argument("phase", help="Phase ID")
    p_adapt.add_argument("--primary", default=DEFAULT_PRIMARY_MODEL, help="Worker 模型")
    p_adapt.add_argument("--fallback", default=DEFAULT_FALLBACK_MODEL, help="备用模型")
    p_adapt.add_argument(
        "--judge-models", default=",".join(DEFAULT_ADAPTIVE_JUDGE_MODELS), help="Judge 模型列表（逗号分隔）"
    )
    p_adapt.add_argument("--max-iter", type=int, default=3, help="最大迭代次数")
    p_adapt.add_argument("--threshold", type=float, default=3.5, help="通过阈值（1-5）")

    # dag
    p_dag = sub.add_parser("dag", help="DAG 并行调度: 全自动推进所有可执行 Phase")
    p_dag.add_argument("--skip", nargs="*", default=[], help="跳过指定 Phase（如 Q03 Q05）")
    p_dag.add_argument("--max-parallel", type=int, default=3, help="最大并行数（默认 3）")
    p_dag.add_argument(
        "--mode", choices=["agent-run", "adaptive"], default="adaptive", help="执行模式（默认 adaptive）"
    )
    p_dag.add_argument("--primary", default=DEFAULT_PRIMARY_MODEL, help="Worker 模型")
    p_dag.add_argument("--fallback", default=DEFAULT_FALLBACK_MODEL, help="备用模型")
    p_dag.add_argument("--plan", action="store_true", help="只显示执行计划，不执行")

    # wiki-compile
    sub.add_parser("wiki-compile", help="从历史提取并编译生成该项目的初始 LLM-Wiki")

    # wiki-lint
    sub.add_parser("wiki-lint", help="启动清理智能体：打扫并梳理当前的 .dqg-wiki 全景拓扑")

    # init
    sub.add_parser("init", help="一键初始化项目（创建目录结构、state.json、version.json）")

    # doctor
    sub.add_parser("doctor", help="环境健康检查（Python/依赖/脚本/profiles/飞书 token）")

    # update
    sub.add_parser("update", help="更新 DQG 到最新版本（git pull + version.json 同步）")

    # version
    sub.add_parser("version", help="显示 DQG 版本号")

    # --- ops: metrics / observe / regression ---

    # metrics
    sub.add_parser("metrics", help="度量自动采集（原 dqg-metrics）")

    # observe
    p_observe = sub.add_parser("observe", help="可观测性报告/告警（原 dqg-observe）")
    p_observe.add_argument("observe_action", nargs="?", default="report", choices=["report", "daily"])
    p_observe.add_argument("--period", choices=["daily", "weekly"], default="daily")
    p_observe.add_argument("--date", default=None, help="锚点日期 YYYY-MM-DD")
    p_observe.add_argument("--project", default=None, help="项目过滤")
    p_observe.add_argument("--phase", default=None, help="Phase 过滤")
    p_observe.add_argument("--block-spike-ratio", type=float, default=2.0, help="BLOCK 激增阈值倍数")
    p_observe.add_argument("--phase-failure-threshold", type=float, default=0.5, help="Phase 失败率阈值")

    # regression
    p_regr = sub.add_parser("regression", help="回归测试（原 dqg-regression）")
    p_regr.add_argument("regression_action", nargs="?", default="run", choices=["run", "trend"])
    p_regr.add_argument("--case", dest="case_id", default=None, help="只运行指定 case")
    p_regr.add_argument("--period", choices=["weekly"], default="weekly")
    p_regr.add_argument("--output-dir", dest="regression_output_dir", default=None, help="输出目录")

    return parser


def _dispatch(cmd: str) -> callable:
    """按需导入并返回命令处理函数."""
    if cmd in ("execute", "finalize", "approve", "skip", "reset", "auto"):
        from dqg.commands.phase import cmd_approve, cmd_auto, cmd_execute, cmd_finalize, cmd_reset, cmd_skip

        return {
            "execute": cmd_execute,
            "finalize": cmd_finalize,
            "approve": cmd_approve,
            "skip": cmd_skip,
            "reset": cmd_reset,
            "auto": cmd_auto,
        }[cmd]

    if cmd in ("status", "next", "log", "detail"):
        from dqg.commands.query import cmd_detail, cmd_log, cmd_next, cmd_status

        return {"status": cmd_status, "next": cmd_next, "log": cmd_log, "detail": cmd_detail}[cmd]

    if cmd == "startup":
        from dqg.commands.startup_fast import cmd_startup

        return cmd_startup

    if cmd in ("judge", "critique", "preference", "golden"):
        from dqg.commands.review import cmd_critique, cmd_golden, cmd_judge, cmd_preference

        return {"judge": cmd_judge, "critique": cmd_critique, "preference": cmd_preference, "golden": cmd_golden}[cmd]

    if cmd in ("orchestrate", "agent-run", "adaptive", "dag"):
        from dqg.commands.agents import cmd_adaptive, cmd_agent_run, cmd_dag, cmd_orchestrate

        return {"orchestrate": cmd_orchestrate, "agent-run": cmd_agent_run, "adaptive": cmd_adaptive, "dag": cmd_dag}[
            cmd
        ]

    if cmd in ("wiki-compile", "wiki-lint"):
        from dqg.commands.wiki import cmd_wiki_compile, cmd_wiki_lint

        return {"wiki-compile": cmd_wiki_compile, "wiki-lint": cmd_wiki_lint}[cmd]

    if cmd in ("init", "doctor", "update", "version"):
        from dqg.commands.setup import cmd_doctor, cmd_init, cmd_update, cmd_version

        return {"init": cmd_init, "doctor": cmd_doctor, "update": cmd_update, "version": cmd_version}[cmd]

    if cmd in ("metrics", "observe", "regression"):
        from dqg.commands.ops import cmd_metrics, cmd_observe, cmd_regression

        return {"metrics": cmd_metrics, "observe": cmd_observe, "regression": cmd_regression}[cmd]

    return None


def _resolve_output_dir(base_dir: str) -> Path:
    """解析 output 目录，worktree 环境自动回退到主仓库."""
    base = Path(base_dir).resolve()
    try:
        r_dir = subprocess.run(
            ["git", "rev-parse", "--git-dir"],
            capture_output=True,
            text=True,
            cwd=str(base),
        )
        r_common = subprocess.run(
            ["git", "rev-parse", "--git-common-dir"],
            capture_output=True,
            text=True,
            cwd=str(base),
        )
        if r_dir.returncode == 0 and r_common.returncode == 0:
            git_dir = (base / r_dir.stdout.strip()).resolve()
            git_common = (base / r_common.stdout.strip()).resolve()
            if git_dir != git_common:
                # worktree: git_dir 指向 worktree 的 .git，git_common 指向主仓库的 .git
                main_repo_root = git_common.parent
                # base_dir 相对于 worktree toplevel 的偏移量也要保留
                r_toplevel = subprocess.run(
                    ["git", "rev-parse", "--show-toplevel"],
                    capture_output=True,
                    text=True,
                    cwd=str(base),
                )
                if r_toplevel.returncode == 0:
                    wt_root = Path(r_toplevel.stdout.strip()).resolve()
                    rel = base.relative_to(wt_root)
                    target = main_repo_root / rel / "output"
                else:
                    target = main_repo_root / "output"
                print(f"[worktree] output 重定向到主仓库: {target}", file=sys.stderr)
                return target
    except (FileNotFoundError, ValueError):
        pass
    return base / "output"


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()
    output_dir = _resolve_output_dir(args.base_dir)

    handler = _dispatch(args.command)
    if not handler:
        print(f"未知命令: {args.command}", file=sys.stderr)
        return 1

    return handler(args, output_dir)
