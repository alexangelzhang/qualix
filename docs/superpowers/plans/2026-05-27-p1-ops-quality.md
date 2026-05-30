# P1 运营质量三件套 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现 --strict-profile-context 严格门禁、task store CLI 接入、以及四类运营口径（命中率/闭环时长/误报率/Guard精度）进入 observe 报告。

**Architecture:** P1-8 在现有 finalize handler 上加 ctx 标志位升级 WARNING→BLOCKED；P1-5 新建 `commands/task_cmd.py` 并接入 `runner.py` 的 `_build_parser`/`_dispatch`；P1-9 在 telemetry record 加 `force_approved` 字段，然后在 `_project_metrics` 计算闭环时长和误报率，在 `generate_report` 里引入 guard precision。三个子项目完全独立。

**Tech Stack:** Python 3.11+, Pydantic v2, argparse, pathlib, pytest

---

## 文件总览

| 操作 | 路径 | 职责 |
|------|------|------|
| MODIFY | `src/dqg/runtime/execution_context.py` | 加 `strict_profile_context: bool = False` |
| MODIFY | `src/dqg/core/runner.py` | finalize 加 flag；新增 task 子命令 |
| MODIFY | `src/dqg/commands/phase.py` | cmd_finalize 传 flag；cmd_approve 传 force_approved |
| MODIFY | `src/dqg/runtime/handlers/handlers_finalize.py` | handle_profile_context_check 加严格模式 |
| CREATE | `src/dqg/commands/task_cmd.py` | cmd_task 实现 list/resume |
| MODIFY | `src/dqg/reporting/telemetry.py` | PhaseRunRecord 加 force_approved |
| MODIFY | `src/dqg/reporting/observability.py` | 闭环时长/误报率/guard_precision |
| CREATE | `tests/test_p1_ops_quality.py` | 7 条单测 |

---

## Task 1：--strict-profile-context 严格模式（P1-8）

**Files:**
- Modify: `src/dqg/runtime/execution_context.py:17-36`
- Modify: `src/dqg/core/runner.py:62-68`（finalize 子命令）
- Modify: `src/dqg/commands/phase.py:205-209`（cmd_finalize）
- Modify: `src/dqg/runtime/handlers/handlers_finalize.py:228-248`
- Test: `tests/test_p1_ops_quality.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_p1_ops_quality.py
"""Tests for P1 ops quality improvements."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock


# ---------------------------------------------------------------------------
# Task 1: --strict-profile-context
# ---------------------------------------------------------------------------

def _make_ctx(tmp_path: Path, phase_id: str = "Q01", strict: bool = False):
    from dqg.runtime.execution_context import ExecutionContext

    ctx = ExecutionContext(
        output_dir=tmp_path,
        project_id="test",
        phase_id=phase_id,
        strict_profile_context=strict,
    )
    ctx.phase_root = tmp_path / "test" / phase_id
    ctx.phase_root.mkdir(parents=True, exist_ok=True)
    ctx.internal_dir = ctx.phase_root / "_internal"
    ctx.internal_dir.mkdir()
    return ctx


def _make_result():
    r = MagicMock()
    r.errors = []
    r.warnings = []
    r.add_warning = lambda msg: r.warnings.append(msg)
    return r


def test_strict_profile_context_blocks_when_section_missing(tmp_path):
    """--strict-profile-context 且报告缺 PROFILE_CONTEXT → BLOCKED."""
    from dqg.runtime.handlers.handlers_finalize import handle_profile_context_check

    ctx = _make_ctx(tmp_path, phase_id="Q01", strict=True)
    # 写一个不含 PROFILE_CONTEXT 的报告文件
    (ctx.phase_root / "phase_a_report.md").write_text("# 报告\n\n无 profile context")

    result = _make_result()
    handle_profile_context_check(ctx, result)

    assert any("BLOCKED" in e for e in result.errors), "严格模式应产生 BLOCKED error"
    assert not any("BLOCKED" in w for w in result.warnings), "不应在 warning 里出现 BLOCKED"


def test_non_strict_profile_context_warns_only(tmp_path):
    """非严格模式下缺 PROFILE_CONTEXT → 仅 WARNING，不 BLOCKED。"""
    from dqg.runtime.handlers.handlers_finalize import handle_profile_context_check

    ctx = _make_ctx(tmp_path, phase_id="Q01", strict=False)
    (ctx.phase_root / "phase_a_report.md").write_text("# 报告\n\n无 profile context")

    result = _make_result()
    handle_profile_context_check(ctx, result)

    assert result.errors == [], "非严格模式不应有 BLOCKED error"
    assert len(result.warnings) > 0, "非严格模式应有 WARNING"
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd /path/to/rd-gate
python -m pytest tests/test_p1_ops_quality.py::test_strict_profile_context_blocks_when_section_missing \
  tests/test_p1_ops_quality.py::test_non_strict_profile_context_warns_only -v 2>&1 | tail -10
```
Expected: `TypeError: ExecutionContext.__init__() got unexpected keyword argument 'strict_profile_context'`

