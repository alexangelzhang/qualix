"""qualix-run: Pipeline 执行入口.

用法:
    qualix-run <project_id> execute <phase>     # 启动 Phase
    qualix-run <project_id> finalize <phase>    # 校验产物并提交 review
    qualix-run <project_id> approve <phase>     # 人工确认通过
    qualix-run <project_id> skip <phase>        # 跳过 Phase
    qualix-run <project_id> status              # 查看状态看板
    qualix-run <project_id> next                # 显示下一步可执行的 Phase
    qualix-run <project_id> log                 # 查看执行记录
    qualix-run <project_id> spec --phase Q05    # Phase 规范（JSON：schema + contract）

各子命令可追加 --json，stdout 仅输出一条 JSON（execute/finalize/approve/…）。
Phase ID: Q01-Q07（旧 ID A/A.3/A.5/A.6/B/C/D 仍兼容）
"""

from __future__ import annotations

import argparse
import contextlib
import io
import subprocess
import sys
from pathlib import Path
from typing import Any

from qualix.constants import (
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
    p_exec.add_argument("--code-repo", default=None, help="代码仓库路径，多个用逗号分隔（如 /path/a,/path/b）")
    p_exec.add_argument("--base-branch", default="master", help="基线分支（默认 master）")
    p_exec.add_argument("--feature-branch", default="HEAD", help="特性分支（默认 HEAD）")
    p_exec.add_argument(
        "--coverage-report",
        default=None,
        help="JaCoCo XML 报告路径（Q06 用，如 /path/to/jacoco.xml）",
    )

    # finalize
    p_fin = sub.add_parser("finalize", help="校验产物并提交 review")
    p_fin.add_argument("phase", help="Phase ID")
    p_fin.add_argument(
        "--code-repo",
        default=None,
        help="代码仓库路径，多个用逗号分隔（手动模式下用于写入 _inputs.json，启用编译/测试 gate）",
    )
    p_fin.add_argument(
        "--strict-profile-context",
        action="store_true",
        default=False,
        help="严格模式：报告缺少 PROFILE_CONTEXT 时阻断 finalize（默认 WARNING）",
    )

    # approve
    p_app = sub.add_parser("approve", help="人工确认通过")
    p_app.add_argument("phase", help="Phase ID")
    p_app.add_argument("--comment", "-c", default="", help="审批备注")
    p_app.add_argument("--force", action="store_true", help="Judge 评分不达标时强制通过")
    p_app.add_argument(
        "--allow-synthetic-review",
        action="store_true",
        help="允许将 auto-synthesized Judge/Critique 视为有效评审闭环（默认：auto-synthesized 只能辅助，不能作为正式 approve 依据）",
    )

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
    p_judge.add_argument(
        "--replay",
        action="store_true",
        help="重跑 Judge（当前 rubric）并与历史 _judge_iter*.json 对比，检测 harness 漂移",
    )
    p_judge.add_argument("--model", default=None, help="Judge 模型（--replay 时生效）")

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

    # adaptive-override：人工批准某轮 adaptive 迭代
    p_aoverride = sub.add_parser("adaptive-override", help="人工批准 adaptive loop 某轮迭代结果")
    p_aoverride.add_argument("phase", help="Phase ID")
    p_aoverride.add_argument("--approve-iteration", type=int, required=True, dest="approve_iteration", help="批准第 N 轮（从 1 开始）")

    # adaptive-diff：展示 adaptive loop 各轮迭代产物 diff
    p_adiff = sub.add_parser("adaptive-diff", help="展示 adaptive loop 各轮迭代产物的 diff summary")
    p_adiff.add_argument("phase", help="Phase ID")

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
    sub.add_parser("wiki-lint", help="启动清理智能体：打扫并梳理当前的 .qualix-wiki 全景拓扑")

    # init
    sub.add_parser("init", help="一键初始化项目（创建目录结构、state.json、version.json）")

    # doctor
    sub.add_parser("doctor", help="环境健康检查（Python/依赖/脚本/profiles/飞书 token）")

    # update
    sub.add_parser("update", help="更新 Qualix 到最新版本（git pull + version.json 同步）")

    # version
    sub.add_parser("version", help="显示 Qualix 版本号")

    # task
    p_task = sub.add_parser("task", help="Task 管理（list/resume）")
    p_task.add_argument(
        "task_action",
        nargs="?",
        default="list",
        choices=["list", "resume"],
        help="操作（list: 列出 tasks；resume: 查找/显示可恢复 task）",
    )
    p_task.add_argument("task_id", nargs="?", default=None, help="Task ID（resume 指定 task 用）")
    p_task.add_argument(
        "--status",
        choices=["running", "completed", "failed", "all"],
        default="all",
        help="按状态过滤（list 用，默认 all）",
    )
    p_task.add_argument("--limit", type=int, default=20, help="最多返回条数（默认 20）")

    # --- ops: metrics / observe / regression ---

    # metrics
    sub.add_parser("metrics", help="度量自动采集（原 qualix-metrics）")

    # observe
    p_observe = sub.add_parser("observe", help="可观测性报告/告警（原 qualix-observe）")
    p_observe.add_argument(
        "observe_action",
        nargs="?",
        default="report",
        choices=["report", "daily", "guard-precision", "prompt-versions", "maintain"],
    )
    p_observe.add_argument("--period", choices=["daily", "weekly"], default="daily")
    p_observe.add_argument("--date", default=None, help="锚点日期 YYYY-MM-DD")
    p_observe.add_argument("--project", default=None, help="项目过滤")
    p_observe.add_argument("--phase", default=None, help="Phase 过滤")
    p_observe.add_argument("--block-spike-ratio", type=float, default=2.0, help="BLOCK 激增阈值倍数")
    p_observe.add_argument("--phase-failure-threshold", type=float, default=0.5, help="Phase 失败率阈值")
    p_observe.add_argument("--prompt-hash", default=None, help="observe prompt-versions 时按 hash 过滤")

    # regression
    p_regr = sub.add_parser("regression", help="回归测试（原 qualix-regression）")
    p_regr.add_argument("regression_action", nargs="?", default="run", choices=["run", "trend", "multi-judge"])
    p_regr.add_argument("--case", dest="case_id", default=None, help="只运行指定 case")
    p_regr.add_argument("--period", choices=["weekly"], default="weekly")
    p_regr.add_argument("--output-dir", dest="regression_output_dir", default=None, help="输出目录")
    p_regr.add_argument("--phase", default=None, help="multi-judge: 指定 Phase ID（默认 Q03）")
    p_regr.add_argument(
        "--models",
        default=None,
        help="multi-judge: 逗号分隔的模型列表（默认 deepseek-chat,claude-opus-4-6）",
    )

    # skill-evolve：从 failure-library 提炼 skill 改进建议
    p_skill = sub.add_parser("skill-evolve", help="从 failure-library 提炼 skill 改进建议")
    p_skill.add_argument(
        "skill_action",
        nargs="?",
        default="analyze",
        choices=["analyze", "suggest", "apply"],
    )
    p_skill.add_argument("--phase", default=None, help="指定 Phase ID，默认全部")
    p_skill.add_argument("--top", type=int, default=10, help="analyze 时每 phase 展示 top N 问题（默认 10）")
    p_skill.add_argument(
        "--no-dry-run",
        dest="dry_run",
        action="store_false",
        default=True,
        help="apply 时真正写入 SKILL.md（默认 dry-run）",
    )

    # ci-gate：读取 _gate_verdict.json 输出结构化结论（零 LLM，适合 CI 调用）
    p_ci = sub.add_parser("ci-gate", help="CI/CD 质量门禁：读取已有 verdict，决定 exit code")
    p_ci.add_argument("phase", nargs="?", default=None, help="Phase ID（如 Q06），与 --all-phases 二选一")
    p_ci.add_argument("--all-phases", action="store_true", help="检查所有已完成 Phase")
    p_ci.add_argument(
        "--fail-on",
        dest="fail_on",
        default="hard",
        choices=["hard", "soft", "any"],
        help="失败级别（hard=默认，soft=SOFT 也 fail，any=任何失败都 fail）",
    )
    p_ci.add_argument("--pr-comment", action="store_true", dest="pr_comment",
                      help="输出 GitHub PR Comment 格式 Markdown")

    # evidence-audit：SE → EUT → Test → Coverage 链路健康度
    p_eaudit = sub.add_parser("evidence-audit", help="展示 SE → EUT → Coverage 链路健康度")
    p_eaudit.add_argument("--phase", default="Q06", help="Phase ID（默认 Q06）")

    # spec：Phase 规范（JSON Schema + contract），代码为单一事实源
    p_spec = sub.add_parser("spec", help="输出 Phase 规范（JSON Schema + phase_contract），供 Agent 解析")
    p_spec.add_argument("--phase", required=True, help="Phase ID (Q01-Q07)")

    # render：渲染 Phase 产物为交互式 HTML（lab, PoC: 仅 Q05）
    p_render = sub.add_parser("render", help="渲染 Phase 产物为交互式 HTML（PoC: 仅 Q05）")
    p_render.add_argument("--phase", required=True, help="Phase ID (目前仅 Q05)")
    p_render.add_argument("--output", default=None, help="输出 HTML 路径（默认 output/<pid>/Q05/eut_matrix.html）")
    p_render.add_argument("--open", action="store_true", help="生成后在浏览器打开")

    _inject_json_flag_on_all_subparsers(parser)

    return parser


def _inject_json_flag_on_all_subparsers(parser: argparse.ArgumentParser) -> None:
    """为每个子命令追加 --json，便于 ``qualix-run <pid> execute Q01 --json`` 形式."""
    for action in parser._actions:
        if type(action).__name__ != "_SubParsersAction":
            continue
        choices: dict[str, Any] = getattr(action, "choices", {}) or {}
        for subparser in choices.values():
            if "--json" not in getattr(subparser, "_option_string_actions", {}):
                subparser.add_argument(
                    "--json",
                    action="store_true",
                    help="stdout 仅输出一条 JSON（machine-readable）",
                )
        break


def _dispatch(cmd: str) -> callable:
    """按需导入并返回命令处理函数."""
    if cmd in ("execute", "finalize", "approve", "skip", "reset", "auto"):
        from qualix.commands.phase import cmd_approve, cmd_auto, cmd_execute, cmd_finalize, cmd_reset, cmd_skip

        return {
            "execute": cmd_execute,
            "finalize": cmd_finalize,
            "approve": cmd_approve,
            "skip": cmd_skip,
            "reset": cmd_reset,
            "auto": cmd_auto,
        }[cmd]

    if cmd in ("status", "next", "log", "detail"):
        from qualix.commands.query import cmd_detail, cmd_log, cmd_next, cmd_status

        return {"status": cmd_status, "next": cmd_next, "log": cmd_log, "detail": cmd_detail}[cmd]

    if cmd == "startup":
        from qualix.commands.startup_fast import cmd_startup

        return cmd_startup

    if cmd in ("judge", "critique", "preference", "golden"):
        from qualix.commands.review import cmd_critique, cmd_golden, cmd_judge, cmd_preference

        return {"judge": cmd_judge, "critique": cmd_critique, "preference": cmd_preference, "golden": cmd_golden}[cmd]

    if cmd in ("orchestrate", "agent-run", "adaptive", "dag", "adaptive-override", "adaptive-diff"):
        from qualix.commands.agents import cmd_adaptive, cmd_adaptive_diff, cmd_adaptive_override, cmd_agent_run, cmd_dag, cmd_orchestrate

        return {
            "orchestrate": cmd_orchestrate,
            "agent-run": cmd_agent_run,
            "adaptive": cmd_adaptive,
            "dag": cmd_dag,
            "adaptive-override": cmd_adaptive_override,
            "adaptive-diff": cmd_adaptive_diff,
        }[cmd]

    if cmd in ("wiki-compile", "wiki-lint"):
        from qualix.commands.wiki import cmd_wiki_compile, cmd_wiki_lint

        return {"wiki-compile": cmd_wiki_compile, "wiki-lint": cmd_wiki_lint}[cmd]

    if cmd in ("init", "doctor", "update", "version"):
        from qualix.commands.setup import cmd_doctor, cmd_init, cmd_update, cmd_version

        return {"init": cmd_init, "doctor": cmd_doctor, "update": cmd_update, "version": cmd_version}[cmd]

    if cmd in ("metrics", "observe", "regression"):
        from qualix.commands.ops import cmd_metrics, cmd_observe, cmd_regression

        return {"metrics": cmd_metrics, "observe": cmd_observe, "regression": cmd_regression}[cmd]

    if cmd == "skill-evolve":
        from qualix.commands.skill_evolve import cmd_skill_evolve

        return cmd_skill_evolve

    if cmd == "ci-gate":
        from qualix.commands.ci import cmd_ci_gate

        return cmd_ci_gate

    if cmd == "evidence-audit":
        from qualix.commands.ci import cmd_evidence_audit

        return cmd_evidence_audit

    if cmd == "spec":
        from qualix.commands.phase_spec import cmd_spec

        return cmd_spec

    if cmd == "render":
        from qualix.commands.render import cmd_render

        return cmd_render

    if cmd == "task":
        from qualix.commands.task_cmd import cmd_task

        return cmd_task

    return None


def _resolve_output_dir(
    base_dir: str,
    *,
    project_id: str | None = None,
    quiet: bool = False,
) -> Path:
    """解析 output 目录，worktree 环境自动回退到主仓库.

    Args:
        base_dir: 项目根目录
        project_id: 项目 ID。提供时优先检查项目 state.json 实际所在路径，
                    避免 .qualix/output/ 目录存在时全局切换导致旧项目失联。
        quiet: True 时压制 worktree 重定向 stderr 提示（--json 模式下启用，
               避免污染 stdout 单条 JSON 契约；Agent 侧如果 stderr 合并捕获
               会破坏解析）
    """
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
                if not quiet:
                    print(f"[worktree] output 重定向到主仓库: {target}", file=sys.stderr)
                return target
    except (FileNotFoundError, ValueError):
        pass
    legacy_output = base / "output"
    qualix_output = base / ".qualix" / "output"
    # 有 project_id 时：state.json 在哪里项目就在哪里，新项目才考虑工作区布局
    if project_id:
        if (legacy_output / project_id / "state.json").exists():
            return legacy_output
        if (qualix_output / project_id / "state.json").exists():
            return qualix_output
    # 无 project_id 或新项目：优先 .qualix/output/（已初始化的工作区），否则 output/
    if qualix_output.exists():
        return qualix_output
    return legacy_output


def _check_version_drift_on_startup(project_root: Path) -> None:
    """Print a warning to stderr if settings.yaml pins a different Qualix version than installed."""
    from importlib.metadata import version as _v

    from qualix.core.settings import check_version_drift

    try:
        installed = _v("qualix")
    except Exception:
        return  # can't compare without installed version
    drift = check_version_drift(project_root, installed)
    if drift is None:
        return
    pinned, running = drift
    print(
        f"\n⚠️  版本漂移: .qualix/settings.yaml pin 的 {pinned} 与安装的 {running} 不一致\n"
        f"   建议运行: qualix-run init --force 同步（注意会清空 code_repos）\n"
        f"   或手动修改 .qualix/settings.yaml 的 qualix_version 字段\n",
        file=sys.stderr,
    )


def _handle_workspace_init(argv: list[str]) -> int:
    """workspace-level `qualix-run init`（不需要 project_id）.

    与现有 per-project `qualix-run <pid> init`（setup.py::cmd_init）不同：
    - 本命令在用户项目根目录创建 .qualix/ 工作区（settings.yaml / output/ / guardrail）
    - setup.py 的 cmd_init 在 output/<pid>/ 下初始化单个项目的 Phase 目录结构
    """
    sub = argparse.ArgumentParser(prog="qualix-run init", description="在当前目录初始化 .qualix/ 工作区")
    sub.add_argument("--profile", default=None, help="profile（不指定则自动识别技术栈）")
    sub.add_argument("--force", action="store_true", help="删除已有 .qualix/ 重建")
    ns = sub.parse_args(argv)

    _check_version_drift_on_startup(Path.cwd())

    from qualix.commands.init import run_init

    return run_init(project_root=Path.cwd(), profile=ns.profile, force=ns.force)


def _handle_workspace_path(argv: list[str]) -> int:
    """workspace-level `qualix-run path <category>`（不需要 project_id）."""
    sub = argparse.ArgumentParser(
        prog="qualix-run path",
        description="打印内置资源目录的绝对路径（只读）",
    )
    sub.add_argument(
        "category",
        choices=sorted(["skills", "references", "profiles", "regression"]),
        help="资源类别",
    )
    ns = sub.parse_args(argv)

    from qualix.commands.path_cmd import run_path

    return run_path(ns.category)


def _handle_workspace_doctor(argv: list[str]) -> int:
    """workspace-level `qualix-run doctor`（不需要 project_id）.

    生成 doctor bundle（脱敏 + 最近产出的 _internal + 版本一致性），
    并可选通过 glab 自动上传为 GitLab issue；glab 缺失/未认证时回退为
    打印 bundle 路径与 issue URL，让用户手动上传。
    """
    from qualix.commands.doctor import run_doctor

    sub = argparse.ArgumentParser(
        prog="qualix-run doctor",
        description="生成 doctor bundle 并（可选）自动上传到 GitLab issue",
    )
    sub.add_argument("--output", default=None, help="bundle 输出路径")
    sub.add_argument(
        "--redact",
        action="store_true",
        default=True,
        help="脱敏路径与 token（默认开启）",
    )
    sub.add_argument(
        "--no-redact",
        dest="redact",
        action="store_false",
        help="跳过脱敏（不可与上传组合）",
    )
    sub.add_argument(
        "--include-internal",
        action="store_true",
        default=True,
        help="包含最近 phase 的 _internal/（默认开启）",
    )
    sub.add_argument(
        "--no-include-internal",
        dest="include_internal",
        action="store_false",
    )
    sub.add_argument("--no-upload", action="store_true", help="只生成 bundle 不上传")
    sub.add_argument("--title", default=None, help="issue 标题（非 TTY 自动兜底）")
    ns = sub.parse_args(argv)

    return run_doctor(
        project_root=Path.cwd(),
        output=Path(ns.output) if ns.output else None,
        redact=ns.redact,
        include_internal=ns.include_internal,
        no_upload=ns.no_upload,
        title=ns.title,
    )


def _handle_workspace_contribute(argv: list[str]) -> int:
    """workspace-level `qualix-run contribute`（不需要 project_id）."""
    sub = argparse.ArgumentParser(
        prog="qualix-run contribute",
        description="把本地新积累的 failure-library 案例贡献回 Qualix repo",
    )
    sub.add_argument("--title", default=None, help="MR 标题（不指定则自动生成）")
    sub.add_argument("--no-upload", action="store_true", help="只扫描不上传")
    ns = sub.parse_args(argv)

    from qualix.commands.contribute import run_contribute

    rc, _ = run_contribute(title=ns.title, no_upload=ns.no_upload)
    return rc


def _handle_workspace_auth(argv: list[str]) -> int:
    """workspace-level `qualix-run auth status`."""
    sub = argparse.ArgumentParser(prog="qualix-run auth", description="Qualix 飞书认证状态")
    sub.add_argument("action", choices=["status"], help="status: 查看飞书认证状态")
    sub.parse_args(argv)

    from qualix.commands.auth import run_auth_status

    return run_auth_status()


class _TeeWriter(io.TextIOBase):
    """Write to both the original stream and an in-memory buffer (for stderr_tail)."""

    def __init__(self, original: io.TextIOBase) -> None:
        self._original = original
        self._buf = io.StringIO()

    def write(self, s: str) -> int:
        self._original.write(s)
        self._buf.write(s)
        return len(s)

    def flush(self) -> None:
        self._original.flush()

    def getvalue(self) -> str:
        return self._buf.getvalue()


def main() -> int:
    from qualix.core.last_run import write_last_run

    exit_code = 0
    tee = _TeeWriter(sys.stderr)
    sys.stderr = tee  # type: ignore[assignment]
    try:
        # workspace-level init 走独立路径（不需要 project_id）
        # 与 subparser 注册的 per-project `qualix-run <pid> init` 并存，靠 argv 位置区分
        if len(sys.argv) >= 2 and sys.argv[1] == "init":
            exit_code = _handle_workspace_init(sys.argv[2:])
            return exit_code

        if len(sys.argv) >= 2 and sys.argv[1] == "path":
            exit_code = _handle_workspace_path(sys.argv[2:])
            return exit_code

        if len(sys.argv) >= 2 and sys.argv[1] == "doctor":
            exit_code = _handle_workspace_doctor(sys.argv[2:])
            return exit_code

        if len(sys.argv) >= 2 and sys.argv[1] == "contribute":
            exit_code = _handle_workspace_contribute(sys.argv[2:])
            return exit_code

        if len(sys.argv) >= 2 and sys.argv[1] == "auth":
            exit_code = _handle_workspace_auth(sys.argv[2:])
            return exit_code

        parser = _build_parser()
        args = parser.parse_args()
        quiet_env = bool(getattr(args, "json", False))
        output_dir = _resolve_output_dir(
            args.base_dir,
            project_id=getattr(args, "project_id", None),
            quiet=quiet_env,
        )

        # Deprecation check: warn if running from inside the Qualix repo layout
        from qualix.core.resource_resolver import ResourceResolver

        ResourceResolver(project_root=Path.cwd()).check_legacy_layout()
        _check_version_drift_on_startup(Path.cwd())

        handler = _dispatch(args.command)
        if not handler:
            print(f"未知命令: {args.command}", file=sys.stderr)
            exit_code = 1
            return exit_code

        exit_code = handler(args, output_dir)
        return exit_code
    finally:
        sys.stderr = tee._original  # type: ignore[assignment]
        with contextlib.suppress(Exception):
            write_last_run(
                project_root=Path.cwd(),
                cmd=sys.argv,
                exit_code=int(exit_code or 0),
                stderr_tail=tee.getvalue(),
            )
