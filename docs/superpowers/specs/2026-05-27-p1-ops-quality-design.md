# P1 运营质量三件套设计文档

**日期**: 2026-05-27  
**状态**: 待实施  
**对应 ROADMAP**: P1-8 strict-profile-context / P1-5 Task CLI / P1-9 运营口径

---

## 范围

| 子项目 | 主要文件 | 估算 |
|--------|---------|------|
| P1-8 strict-profile-context | `execution_context.py`, `handlers_finalize.py`, `phase.py` | 1h |
| P1-5 Task store CLI | `commands/task_cmd.py`（新建）, `core/cli.py` | 2h |
| P1-9 四类运营口径 | `telemetry.py`, `observability.py`, `phase.py` | 2.5h |

---

## P1-8：`--strict-profile-context` 严格模式

### 背景

`handle_profile_context_check` 当前两处 `result.add_warning(...)`：
- 缺少 `_profile_context.md` 文件
- 报告缺少 `PROFILE_CONTEXT` section

Warning 不阻断 approve，不能接 CI 门禁。加 `--strict-profile-context` flag 后升级为 BLOCKED。

### 设计

**ExecutionContext** (`src/dqg/runtime/execution_context.py`):

```python
strict_profile_context: bool = False   # 新增字段
```

**cmd_finalize** (`src/dqg/commands/phase.py`)，在 finalize 子命令的 argparse 里追加：

```python
parser_finalize.add_argument(
    "--strict-profile-context",
    action="store_true",
    default=False,
    help="严格模式：报告缺少 PROFILE_CONTEXT 时阻断 finalize（默认 WARNING）",
)
```

在 `cmd_finalize` 构造 `ExecutionContext` 时传入：

```python
ctx.strict_profile_context = getattr(args, "strict_profile_context", False)
```

**handle_profile_context_check** (`handlers_finalize.py` L228-248)，将两处 `result.add_warning(...)` 改为：

```python
_msg_missing_file = f"PROFILE_CONTEXT 文件缺失: {profile_ctx_path}"
_msg_missing_section = "报告缺少 PROFILE_CONTEXT 章节"

if ctx.strict_profile_context:
    result.errors.append(f"BLOCKED: [profile_context] {_msg_missing_file}")  # or section
else:
    result.add_warning(_msg_missing_file)
```

错误字符串以 `BLOCKED:` 前缀进入 `result.errors`，由 `build_verdict()` 转为 `CheckItem(level=HARD, source="handler", name="profile_context")`。

### 验收
- `finalize` 无 flag → WARNING（不阻断）
- `finalize --strict-profile-context` 且报告缺 PROFILE_CONTEXT → BLOCKED，approve 被拒

---

## P1-5：Task store CLI

### 背景

`task_store.py` 已有 `list_task_runs`、`get_resumable_task`、`get_latest_checkpoint`、`replay_from_checkpoint`，但没有 CLI 入口。

### 设计

**新文件** `src/dqg/commands/task_cmd.py`：

```python
def cmd_task_list(args, output_dir: Path) -> int:
    """qualix-run <pid> task list [--status STATUS] [--limit N] [--json]"""

def cmd_task_resume(args, output_dir: Path) -> int:
    """qualix-run <pid> task resume [task_id] [--json]
    
    无 task_id → 调 get_resumable_task 找可恢复任务
    有 task_id → 调 get_latest_checkpoint 取最新 checkpoint
    """
```

**输出格式**（--json 模式复用 `cli_envelope`）：

`task list` 普通模式：

```
TASK_ID        TYPE       PROJECT  PHASE  STATUS     STARTED
abc123def...   adaptive   proj1    Q05    running    2026-05-27T10:00
...
```

`task resume`（无 task_id）：

```
可恢复任务: abc123def...
  类型: adaptive  项目: proj1  Phase: Q05
  最新 checkpoint: iter_3 (2026-05-27T10:30)
  恢复命令: qualix-run proj1 adaptive Q05 --resume abc123def...
```

**注册到 core/cli.py** (`main()` 里的 subparser 区)：