- [ ] **Step 3: 在 ExecutionContext 加字段**

读取 `src/dqg/runtime/execution_context.py`，在 `coverage_report: str | None = None` 之后（约 L27）插入：

```python
    strict_profile_context: bool = False  # finalize --strict-profile-context 时为 True
```

- [ ] **Step 4: 修改 handle_profile_context_check**

读取 `src/dqg/runtime/handlers/handlers_finalize.py`，找到 `handle_profile_context_check` 函数（L228-248）。
将：

```python
    if not profile_ctx_path.exists():
        result.add_warning(f"Missing profile context: {profile_ctx_path}")

    report_path = ctx.phase_root / report_file
    if report_path.exists():
        import re as _re

        _PROFILE_CTX_RE = _re.compile(r"^#{1,3}\s*(\d+\.\s*)?PROFILE_CONTEXT", _re.MULTILINE)
        if not _PROFILE_CTX_RE.search(report_path.read_text(encoding="utf-8")):
            result.add_warning("Report missing PROFILE_CONTEXT section")
```

改为：

```python
    _strict = getattr(ctx, "strict_profile_context", False)

    if not profile_ctx_path.exists():
        _msg = f"Missing profile context: {profile_ctx_path}"
        if _strict:
            result.errors.append(f"BLOCKED: [profile_context] {_msg}")
        else:
            result.add_warning(_msg)

    report_path = ctx.phase_root / report_file
    if report_path.exists():
        import re as _re

        _PROFILE_CTX_RE = _re.compile(r"^#{1,3}\s*(\d+\.\s*)?PROFILE_CONTEXT", _re.MULTILINE)
        if not _PROFILE_CTX_RE.search(report_path.read_text(encoding="utf-8")):
            _msg2 = "Report missing PROFILE_CONTEXT section"
            if _strict:
                result.errors.append(f"BLOCKED: [profile_context] {_msg2}")
            else:
                result.add_warning(_msg2)
```

- [ ] **Step 5: 在 runner.py 的 finalize 子命令加 flag**

读取 `src/dqg/core/runner.py`，找到 finalize 子命令（约 L62-68）：

```python
    # finalize
    p_fin = sub.add_parser("finalize", help="校验产物并提交 review")
    p_fin.add_argument("phase", help="Phase ID")
    p_fin.add_argument(
        "--code-repo",
        ...
    )
```

在 `p_fin.add_argument("--code-repo", ...)` 块之后追加：

```python
    p_fin.add_argument(
        "--strict-profile-context",
        action="store_true",
        default=False,
        help="严格模式：报告缺少 PROFILE_CONTEXT 时阻断 finalize（默认 WARNING）",
    )
```

- [ ] **Step 6: 在 cmd_finalize 构造 ctx 时传入 flag**

读取 `src/dqg/commands/phase.py`，找到 `cmd_finalize` 里的 `ctx = ExecutionContext(...)` 块（约 L205-209）：

