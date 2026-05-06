# Phase Schema 文件去重 Facade Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 消除 `src/dqg/schemas/` 下 7 对重复的 phase schema 文件，旧文件改造为 re-export facade，保持向后兼容。

**Architecture:** 7 个旧文件（`phase_a`/`phase_a3`/`phase_a5`/`phase_a6`/`phase_b`/`phase_c`/`phase_d`）被完全覆盖为 3 行 facade，从对应的 `phase_qXX.py` re-export。`auto_checks.py` 的 `_SCHEMA_MAP` 同步更新到新命名。新增 facade 等价性测试保证调用方不破坏。

**Tech Stack:** Python 3.11+, Pydantic v2, pytest

---

## 文件清单

| 文件 | 操作 |
|------|------|
| `src/dqg/schemas/phase_a.py` | 完全覆盖为 facade |
| `src/dqg/schemas/phase_a3.py` | 完全覆盖为 facade |
| `src/dqg/schemas/phase_a5.py` | 完全覆盖为 facade |
| `src/dqg/schemas/phase_a6.py` | 完全覆盖为 facade |
| `src/dqg/schemas/phase_b.py` | 完全覆盖为 facade |
| `src/dqg/schemas/phase_c.py` | 完全覆盖为 facade |
| `src/dqg/schemas/phase_d.py` | 完全覆盖为 facade |
| `src/dqg/quality/checks/auto_checks.py` | 修改 `_SCHEMA_MAP` |
| `tests/test_schema_facade.py` | 新建 facade 等价性测试 |

---

## Task 1: 新建 facade 等价性测试

**Files:**
- Create: `tests/test_schema_facade.py`

- [ ] **Step 1: 写失败测试**

新建 `tests/test_schema_facade.py`：

```python
"""Facade 等价性测试：旧命名 phase_[a-d] 应与新命名 phase_qXX 等价."""


class TestFacadeEquivalence:
    def test_phase_a_equivalent_to_phase_q01(self):
        from dqg.schemas import phase_a, phase_q01

        assert phase_a.PhaseAOutput is phase_q01.PhaseAOutput

    def test_phase_a3_equivalent_to_phase_q02(self):
        from dqg.schemas import phase_a3, phase_q02

        assert phase_a3.PhaseA3Output is phase_q02.PhaseA3Output

    def test_phase_a6_equivalent_to_phase_q03(self):
        from dqg.schemas import phase_a6, phase_q03

        assert phase_a6.PhaseA6Output is phase_q03.PhaseA6Output

    def test_phase_a5_equivalent_to_phase_q04(self):
        from dqg.schemas import phase_a5, phase_q04

        assert phase_a5.PhaseA5Output is phase_q04.PhaseA5Output

    def test_phase_b_equivalent_to_phase_q05(self):
        from dqg.schemas import phase_b, phase_q05

        assert phase_b.PhaseBOutput is phase_q05.PhaseBOutput
        assert phase_b.EutItem is phase_q05.EutItem
        assert phase_b.TCItem is phase_q05.TCItem

    def test_phase_c_equivalent_to_phase_q06(self):
        from dqg.schemas import phase_c, phase_q06

        assert phase_c.PhaseCOutput is phase_q06.PhaseCOutput
        assert phase_c.EutAuditItem is phase_q06.EutAuditItem
        assert phase_c.FindingItem is phase_q06.FindingItem

    def test_phase_d_equivalent_to_phase_q07(self):
        from dqg.schemas import phase_d, phase_q07

        assert phase_d.PhaseDOutput is phase_q07.PhaseDOutput


class TestOldImportPathsStillWork:
    def test_phase_b_import_still_works(self):
        from dqg.schemas.phase_b import EutItem, PhaseBOutput, TCItem

        assert EutItem.__name__ == "EutItem"
        assert TCItem.__name__ == "TCItem"
        assert PhaseBOutput.__name__ == "PhaseBOutput"

    def test_phase_c_import_still_works(self):
        from dqg.schemas.phase_c import EutAuditItem, FindingItem, PhaseCOutput

        assert EutAuditItem.__name__ == "EutAuditItem"
        assert FindingItem.__name__ == "FindingItem"
        assert PhaseCOutput.__name__ == "PhaseCOutput"
```

- [ ] **Step 2: 运行测试，确认当前通过**

```bash
cd /Users/zhangyiqian/git_dev/dev-quality-gate/dev-quality-gate
python -m pytest tests/test_schema_facade.py -v
```

期望：除`TestFacadeEquivalence` 7 个测试全部 FAIL（因为旧文件是独立副本，不 `is` 等价），`TestOldImportPathsStillWork` 2 个测试 PASS（现有旧文件有这些类）

- [ ] **Step 3: Commit（测试先行）**

```bash
git add tests/test_schema_facade.py
git commit -m "test: facade equivalence tests for phase schemas"
```