```python
# task 子命令
sp_task = subparsers.add_parser("task", help="Task 管理（list/resume）")
task_sub = sp_task.add_subparsers(dest="task_action")

sp_task_list = task_sub.add_parser("list", help="列出 task runs")
sp_task_list.add_argument("--status", choices=["running","completed","failed","all"], default="all")
sp_task_list.add_argument("--limit", type=int, default=20)
sp_task_list.add_argument("--json", action="store_true")

sp_task_resume = task_sub.add_parser("resume", help="查找/显示可恢复 task")
sp_task_resume.add_argument("task_id", nargs="?", default=None)
sp_task_resume.add_argument("--json", action="store_true")
```

`_base_dir()` 和 `_output_dir()` 全局函数已在 `core/cli.py` 里，`task_cmd.py` 直接用 `task_store.py` 的函数。

### 验收
- `qualix-run proj1 task list` → 表格显示 task runs
- `qualix-run proj1 task list --status running --json` → JSON 格式
- `qualix-run proj1 task resume` → 显示可恢复 task 的 checkpoint 信息

---

## P1-9：四类运营口径

### 背景

`observability.py::_project_metrics` 已有 `phase_approval_rate`、`avg_duration_seconds`，但缺：
- 闭环时长（execute→approve 时间差）
- 误报率（force approve 占比）
- Guard 精度（命中率）未接入 observe 报告

### 设计

#### A. PhaseRunRecord 加 force_approved 字段

`src/dqg/reporting/telemetry.py::PhaseRunRecord` 新增：

```python
force_approved: bool = False   # approve --force 时为 True
```

`cmd_approve` (`phase.py`) 在 `append_record(...)` 调用时传入：

```python
PhaseRunRecord(
    ...,
    action="approve",
    status="approved",
    force_approved=force,
    comment=comment,
)
```

#### B. _project_metrics 增加闭环时长 + 误报率

在 `observability.py::_project_metrics` 里：

```python
# 闭环时长：每个 Phase 首次 execute.timestamp → approve.timestamp（小时）
execute_records = [r for r in records if r.action == "execute"]
closure_hours: list[float] = []
for phase in ALLOWED_PHASES:
    first_exec = next((r for r in execute_records if r.phase_id == phase), None)
    last_approve = next((r for r in reversed(approve_records) if r.phase_id == phase), None)
    if first_exec and last_approve:
        try:
            t0 = datetime.fromisoformat(first_exec.timestamp)
            t1 = datetime.fromisoformat(last_approve.timestamp)
            delta_hours = (t1 - t0).total_seconds() / 3600
            if delta_hours >= 0:
                closure_hours.append(delta_hours)
        except (ValueError, TypeError):
            pass

avg_closure_hours = round(mean(closure_hours), 2) if closure_hours else 0.0

# 误报率：force_approved / total_approved
force_count = sum(1 for r in approve_records if getattr(r, "force_approved", False))
force_approve_rate = round(force_count / len(approve_records), 4) if approve_records else 0.0
```

在 `_project_metrics` 返回字典追加：
```python
"avg_closure_hours": avg_closure_hours,
"force_approve_rate": force_approve_rate,
```

#### C. generate_report 加入 guard_precision

`observability.py::generate_report` 返回的 payload 中追加：

```python
from dqg.reporting.guard_precision_report import build_guard_precision_summary
guard_precision = build_guard_precision_summary(output_dir)
payload["guard_precision"] = guard_precision
```

#### D. _write_markdown_report 增加运营口径节

在现有 Markdown 报告末尾追加「运营口径」节：

```markdown
## 运营口径

### Guard 精度
| Guard | 触发次数 | 通过 | 阻断 | 命中率 |
...（来自 guard_precision）

### Phase 运营
| Phase | 通过率 | 闭环时长(h) | Force 率 |
...（来自 phase_stats + avg_closure_hours + force_approve_rate）
```

---

## 测试计划

| 测试 | 覆盖点 |
|------|--------|
| `test_strict_profile_context_blocks` | 严格模式下 BLOCKED |
| `test_no_strict_warns_only` | 非严格模式下仍是 WARNING |
| `test_cmd_task_list_returns_records` | task list 返回已有 runs |
| `test_cmd_task_resume_no_id_finds_resumable` | resume 无 id 返回可恢复 task |
| `test_closure_hours_computed` | execute/approve 时间差计算正确 |
| `test_force_approve_rate` | force_approved=True 的比率计算 |
| `test_generate_report_includes_guard_precision` | observe 报告含 guard_precision 字段 |