```python
    ctx = ExecutionContext(
        output_dir=output_dir,
        project_id=args.project_id,
        phase_id=args.phase,
    )
```

改为：

```python
    ctx = ExecutionContext(
        output_dir=output_dir,
        project_id=args.project_id,
        phase_id=args.phase,
        strict_profile_context=getattr(args, "strict_profile_context", False),
    )
```

- [ ] **Step 7: 运行测试确认通过**

```bash
python -m pytest tests/test_p1_ops_quality.py::test_strict_profile_context_blocks_when_section_missing \
  tests/test_p1_ops_quality.py::test_non_strict_profile_context_warns_only -v 2>&1 | tail -8
```
Expected: 2 PASSED

- [ ] **Step 8: 全量回归**

```bash
python -m pytest tests/ -x -q --ignore=tests/test_p1_ops_quality.py 2>&1 | tail -5
```
Expected: no new failures

- [ ] **Step 9: 提交**

```bash
git add src/dqg/runtime/execution_context.py src/dqg/runtime/handlers/handlers_finalize.py \
        src/dqg/core/runner.py src/dqg/commands/phase.py tests/test_p1_ops_quality.py
git commit -m "feat(p1-8): --strict-profile-context 严格门禁（WARNING 升级为 BLOCKED）"
```

---

## Task 2：Task store CLI（P1-5）

**Files:**
- Create: `src/dqg/commands/task_cmd.py`
- Modify: `src/dqg/core/runner.py:188-228`（ops 区末尾加 task）
- Test: `tests/test_p1_ops_quality.py`

- [ ] **Step 1: 写失败测试**

在 `tests/test_p1_ops_quality.py` 追加：

```python
# ---------------------------------------------------------------------------
# Task 2: Task store CLI
# ---------------------------------------------------------------------------

def test_cmd_task_list_returns_records(tmp_path):
    """cmd_task list 应返回已有 task runs."""
    from dqg.commands.task_cmd import cmd_task
    from dqg.runtime.task_store import create_task_run, complete_task_run

    # 创建两条 task run
    tid1 = create_task_run(tmp_path, task_type="adaptive", project_id="p1", phase_id="Q01")
    complete_task_run(tmp_path, tid1, status="completed", result_summary="done")
    tid2 = create_task_run(tmp_path, task_type="adaptive", project_id="p1", phase_id="Q05")

    args = type("A", (), {
        "project_id": "p1",
        "task_action": "list",
        "task_id": None,
        "status": "all",
        "limit": 20,
        "json": False,
    })()
    rc = cmd_task(args, tmp_path)
    assert rc == 0


def test_cmd_task_resume_no_tasks(tmp_path):
    """cmd_task resume 无可恢复 task 时应优雅返回（非 crash）."""
    from dqg.commands.task_cmd import cmd_task

    args = type("A", (), {
        "project_id": "p1",
        "task_action": "resume",
        "task_id": None,
        "status": "all",
        "limit": 20,
        "json": False,
    })()
    rc = cmd_task(args, tmp_path)
    assert rc in (0, 1)  # 无 task 可以 0（空列表）或 1（无法恢复）
```

- [ ] **Step 2: 运行测试确认失败**

```bash
python -m pytest tests/test_p1_ops_quality.py::test_cmd_task_list_returns_records \
  tests/test_p1_ops_quality.py::test_cmd_task_resume_no_tasks -v 2>&1 | tail -8
```
Expected: `ModuleNotFoundError: No module named 'dqg.commands.task_cmd'`

- [ ] **Step 3: 创建 task_cmd.py**

新建 `src/dqg/commands/task_cmd.py`：

