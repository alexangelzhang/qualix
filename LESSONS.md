# Qualix 项目经验教训

## Entries

### BL-20260525-python-local-import-scoping

- **Scope**: src/qualix/runtime/phase_runtime.py, 任何在函数体内 import 的场景
- **Trigger**: 在函数体内写 `from module import NAME`，而函数前部已经在用同名的模块级变量
- **Do**: 用不同的别名（`as _local_alias`）或直接复用已有的模块级导入；不要在函数中 re-import 已有的顶层符号
- **Why**: Python 字节码编译器一旦在函数体内看到 `from X import NAME`，就把整个函数所有 `NAME` 的引用都视为 local variable，包括 import 语句之前的行——导致 `UnboundLocalError`
- **Evidence**: `test_phase_execute_weak_assert.py` 因为 Defer-A2 在 runtime_execute() 里写了 `from qualix.core.state_machine import PHASE_DEFS, phase_dir as _pd`，导致第 96 行 `PHASE_DEFS[ctx.phase_id]`（该行在 import 前）抛 UnboundLocalError。修复：改用 `phase_dir` 的模块级别名 `_phase_dir`，去掉 `PHASE_DEFS` 的 local import。

### BL-20260525-qualix-gitignore

- **Scope**: 项目根目录 `.qualix/` 目录
- **Trigger**: 想把示例配置文件（如 `rule_overrides.yaml.example`）放到 `.qualix/` 里版本控制
- **Do**: 示例文件放 `docs/examples/` 或在 AGENTS.md/ROADMAP.md 里以代码块形式说明格式；不要放 `.qualix/`
- **Why**: `.qualix/` 在 .gitignore 里（存运行时状态和本地配置），git add 会报 ignored 错误
- **Evidence**: `git add qualix/.qualix/rule_overrides.yaml.example` 报 `The following paths are ignored by one of your .gitignore files`

### BL-20260525-file-split-range-overlap

- **Scope**: 任何用 Python extract(start, end) 脚本拆分大文件的场景
- **Trigger**: 生成多个 extract() 调用时，其中某段的范围覆盖了另一段已有的范围
- **Do**: 写完提取脚本后，用 `ast.parse()` 扫描输出文件，检查是否有重复的函数名（`Counter(funcs) > 1`）；拆分前先画出不重叠的行范围区间
- **Why**: 两个 `extract(1436, 1581)` + `extract(1483, 1548)` 导致函数被重复定义（F811），ruff pre-commit 才发现
- **Evidence**: _checks_production.py 里 `check_eut_then_phantom_methods` 出现两次，commit d0dd2cf7 之前的 ruff 报 F811

### BL-20260525-constant-between-functions

- **Scope**: 拆分包含散落在函数间的模块级常量的大 Python 文件
- **Trigger**: 按行范围拆分，把某个函数移到 file_B，但该函数依赖的常量（如 `_INJECT_MOCKS_PATTERN` 在 L479）已经随另一个行范围去了 file_A
- **Do**: 拆分后对每个子文件运行 `python -c "from module import *"` 不够，要用实际测试用例触发函数体内的 NameError；或先用静态分析找所有引用 `_UPPER_CASE` 名字但未在本文件定义/导入的情况
- **Why**: import 阶段不报错，但函数调用时 NameError（常量是运行时绑定的名字）
- **Evidence**: `_INJECT_MOCKS_PATTERN` 在 eut_basic.py（L479）但被 eut_alignment.py 里的 `_check_test_file_eut_reverse` 使用，import 通过、运行失败