---

## Task 2: `phase_a` → facade

**Files:**
- Modify: `src/dqg/schemas/phase_a.py`

- [ ] **Step 1: 完全覆盖 `phase_a.py` 为 facade**

```python
"""Facade: re-export from phase_q01.py (kept for backward compatibility).

本文件保留是为了向后兼容旧 import 路径，新代码请直接使用 phase_q01.py。
"""

from dqg.schemas.phase_q01 import *  # noqa: F401, F403
```

- [ ] **Step 2: 运行 facade 等价性测试验证**

```bash
python -m pytest tests/test_schema_facade.py::TestFacadeEquivalence::test_phase_a_equivalent_to_phase_q01 -v
```

期望：PASS

- [ ] **Step 3: 运行 TestOldImportPathsStillWork 确认兼容性**

```bash
python -m pytest tests/test_schema_facade.py::TestOldImportPathsStillWork -v
```

期望：2 个测试全部 PASS

- [ ] **Step 4: 全量测试确认无回归**

```bash
python -m pytest tests/ --tb=short 2>&1 | tail -5
```

期望：所有原有测试 PASS

- [ ] **Step 5: Commit**

```bash
git add src/dqg/schemas/phase_a.py
git commit -m "refactor: phase_a.py → facade re-export from phase_q01"
```

---

## Task 3: `phase_a3` → facade

**Files:**
- Modify: `src/dqg/schemas/phase_a3.py`

- [ ] **Step 1: 完全覆盖 `phase_a3.py` 为 facade**

```python
"""Facade: re-export from phase_q02.py (kept for backward compatibility).

本文件保留是为了向后兼容旧 import 路径，新代码请直接使用 phase_q02.py。
"""

from dqg.schemas.phase_q02 import *  # noqa: F401, F403
```

- [ ] **Step 2: 运行 facade 等价性测试验证**

```bash
python -m pytest tests/test_schema_facade.py::TestFacadeEquivalence::test_phase_a3_equivalent_to_phase_q02 -v
```

期望：PASS

- [ ] **Step 3: 全量测试**

```bash
python -m pytest tests/ --tb=short 2>&1 | tail -5
```

期望：所有测试 PASS

- [ ] **Step 4: Commit**

```bash
git add src/dqg/schemas/phase_a3.py
git commit -m "refactor: phase_a3.py → facade re-export from phase_q02"
```

---

## Task 4: `phase_a6` → facade

**Files:**
- Modify: `src/dqg/schemas/phase_a6.py`

- [ ] **Step 1: 完全覆盖 `phase_a6.py` 为 facade**

```python
"""Facade: re-export from phase_q03.py (kept for backward compatibility).

本文件保留是为了向后兼容旧 import 路径，新代码请直接使用 phase_q03.py。
"""

from dqg.schemas.phase_q03 import *  # noqa: F401, F403
```

- [ ] **Step 2: 运行 facade 等价性测试验证**

```bash
python -m pytest tests/test_schema_facade.py::TestFacadeEquivalence::test_phase_a6_equivalent_to_phase_q03 -v
```

期望：PASS

- [ ] **Step 3: 全量测试**

```bash
python -m pytest tests/ --tb=short 2>&1 | tail -5
```

期望：所有测试 PASS

- [ ] **Step 4: Commit**

```bash
git add src/dqg/schemas/phase_a6.py
git commit -m "refactor: phase_a6.py → facade re-export from phase_q03"
```

---

## Task 5: `phase_a5` → facade

**Files:**
- Modify: `src/dqg/schemas/phase_a5.py`

- [ ] **Step 1: 完全覆盖 `phase_a5.py` 为 facade**

```python
"""Facade: re-export from phase_q04.py (kept for backward compatibility).

本文件保留是为了向后兼容旧 import 路径，新代码请直接使用 phase_q04.py。
"""

from dqg.schemas.phase_q04 import *  # noqa: F401, F403
```

- [ ] **Step 2: 运行 facade 等价性测试验证**

```bash
python -m pytest tests/test_schema_facade.py::TestFacadeEquivalence::test_phase_a5_equivalent_to_phase_q04 -v
```

期望：PASS

- [ ] **Step 3: 全量测试**

```bash
python -m pytest tests/ --tb=short 2>&1 | tail -5
```

期望：所有测试 PASS

- [ ] **Step 4: Commit**

```bash
git add src/dqg/schemas/phase_a5.py
git commit -m "refactor: phase_a5.py → facade re-export from phase_q04"
```

---

## Task 6: `phase_b` → facade

**Files:**
- Modify: `src/dqg/schemas/phase_b.py`

- [ ] **Step 1: 完全覆盖 `phase_b.py` 为 facade**