```python
"""dqg-run <pid> task list|resume — Task 管理 CLI."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from dqg.log import get_logger

log = get_logger(__name__)


def _print_table(rows: list[dict[str, Any]]) -> None:
    """打印简单的 ASCII 表格."""
    if not rows:
        print("  (无记录)")
        return
    cols = ["id", "task_type", "project_id", "phase_id", "status", "created_at"]
    widths = {c: max(len(c), max((len(str(r.get(c, "") or "")) for r in rows), default=0)) for c in cols}
    header = "  " + "  ".join(c.ljust(widths[c]) for c in cols)
    sep = "  " + "  ".join("-" * widths[c] for c in cols)
    print(header)
    print(sep)
    for row in rows:
        print("  " + "  ".join(str(row.get(c, "") or "").ljust(widths[c]) for c in cols))


def cmd_task(args, output_dir: Path) -> int:
    """dqg-run <pid> task list|resume."""
    from dqg.commands.cli_json import cli_envelope, cli_json_mode, print_cli_json
    from dqg.runtime.task_store import (
        get_latest_checkpoint,
        get_resumable_task,
        get_task_run,
        list_task_runs,
    )

    action = getattr(args, "task_action", "list") or "list"
    task_id = getattr(args, "task_id", None)
    use_json = cli_json_mode(args)

    if action == "list":
        status_filter = getattr(args, "status", "all")
        limit = getattr(args, "limit", 20)
        runs = list_task_runs(
            output_dir,
            project_id=args.project_id,
            status=None if status_filter == "all" else status_filter,
            limit=limit,
        )
        if use_json:
            print_cli_json(
                cli_envelope(
                    command="task list",
                    project_id=args.project_id,
                    success=True,
                    exit_code=0,
                    extra={"tasks": runs, "total": len(runs)},
                )
            )
        else:
            print(f"\n  Task runs（{args.project_id}）:")
            _print_table(runs)
        return 0

    if action == "resume":
        if task_id:
            # 指定 task_id：查最新 checkpoint
            task = get_task_run(output_dir, task_id)
            if not task:
                if not use_json:
                    print(f"  ❌ Task {task_id} 不存在", file=sys.stderr)
                return 1
            ckpt = get_latest_checkpoint(output_dir, task_id)
            if use_json:
                print_cli_json(
                    cli_envelope(
                        command="task resume",
                        project_id=args.project_id,
                        success=True,
                        exit_code=0,
                        extra={"task": task, "checkpoint": ckpt},
                    )
                )
            else:
                print(f"\n  Task: {task_id}")
                print(f"  类型: {task.get('task_type')}  Phase: {task.get('phase_id')}  状态: {task.get('status')}")
                if ckpt:
                    print(f"  最新 checkpoint: {ckpt.get('checkpoint_id')} ({ckpt.get('created_at', '')})")
                    print(f"  迭代轮次: {ckpt.get('iteration', '?')}")
                else:
                    print("  无 checkpoint")
            return 0
        else:
            # 无 task_id：查找可恢复 task
            task = get_resumable_task(output_dir, project_id=args.project_id)
            if not task:
                if not use_json:
                    print(f"\n  (无可恢复的 task，project={args.project_id})")
                return 0
            ckpt = get_latest_checkpoint(output_dir, task["id"])
            if use_json:
                print_cli_json(
                    cli_envelope(
                        command="task resume",
                        project_id=args.project_id,
                        success=True,
                        exit_code=0,
                        extra={"task": task, "checkpoint": ckpt},
                    )
                )
            else:
                print(f"\n  可恢复任务: {task['id']}")
                print(f"  类型: {task.get('task_type')}  Phase: {task.get('phase_id')}  状态: {task.get('status')}")
                if ckpt:
                    print(f"  最新 checkpoint: {ckpt.get('checkpoint_id')} ({ckpt.get('created_at', '')})")
                    print(f"  恢复命令: dqg-run {args.project_id} adaptive {task.get('phase_id', '')} --resume {task['id']}")
            return 0

    print(f"  未知 task action: {action}", file=sys.stderr)
    return 1
```

- [ ] **Step 4: 在 runner.py 注册 task 子命令**

读取 `src/dqg/core/runner.py`，在 `# --- ops: metrics / observe / regression ---` 注释区（约 L188）之后、`# metrics` 之前插入：

