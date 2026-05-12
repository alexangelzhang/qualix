"""DQG 全局命令入口.

全局命令（不需要 project_id）：
    dqg init          — 初始化环境 + 启动看板
    dqg dashboard     — 启动/停止/状态看板
    dqg version       — 版本信息

项目命令委托给 dqg-run：
    dqg run <project_id> <command> ...
"""

from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
from pathlib import Path

from dqg.constants import DASHBOARD_PID_FILE as _DASHBOARD_PID_FILE
from dqg.constants import DASHBOARD_PORT as _DASHBOARD_PORT


def _base_dir() -> Path:
    return Path.cwd()


def _output_dir() -> Path:
    return _base_dir() / "output"


def _pid_file() -> Path:
    return _output_dir() / _DASHBOARD_PID_FILE


# ---------------------------------------------------------------------------
# init
# ---------------------------------------------------------------------------


def _cmd_init(args: argparse.Namespace) -> int:
    """初始化 DQG 环境."""
    base = _base_dir()
    output = _output_dir()

    print("DQG 初始化")
    print("=" * 50)

    # 1. 检查目录结构
    print("\n1. 检查目录结构...")
    output.mkdir(parents=True, exist_ok=True)
    (output / ".dqg").mkdir(exist_ok=True)
    print(f"   output 目录: {output}")

    # 2. 检查依赖
    print("\n2. 检查依赖...")
    deps_ok = True

    # Python package
    try:
        import dqg.core.runner

        print("   dqg package: OK")
    except ImportError:
        print("   dqg package: 未安装，执行 `pip install -e '.[dev]'`")
        deps_ok = False

    # larkkit
    try:
        result = subprocess.run(
            ["uvx", "larkkit", "version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            version = result.stdout.strip().split("\n")[0]
            print(f"   larkkit: {version}")
        else:
            print("   larkkit: 未安装，执行 `uvx larkkit version` 检查")
    except (FileNotFoundError, subprocess.TimeoutExpired):
        print("   larkkit: 未安装（飞书文档抓取需要）")

    # streamlit
    try:
        import streamlit

        print(f"   streamlit: {streamlit.__version__}")
    except ImportError:
        print("   streamlit: 未安装，执行 `pip install streamlit`")
        deps_ok = False

    # 3. 迁移历史数据到 SQLite
    print("\n3. 初始化数据库...")
    try:
        from dqg.store import migrate_all

        result = migrate_all(output)
        total = sum(result.values())
        if total > 0:
            print(f"   已迁移 {total} 条历史记录: {result}")
        else:
            print("   数据库就绪（无历史数据需迁移）")
    except Exception as e:
        print(f"   数据库初始化失败: {e}")

    # 4. 检查平台指令文件
    print("\n4. 检查平台指令文件...")
    platform_files = {
        "CLAUDE.md": "Claude Code",
        "AGENTS.md": "Codex / opencode / IntelliJ",
        "GEMINI.md": "Gemini CLI",
        ".cursor/rules/dqg.mdc": "Cursor",
    }
    for f, name in platform_files.items():
        path = base / f
        status = "OK" if path.exists() else "缺失"
        print(f"   {name} ({f}): {status}")

    # 5. 检查 bug 案例库
    print("\n5. 检查 Bug 案例库...")
    try:
        from dqg.tracking.bug_cases import load_cases, summarize_cases

        cases = load_cases()
        summary = summarize_cases(cases)
        print(f"   {summary['total']} 条案例 ({summary['open']} open, {summary['fixed']} fixed)")
    except Exception as e:
        print(f"   案例库加载失败: {e}")

    # 6. 启动看板
    if not getattr(args, "no_dashboard", False):
        print("\n6. 启动看板...")
        _start_dashboard()
    else:
        print("\n6. 跳过看板启动 (--no-dashboard)")

    print("\n" + "=" * 50)
    if deps_ok:
        print("初始化完成! 在 AI IDE 中输入 @dqg-starter 开始使用。")
    else:
        print("初始化完成（部分依赖缺失，请按提示安装）。")

    return 0


# ---------------------------------------------------------------------------
# dashboard
# ---------------------------------------------------------------------------


def _is_dashboard_running() -> tuple[bool, int | None]:
    """检查看板是否在运行."""
    pid_file = _pid_file()
    if not pid_file.exists():
        return False, None
    try:
        pid = int(pid_file.read_text().strip())
        os.kill(pid, 0)  # 检查进程是否存在
        return True, pid
    except (ValueError, ProcessLookupError, PermissionError):
        pid_file.unlink(missing_ok=True)
        return False, None


def _start_dashboard(port: int = _DASHBOARD_PORT) -> bool:
    """后台启动看板."""
    running, pid = _is_dashboard_running()
    if running:
        print(f"   看板已在运行 (PID: {pid}, http://localhost:{port})")
        return True

    try:
        from dqg.reporting import dashboard as _dashboard_mod

        dashboard_path = Path(_dashboard_mod.__file__)
    except ImportError:
        dashboard_path = Path(__file__).parents[1] / "reporting" / "dashboard" / "__init__.py"
    if not dashboard_path.exists():
        print("   dashboard 包不存在")
        return False

    try:
        proc = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "streamlit",
                "run",
                str(dashboard_path),
                "--server.port",
                str(port),
                "--server.headless",
                "true",
                "--browser.gatherUsageStats",
                "false",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        # 保存 PID
        pid_file = _pid_file()
        pid_file.parent.mkdir(parents=True, exist_ok=True)
        pid_file.write_text(str(proc.pid))
        print(f"   看板已启动 (PID: {proc.pid}, http://localhost:{port})")
        return True
    except Exception as e:
        print(f"   看板启动失败: {e}")
        return False


def _stop_dashboard() -> bool:
    """停止看板."""
    running, pid = _is_dashboard_running()
    if not running:
        print("   看板未在运行")
        return True

    try:
        os.kill(pid, signal.SIGTERM)
        _pid_file().unlink(missing_ok=True)
        print(f"   看板已停止 (PID: {pid})")
        return True
    except (ProcessLookupError, PermissionError) as e:
        print(f"   停止失败: {e}")
        _pid_file().unlink(missing_ok=True)
        return False


def _cmd_dashboard(args: argparse.Namespace) -> int:
    """看板管理."""
    action = getattr(args, "action", "status")

    if action == "start":
        port = getattr(args, "port", _DASHBOARD_PORT)
        _start_dashboard(port)
    elif action == "stop":
        _stop_dashboard()
    else:
        running, pid = _is_dashboard_running()
        if running:
            print(f"看板运行中 (PID: {pid}, http://localhost:{_DASHBOARD_PORT})")
        else:
            print("看板未运行。启动: dqg dashboard start")

    return 0


# ---------------------------------------------------------------------------
# version
# ---------------------------------------------------------------------------


def _cmd_version(_args: argparse.Namespace) -> int:
    from dqg.commands.setup import DQG_VERSION

    print(f"DQG (Dev Quality Gate) v{DQG_VERSION}")
    return 0


def _cmd_experiment(args: argparse.Namespace) -> int:
    """Skill 自动迭代实验."""
    from dqg.tracking.experiment import cmd_experiment

    return cmd_experiment(args, _output_dir())


def _cmd_cache(args) -> int:
    """dqg cache export <project_id> [--phase Q01] [--output path]"""
    from dqg.cache.fact_cache import export_facts_to_markdown
    from dqg.core.phase_registry import PHASE_DEFS

    output_dir = _output_dir()
    project_id = args.project_id
    phase_filter = args.phase

    phases = [phase_filter] if phase_filter else list(PHASE_DEFS.keys())

    exported_paths = []
    for phase_id in phases:
        path = export_facts_to_markdown(output_dir, project_id, phase_id)
        if path:
            exported_paths.append(path)
            print(f"  ✓ Phase {phase_id}: {path}")

    # 全量 semantic_cache 快照
    if not phase_filter:
        snapshot_path = _export_semantic_cache(output_dir, project_id, args.output)
        if snapshot_path:
            exported_paths.append(snapshot_path)
            print(f"  ✓ Semantic cache: {snapshot_path}")

    if not exported_paths:
        print("  暂无可导出的缓存数据")
        return 0

    print(f"\n  共导出 {len(exported_paths)} 个文件，可纳入 git 追踪")
    return 0


def _export_semantic_cache(output_dir, project_id: str, output_path: str | None) -> Path | None:
    """导出 semantic_cache 为 Markdown 快照."""
    from datetime import datetime
    from pathlib import Path

    from dqg.store import get_connection

    try:
        with get_connection(output_dir) as conn:
            rows = conn.execute(
                "SELECT query_text, result_json, result_type, hit_count, created_at "
                "FROM query_cache ORDER BY created_at DESC",
            ).fetchall()
    except Exception as e:
        from dqg.log import get_logger

        get_logger(__name__).debug("Semantic cache export failed: %s", e)
        return None

    if not rows:
        return None

    lines = [
        f"# Semantic Cache Snapshot — {project_id}",
        "",
        f"> 生成于 {datetime.now().strftime('%Y-%m-%d %H:%M')}，共 {len(rows)} 条缓存条目。",
        "> 可纳入 git 追踪，用于审计 Judge 命中了哪些缓存结果。",
        "",
    ]

    for row in rows:
        query_text, result_json, result_type, hit_count, created_at = row

        lines.append(f"### 查询: {(query_text or '')[:80]}")
        lines.append(f"- 类型: `{result_type or '—'}` | 命中: {hit_count or 0} | 创建: {created_at or '—'}")
        result_preview = (result_json or "")[:200].replace("\n", " ")
        lines.append(f"- 结果: {result_preview}{'...' if len(result_json or '') > 200 else ''}")
        lines.append("")

    content = "\n".join(lines)
    if output_path:
        dest = Path(output_path)
    else:
        dest = output_dir / project_id / "cache_snapshot.md"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(content, encoding="utf-8")
    return dest


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(
        description="DQG 研发质量门禁",
        usage="dqg <command> [options]",
    )
    sub = parser.add_subparsers(dest="command")

    # init
    p_init = sub.add_parser("init", help="初始化环境 + 启动看板")
    p_init.add_argument("--no-dashboard", action="store_true", help="不启动看板")

    # dashboard
    p_dash = sub.add_parser("dashboard", help="看板管理")
    p_dash.add_argument("action", nargs="?", default="status", choices=["start", "stop", "status"])
    p_dash.add_argument("--port", type=int, default=_DASHBOARD_PORT, help=f"端口（默认 {_DASHBOARD_PORT}）")

    # version
    sub.add_parser("version", help="版本信息")

    # experiment
    p_exp = sub.add_parser("experiment", help="Skill 自动迭代实验")
    p_exp.add_argument("phase", help="Phase ID (Q01-Q07)")
    p_exp.add_argument("exp_action", nargs="?", default="start", choices=["start", "log", "persist"])
    p_exp.add_argument("--cycle", type=int, default=1, help="实验轮次")
    p_exp.add_argument("--benchmark", default="", help="Benchmark case ID")

    # cache
    p_cache = sub.add_parser("cache", help="缓存管理（审计导出）")
    p_cache.add_argument("cache_action", choices=["export"], help="操作类型")
    p_cache.add_argument("project_id", help="项目 ID")
    p_cache.add_argument("--phase", default=None, help="指定 Phase（不填则导出所有）")
    p_cache.add_argument("--format", dest="fmt", default="markdown", choices=["markdown"], help="输出格式")
    p_cache.add_argument("--output", default=None, help="输出文件路径（默认写入 output/<project>/cache_snapshot.md）")

    # run (delegate to dqg-run)
    p_run = sub.add_parser("run", help="项目命令（等同于 dqg-run）")
    p_run.add_argument("run_args", nargs=argparse.REMAINDER, help="dqg-run 参数")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 0

    cmd_map = {
        "init": _cmd_init,
        "dashboard": _cmd_dashboard,
        "version": _cmd_version,
        "experiment": _cmd_experiment,
        "cache": _cmd_cache,
    }

    handler = cmd_map.get(args.command)
    if handler:
        return handler(args)

    if args.command == "run":
        # 委托给 dqg-run
        from dqg.core.runner import main as runner_main

        sys.argv = ["dqg-run", *args.run_args]
        return runner_main()

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