```python
"""Facade: re-export from phase_q05.py (kept for backward compatibility).

本文件保留是为了向后兼容旧 import 路径，新代码请直接使用 phase_q05.py。
"""

from dqg.schemas.phase_q05 import *  # noqa: F401, F403
```

- [ ] **Step 2: 运行 facade 等价性测试验证**

```bash
python -m pytest tests/test_schema_facade.py::TestFacadeEquivalence::test_phase_b_equivalent_to_phase_q05 tests/test_schema_facade.py::TestOldImportPathsStillWork::test_phase_b_import_still_works -v
```

期望：2 个测试全部 PASS

- [ ] **Step 3: 全量测试**

```bash
python -m pytest tests/ --tb=short 2>&1 | tail -5
```

期望：所有测试 PASS

- [ ] **Step 4: Commit**

```bash
git add src/dqg/schemas/phase_b.py
git commit -m "refactor: phase_b.py → facade re-export from phase_q05"
```

---

## Task 7: `phase_c` → facade

**Files:**
- Modify: `src/dqg/schemas/phase_c.py`

- [ ] **Step 1: 完全覆盖 `phase_c.py` 为 facade**

```python
"""Facade: re-export from phase_q06.py (kept for backward compatibility).

本文件保留是为了向后兼容旧 import 路径，新代码请直接使用 phase_q06.py。
"""

from dqg.schemas.phase_q06 import *  # noqa: F401, F403
```

- [ ] **Step 2: 运行 facade 等价性测试验证**

```bash
python -m pytest tests/test_schema_facade.py::TestFacadeEquivalence::test_phase_c_equivalent_to_phase_q06 tests/test_schema_facade.py::TestOldImportPathsStillWork::test_phase_c_import_still_works -v
```

期望：2 个测试全部 PASS

- [ ] **Step 3: 全量测试**

```bash
python -m pytest tests/ --tb=short 2>&1 | tail -5
```

期望：所有测试 PASS

- [ ] **Step 4: Commit**

```bash
git add src/dqg/schemas/phase_c.py
git commit -m "refactor: phase_c.py → facade re-export from phase_q06"
```

---

## Task 8: `phase_d` → facade

**Files:**
- Modify: `src/dqg/schemas/phase_d.py`

- [ ] **Step 1: 完全覆盖 `phase_d.py` 为 facade**

```python
"""Facade: re-export from phase_q07.py (kept for backward compatibility).

本文件保留是为了向后兼容旧 import 路径，新代码请直接使用 phase_q07.py。
"""

from dqg.schemas.phase_q07 import *  # noqa: F401, F403
```

- [ ] **Step 2: 运行 facade 等价性测试验证**

```bash
python -m pytest tests/test_schema_facade.py::TestFacadeEquivalence::test_phase_d_equivalent_to_phase_q07 -v
```

期望：PASS

- [ ] **Step 3: 全量测试**

```bash
python -m pytest tests/ --tb=short 2>&1 | tail -5
```

期望：所有测试 PASS

- [ ] **Step 4: Commit**

```bash
git add src/dqg/schemas/phase_d.py
git commit -m "refactor: phase_d.py → facade re-export from phase_q07"
```

---

## Task 9: 更新 `auto_checks.py` `_SCHEMA_MAP`

**Files:**
- Modify: `src/dqg/quality/checks/auto_checks.py`

- [ ] **Step 1: 修改 `_SCHEMA_MAP` 指向新命名**

在 `src/dqg/quality/checks/auto_checks.py` 第 32-42 行附近，把 `_SCHEMA_MAP` 替换为：

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

- [ ] **Step 2: 全量测试**

```bash
python -m pytest tests/ --tb=short 2>&1 | tail -5
```

期望：所有测试 PASS（包括 `test_auto_checks.py` 和 `test_lineage_tracking.py::TestLocationGate`）

- [ ] **Step 3: Commit**

```bash
git add src/dqg/quality/checks/auto_checks.py
git commit -m "refactor: auto_checks _SCHEMA_MAP → phase_qXX naming"
```

---

## Task 10: 最终验证 + Ruff lint

- [ ] **Step 1: 全量 pytest**

```bash
python -m pytest tests/ --tb=short
```

期望：所有测试 PASS，无新增失败

- [ ] **Step 2: Ruff lint**

```bash
python -m ruff check src/dqg/schemas/ src/dqg/quality/checks/auto_checks.py tests/test_schema_facade.py
```

期望：无 lint 错误

- [ ] **Step 3: 如有 lint 错误，修复后重新运行**

```bash
python -m ruff check --fix src/dqg/schemas/ src/dqg/quality/checks/auto_checks.py tests/test_schema_facade.py
python -m pytest tests/ --tb=short 2>&1 | tail -5
```

- [ ] **Step 4: 最终 commit（如有 lint 修复）**

```bash
git add -p
git commit -m "fix: ruff lint for schema facade refactor"
```
