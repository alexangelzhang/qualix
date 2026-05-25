# DQG 项目经验教训

## Entries

### BL-20260525-python-local-import-scoping

- **Scope**: src/dqg/runtime/phase_runtime.py, 任何在函数体内 import 的场景
- **Trigger**: 在函数体内写 `from module import NAME`，而函数前部已经在用同名的模块级变量
- **Do**: 用不同的别名（`as _local_alias`）或直接复用已有的模块级导入；不要在函数中 re-import 已有的顶层符号
- **Why**: Python 字节码编译器一旦在函数体内看到 `from X import NAME`，就把整个函数所有 `NAME` 的引用都视为 local variable，包括 import 语句之前的行——导致 `UnboundLocalError`
- **Evidence**: `test_phase_execute_weak_assert.py` 因为 Defer-A2 在 runtime_execute() 里写了 `from dqg.core.state_machine import PHASE_DEFS, phase_dir as _pd`，导致第 96 行 `PHASE_DEFS[ctx.phase_id]`（该行在 import 前）抛 UnboundLocalError。修复：改用 `phase_dir` 的模块级别名 `_phase_dir`，去掉 `PHASE_DEFS` 的 local import。

### BL-20260525-dqg-gitignore

- **Scope**: 项目根目录 `.dqg/` 目录
- **Trigger**: 想把示例配置文件（如 `rule_overrides.yaml.example`）放到 `.dqg/` 里版本控制
- **Do**: 示例文件放 `docs/examples/` 或在 AGENTS.md/ROADMAP.md 里以代码块形式说明格式；不要放 `.dqg/`
- **Why**: `.dqg/` 在 .gitignore 里（存运行时状态和本地配置），git add 会报 ignored 错误
- **Evidence**: `git add dev-quality-gate/.dqg/rule_overrides.yaml.example` 报 `The following paths are ignored by one of your .gitignore files`
