"""Wiki 命令：wiki-compile / wiki-lint."""

from __future__ import annotations

from pathlib import Path


def cmd_wiki_compile(args, output_dir: Path) -> int:
    from qualix.commands.cli_json import cli_envelope, cli_json_mode, print_cli_json
    from qualix.memory.memory_layer import MemoryLayer
    from qualix.memory.wiki_layer import WikiManager

    if not cli_json_mode(args):
        print("\n  [Wiki] 开始从 Phase Q01 中编译并构建项目 LLM-Wiki ...")
    wm = WikiManager(output_dir)
    text = wm.compile_wiki(args.project_id)
    if not cli_json_mode(args):
        print(text)
    count = MemoryLayer(output_dir).sync_wiki_to_sqlite(args.project_id)
    if cli_json_mode(args):
        print_cli_json(
            cli_envelope(
                command="wiki-compile",
                project_id=args.project_id,
                success=True,
                exit_code=0,
                extra={"compile_output": text, "sqlite_nodes_synced": count},
            )
        )
    else:
        print(f"  [Wiki] 静默桥接: 同步了 {count} 个百科节点至 FTS5 SQLite。")
    return 0


def cmd_wiki_lint(args, output_dir: Path) -> int:
    from qualix.commands.cli_json import cli_envelope, cli_json_mode, print_cli_json
    from qualix.memory.memory_layer import MemoryLayer
    from qualix.memory.wiki_layer import WikiManager

    if not cli_json_mode(args):
        print("\n  [Wiki] 启动 LLM-Linter 整理冗余孤儿页面 ...")
    wm = WikiManager(output_dir)
    text = wm.lint_wiki(args.project_id)
    if not cli_json_mode(args):
        print(text)
    MemoryLayer(output_dir).sync_wiki_to_sqlite(args.project_id)
    if cli_json_mode(args):
        print_cli_json(
            cli_envelope(
                command="wiki-lint",
                project_id=args.project_id,
                success=True,
                exit_code=0,
                extra={"lint_output": text},
            )
        )
    return 0
