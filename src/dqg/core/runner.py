"""dqg-run: Pipeline 执行入口.

用法:
    dqg-run <project_id> execute <phase>     # 启动 Phase
    dqg-run <project_id> finalize <phase>    # 校验产物并提交 review
    dqg-run <project_id> approve <phase>     # 人工确认通过
    dqg-run <project_id> skip <phase>        # 跳过 Phase
    dqg-run <project_id> status              # 查看状态看板
    dqg-run <project_id> next                # 显示下一步可执行的 Phase
    dqg-run <project_id> log                 # 查看执行记录
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from dqg.constants import DEFAULT_ADAPTIVE_JUDGE_MODELS, DEFAULT_FALLBACK_MODEL, DEFAULT_JUDGE_MODEL, DEFAULT_PRIMARY_MODEL
from dqg.core.profiles import list_profiles


def main() -> int:
    parser = argparse.ArgumentParser(description="研发质量门禁 Pipeline Runner")
    parser.add_argument("project_id", help="项目 ID")
    parser.add_argument("--base-dir", default=".", help="项目根目录")
    parser.add_argument(
        "--profile",
        default=None,
        choices=[profile.profile_id for profile in list_profiles()],
        help="技术栈 profile（默认 java-ddd-tmf）",
    )

    sub = parser.add_subparsers(dest="command", required=True)

    # execute
    p_exec = sub.add_parser("execute", help="启动 Phase")
    p_exec.add_argument("phase", help="Phase ID (A, A.5, A.6, B, C, D)")
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
    p_auto.add_argument("--skip", nargs="*", default=[], help="跳过指定 Phase（如 A.6）")

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
    p_adapt.add_argument("--judge-models", default=",".join(DEFAULT_ADAPTIVE_JUDGE_MODELS), help="Judge 模型列表（逗号分隔）")
    p_adapt.add_argument("--max-iter", type=int, default=3, help="最大迭代次数")
    p_adapt.add_argument("--threshold", type=float, default=3.5, help="通过阈值（1-5）")

    # wiki-compile
    sub.add_parser("wiki-compile", help="从历史提取并编译生成该项目的初始 LLM-Wiki")

    # wiki-lint
    sub.add_parser("wiki-lint", help="启动清理智能体：打扫并梳理当前的 .dqg-wiki 全景拓扑")

    args = parser.parse_args()
    base_dir = Path(args.base_dir).resolve()
    output_dir = base_dir / "output"

    # 延迟导入，按需加载对应命令模块
    from dqg.commands.phase import cmd_execute, cmd_finalize, cmd_approve, cmd_skip, cmd_auto
    from dqg.commands.query import cmd_status, cmd_next, cmd_detail, cmd_log, cmd_startup
    from dqg.commands.review import cmd_judge, cmd_critique, cmd_preference, cmd_golden
    from dqg.commands.agents import cmd_orchestrate, cmd_agent_run, cmd_adaptive
    from dqg.commands.wiki import cmd_wiki_compile, cmd_wiki_lint

    cmd_map = {
        "execute": cmd_execute,
        "finalize": cmd_finalize,
        "approve": cmd_approve,
        "skip": cmd_skip,
        "status": cmd_status,
        "next": cmd_next,
        "log": cmd_log,
        "startup": cmd_startup,
        "detail": cmd_detail,
        "auto": cmd_auto,
        "judge": cmd_judge,
        "critique": cmd_critique,
        "preference": cmd_preference,
        "golden": cmd_golden,
        "orchestrate": cmd_orchestrate,
        "agent-run": cmd_agent_run,
        "adaptive": cmd_adaptive,
        "wiki-compile": cmd_wiki_compile,
        "wiki-lint": cmd_wiki_lint,
    }

    handler = cmd_map.get(args.command)
    if not handler:
        print(f"未知命令: {args.command}", file=sys.stderr)
        return 1

    return handler(args, output_dir)
