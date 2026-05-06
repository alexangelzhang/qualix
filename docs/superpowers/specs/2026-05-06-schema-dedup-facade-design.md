# Phase Schema 文件去重 Facade 设计文档

**日期：** 2026-05-06
**状态：** 已批准
**范围：** `src/dqg/schemas/` 下 7 对重复的 phase schema 文件

## 背景

`src/dqg/schemas/` 存在 14 个 phase schema 文件，分两套命名：
- 旧命名：`phase_a.py` / `phase_a3.py` / `phase_a5.py` / `phase_a6.py` / `phase_b.py` / `phase_c.py` / `phase_d.py`
- 新命名：`phase_q01.py` ~ `phase_q07.py`

经 diff 比对，7 对文件内容 **100% 相同**（共 525 行代码重复）。调用方散落在 `src/` 和 `tests/` 中，两套 import 路径并存。`auto_checks.py` 用旧命名，`schemas/__init__.py` 用新命名。

目标：消除代码重复源头，保留向后兼容，后续逐步迁移调用方。

## 方案：Facade 改造

### 文件改造规则

7 个旧文件全部替换为 re-export facade，每个文件内容如下：

```python
"""Facade: re-export from phase_qXX.py (kept for backward compatibility).

本文件保留是为了向后兼容旧 import 路径，新代码请直接使用 phase_qXX.py。
"""
from dqg.schemas.phase_qXX import *  # noqa: F401, F403
```

对应关系：

| 旧文件 | 新文件 |
|--------|--------|
| `phase_a.py`  | `phase_q01.py` |
| `phase_a3.py` | `phase_q02.py` |
| `phase_a6.py` | `phase_q03.py` |
| `phase_a5.py` | `phase_q04.py` |
| `phase_b.py`  | `phase_q05.py` |
| `phase_c.py`  | `phase_q06.py` |
| `phase_d.py`  | `phase_q07.py` |

### `auto_checks.py` `_SCHEMA_MAP` 更新

把 `_SCHEMA_MAP` 从旧命名改为新命名，统一规范：

```python
_SCHEMA_MAP: Final = MappingProxyType(
    {
        "Q01": "dqg.schemas.phase_q01:PhaseAOutput",
        "Q02": "dqg.schemas.phase_q02:PhaseA3Output",
        "Q03": "dqg.schemas.phase_q03:PhaseA6Output",
        "Q04": "dqg.schemas.phase_q04:PhaseA5Output",
        "Q05": "dqg.schemas.phase_q05:PhaseBOutput",
        "Q06": "dqg.schemas.phase_q06:PhaseCOutput",
        "Q07": "dqg.schemas.phase_q07:PhaseDOutput",
    }
)
```

## 验证策略

### 等价性测试（`tests/test_schema_facade.py`）

7 对 facade 每对至少 1 个测试，验证：

1. **Import 兼容性**：`from dqg.schemas.phase_X import <class>` 不抛异常
2. **对象等价性**：`dqg.schemas.phase_b.EutItem is dqg.schemas.phase_q05.EutItem`
3. **字段等价性**：旧路径构造的实例和新路径构造的实例字段完全一致

### 全量验证

- `python -m pytest tests/ --tb=short`：0 regression
- `python -m ruff check src/ tests/`：lint 通过

## 改动文件清单

| 文件 | 操作 |
|------|------|
| `src/dqg/schemas/phase_a.py` | 完全覆盖为 facade |
| `src/dqg/schemas/phase_a3.py` | 完全覆盖为 facade |
| `src/dqg/schemas/phase_a5.py` | 完全覆盖为 facade |
| `src/dqg/schemas/phase_a6.py` | 完全覆盖为 facade |
| `src/dqg/schemas/phase_b.py` | 完全覆盖为 facade |
| `src/dqg/schemas/phase_c.py` | 完全覆盖为 facade |
| `src/dqg/schemas/phase_d.py` | 完全覆盖为 facade |
| `src/dqg/quality/checks/auto_checks.py` | 修改 `_SCHEMA_MAP` 指向新命名 |
| `tests/test_schema_facade.py` | 新建 facade 等价性测试 |

## Out of Scope

- 不批量迁移调用方的 import 路径（facade 保证兼容，迁移作为后续任务）
- 不删除旧文件
- 不新增新字段或功能
- 不改 skill 文件、spec 文件、计划文件
- 不改 `schemas/__init__.py`（已指向新命名）

## 风险与缓解

| 风险 | 缓解 |
|------|------|
| `from X import *` 不导出下划线开头的私有符号 | 现有调用方只用公开类，不依赖私有常量 |
| facade 使私有常量在旧文件不可见 | 等价性测试验证所有公开 API 可用 |
| `_SCHEMA_MAP` 改动影响 finalize gate | 回归测试全量 623+ 测试验证 |
