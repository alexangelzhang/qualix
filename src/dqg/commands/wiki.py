"""Wiki 命令：wiki-compile / wiki-lint."""

from __future__ import annotations

from pathlib import Path


def cmd_wiki_compile(args, output_dir: Path) -> int:
    from dqg.memory.memory_layer import MemoryLayer
    from dqg.memory.wiki_layer import WikiManager

    print("\n  [Wiki] 开始从 Phase Q01 中编译并构建项目 LLM-Wiki ...")
    wm = WikiManager(output_dir)
    print(wm.compile_wiki(args.project_id))
    count = MemoryLayer(output_dir).sync_wiki_to_sqlite(args.project_id)
    print(f"  [Wiki] 静默桥接: 同步了 {count} 个百科节点至 FTS5 SQLite。")
    return 0


def cmd_wiki_lint(args, output_dir: Path) -> int:
    from dqg.memory.memory_layer import MemoryLayer
    from dqg.memory.wiki_layer import WikiManager

    print("\n  [Wiki] 启动 LLM-Linter 整理冗余孤儿页面 ...")
    wm = WikiManager(output_dir)
    print(wm.lint_wiki(args.project_id))
    MemoryLayer(output_dir).sync_wiki_to_sqlite(args.project_id)
    return 0