```python
    # task
    p_task = sub.add_parser("task", help="Task 管理（list/resume）")
    p_task.add_argument(
        "task_action", nargs="?", default="list", choices=["list", "resume"],
        help="操作（list: 列出 tasks；resume: 查找/显示可恢复 task）",
    )
    p_task.add_argument("task_id", nargs="?", default=None, help="Task ID（resume 指定 task 用）")
    p_task.add_argument(
        "--status", choices=["running", "completed", "failed", "all"], default="all",
        help="按状态过滤（list 用，默认 all）",
    )
    p_task.add_argument("--limit", type=int, default=20, help="最多返回条数（默认 20）")

```

在 `_dispatch` 函数（约 L293 的 ops 分支之后）追加：

```python
    if cmd == "task":
        from dqg.commands.task_cmd import cmd_task

        return cmd_task
```

- [ ] **Step 5: 运行测试确认通过**

```bash
python -m pytest tests/test_p1_ops_quality.py::test_cmd_task_list_returns_records \
  tests/test_p1_ops_quality.py::test_cmd_task_resume_no_tasks -v 2>&1 | tail -8
```
Expected: 2 PASSED

- [ ] **Step 6: 全量回归**

```bash
python -m pytest tests/ -x -q 2>&1 | tail -5
```
Expected: no new failures

- [ ] **Step 7: 提交**

```bash
git add src/dqg/commands/task_cmd.py src/dqg/core/runner.py tests/test_p1_ops_quality.py
git commit -m "feat(p1-5): task store CLI（dqg-run <pid> task list/resume）"
```

---

## Task 3：四类运营口径（P1-9）

**Files:**
- Modify: `src/dqg/reporting/telemetry.py:22-39`（PhaseRunRecord）
- Modify: `src/dqg/commands/phase.py:530-545`（cmd_approve telemetry）
- Modify: `src/dqg/reporting/observability.py:91-136, 405-427, 220-312`
- Test: `tests/test_p1_ops_quality.py`

- [ ] **Step 1: 写失败测试**

在 `tests/test_p1_ops_quality.py` 追加：

```python
# ---------------------------------------------------------------------------
# Task 3: 四类运营口径
# ---------------------------------------------------------------------------

def test_phase_run_record_has_force_approved_field():
    """PhaseRunRecord 应有 force_approved 字段，默认 False。"""
    from dqg.reporting.telemetry import PhaseRunRecord

    r = PhaseRunRecord(project_id="p1", phase_id="Q01", phase_name="需求分析", action="approve", status="approved")
    assert hasattr(r, "force_approved"), "PhaseRunRecord 缺少 force_approved 字段"
    assert r.force_approved is False


def test_closure_hours_computed(tmp_path):
    """_project_metrics 应计算 avg_closure_hours。"""
    from datetime import datetime, timezone, timedelta
    from dqg.reporting.telemetry import PhaseRunRecord
    from dqg.reporting.observability import _project_metrics

    now = datetime.now(timezone.utc)
    records = [
        PhaseRunRecord(
            project_id="p1", phase_id="Q01", phase_name="x", action="execute", status="ok",
            timestamp=(now - timedelta(hours=3)).isoformat(),
        ),
        PhaseRunRecord(
            project_id="p1", phase_id="Q01", phase_name="x", action="approve", status="approved",
            timestamp=now.isoformat(),
            force_approved=False,
        ),
    ]
    metrics = _project_metrics(tmp_path, "p1", records)
    assert "avg_closure_hours" in metrics
    assert metrics["avg_closure_hours"] >= 2.9  # 约 3 小时


def test_force_approve_rate_computed(tmp_path):
    """force_approve_rate 应等于 force_approved / total_approved。"""
    from dqg.reporting.telemetry import PhaseRunRecord
    from dqg.reporting.observability import _project_metrics

    records = [
        PhaseRunRecord(project_id="p1", phase_id="Q01", phase_name="x", action="approve", status="approved", force_approved=True),
        PhaseRunRecord(project_id="p1", phase_id="Q01", phase_name="x", action="approve", status="approved", force_approved=False),
    ]
    metrics = _project_metrics(tmp_path, "p1", records)
    assert metrics["force_approve_rate"] == 0.5


def test_generate_report_includes_guard_precision(tmp_path):
    """generate_report 的返回 payload 应含 guard_precision 字段。"""
    from datetime import date
    from dqg.reporting.observability import generate_report

    # 无记录也应能运行，payload 里有 guard_precision key
    try:
        payload, _, _ = generate_report(tmp_path, period_name="daily", anchor=date.today())
        assert "guard_precision" in payload
    except Exception as e:
        # 如果因为没有任何项目而抛异常，视为需要修改 generate_report 的 guard_precision 注入
        assert False, f"generate_report 抛出异常: {e}"
```

- [ ] **Step 2: 运行测试确认失败**

```bash
python -m pytest tests/test_p1_ops_quality.py::test_phase_run_record_has_force_approved_field \
  tests/test_p1_ops_quality.py::test_closure_hours_computed \
  tests/test_p1_ops_quality.py::test_force_approve_rate_computed \
  tests/test_p1_ops_quality.py::test_generate_report_includes_guard_precision -v 2>&1 | tail -10
```
Expected: 4 FAILED

- [ ] **Step 3: PhaseRunRecord 加 force_approved 字段**

读取 `src/dqg/reporting/telemetry.py`，在 `llm_calls` 字段之后（约 L39）追加：

```python
    force_approved: bool = False  # approve --force 时为 True，用于误报率统计
```

- [ ] **Step 4: cmd_approve 传 force_approved**

读取 `src/dqg/commands/phase.py`，找到 `append_record(` 调用（约 L534-545）：

```python
    append_record(
        output_dir,
        PhaseRunRecord(
            project_id=args.project_id,
            phase_id=args.phase,
            phase_name=PHASE_DEFS[args.phase]["name"],
            action="approve",
            status="approved",
            comment=comment,
        ),
    )
```

改为：

```python
    append_record(
        output_dir,
        PhaseRunRecord(
            project_id=args.project_id,
            phase_id=args.phase,
            phase_name=PHASE_DEFS[args.phase]["name"],
            action="approve",
            status="approved",
            comment=comment,
            force_approved=force,
        ),
    )
```

（`force` 变量在 `cmd_approve` 中已存在，来自 `force = getattr(args, "force", False)`）

- [ ] **Step 5: _project_metrics 加闭环时长和误报率**

读取 `src/dqg/reporting/observability.py`。

在 `_project_metrics` 函数（约 L91）中找到 `approve_records` 定义行（约 L93），在其下方追加：

```python
    # 闭环时长（execute → approve 时间差，小时）
    execute_records = [r for r in records if r.action == "execute"]
    closure_hours: list[float] = []
    for phase in ALLOWED_PHASES:
        first_exec = next((r for r in execute_records if r.phase_id == phase), None)
        last_approve = next(
            (r for r in reversed(approve_records) if r.phase_id == phase), None
        )
        if first_exec and last_approve and first_exec.timestamp and last_approve.timestamp:
            try:
                t0 = datetime.fromisoformat(first_exec.timestamp)
                t1 = datetime.fromisoformat(last_approve.timestamp)
                delta = (t1 - t0).total_seconds() / 3600
                if delta >= 0:
                    closure_hours.append(delta)
            except (ValueError, TypeError):
                pass
    avg_closure_hours = round(mean(closure_hours), 2) if closure_hours else 0.0

    # 误报率（force_approved / total_approved）
    force_count = sum(1 for r in approve_records if getattr(r, "force_approved", False))
    force_approve_rate = round(force_count / len(approve_records), 4) if approve_records else 0.0
```

在 `_project_metrics` 的 `return {...}` 里（约 L126）追加两个字段：

```python
        "avg_closure_hours": avg_closure_hours,
        "force_approve_rate": force_approve_rate,
```

- [ ] **Step 6: generate_report 加入 guard_precision**

读取 `observability.py`，在 `generate_report` 里找到 `payload["metric_anomalies"] = ...` 行（约 L423），在其之后插入：

```python
    try:
        from dqg.reporting.guard_precision_report import build_guard_precision_summary

        payload["guard_precision"] = build_guard_precision_summary(output_dir)
    except Exception:
        payload["guard_precision"] = {}
```

- [ ] **Step 7: _write_markdown_report 追加运营口径节**

读取 `observability.py`，找到 `_write_markdown_report` 末尾（约 L298-312），在 `path.write_text(...)` 之前插入：

```python
    # 运营口径节
    gp = payload.get("guard_precision", {})
    guard_rows = gp.get("guards", [])
    if guard_rows:
        lines += [
            "",
            "## 运营口径",
            "",
            "### Guard 精度",
            "",
            "| Guard | 执行 | 通过 | 阻断 | 命中率 |",
            "| --- | ---: | ---: | ---: | ---: |",
        ]
        for g in guard_rows:
            total = g.get("total", 0)
            blocked = g.get("blocked", 0)
            hit_rate = blocked / total if total > 0 else 0.0
            lines.append(
                f"| {g.get('name', '?')} | {total} | {g.get('passed', 0)} | {blocked} | {hit_rate:.2%} |"
            )

    has_closure = any(r.get("avg_closure_hours", 0) > 0 for r in payload.get("projects", []))
    if has_closure:
        lines += [
            "",
            "### Phase 运营（闭环时长 / 误报率）",
            "",
            "| Project | 平均闭环时长(h) | Force Approve 率 |",
            "| --- | ---: | ---: |",
        ]
        for item in payload.get("projects", []):
            lines.append(
                f"| {item['project_id']} | {item.get('avg_closure_hours', 0):.2f} | "
                f"{item.get('force_approve_rate', 0):.2%} |"
            )
```

- [ ] **Step 8: 运行测试确认通过**

```bash
python -m pytest tests/test_p1_ops_quality.py -v 2>&1 | tail -15
```
Expected: 7 PASSED (Tasks 1+2+3 全部)

- [ ] **Step 9: 全量回归**

```bash
python -m pytest tests/ -q 2>&1 | tail -5
```
Expected: no new failures（`test_file_line_limit` 预存在，忽略）

- [ ] **Step 10: 提交**

```bash
git add src/dqg/reporting/telemetry.py src/dqg/commands/phase.py \
        src/dqg/reporting/observability.py tests/test_p1_ops_quality.py
git commit -m "feat(p1-9): 四类运营口径——闭环时长/误报率/Guard精度接入 observe 报告"
```

---

## Self-Review

**Spec coverage:**

| Spec 要求 | Task |
|-----------|------|
| ExecutionContext.strict_profile_context | Task 1 Step 3 |
| finalize --strict-profile-context argparse | Task 1 Step 5 |
| handle_profile_context_check BLOCKED 升级 | Task 1 Step 4 |
| cmd_task list（显示 task runs） | Task 2 Step 3 |
| cmd_task resume（显示 checkpoint 信息） | Task 2 Step 3 |
| runner.py task 子命令注册 | Task 2 Step 4 |
| PhaseRunRecord.force_approved | Task 3 Step 3 |
| cmd_approve 传 force_approved | Task 3 Step 4 |
| _project_metrics avg_closure_hours | Task 3 Step 5 |
| _project_metrics force_approve_rate | Task 3 Step 5 |
| generate_report guard_precision | Task 3 Step 6 |
| _write_markdown_report 运营口径节 | Task 3 Step 7 |
| 7 条单测 | Tasks 1-3 |

**No placeholders:** 所有步骤有完整代码。

**Type consistency:**
- `strict_profile_context: bool` 在 Task 1 Step 3 定义，在 Step 4（handler）和 Step 6（cmd_finalize）使用，类型一致。
- `force_approved: bool = False` 在 Task 3 Step 3 定义，在 Step 4（cmd_approve）传 `force_approved=force`（`force` 是 `bool`），一致。
- `avg_closure_hours: float`、`force_approve_rate: float` 在 Task 3 Step 5 定义，在 Step 7（_write_markdown_report）作为 `item.get(...)` 读取，一致。
