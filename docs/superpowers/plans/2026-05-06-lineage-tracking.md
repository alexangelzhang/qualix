# 行级血缘追踪 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 Q05/Q06 的每条审计判定和测试用例附加结构化双坐标（测试代码位置 + 被测生产代码位置），同时服务于人工 review 和自动修复 agent。

**Architecture:** 新增共享 `SourceLocation` Pydantic 模型，在 Q05 `TCItem` 和 Q06 `EutAuditItem`/`FindingItem` 上追加两个可选字段。Finalize gate 在 `auto_checks.py` 追加校验规则：COVERED 判定缺少 `test_location` 时降级为 PARTIAL。Skill prompt 更新 JSON 格式示例并新增 IRON LAW。

**Tech Stack:** Python 3.11+, Pydantic v2, pytest

---

## 文件清单

| 文件 | 操作 |
|------|------|
| `src/dqg/schemas/location.py` | 新建 |
| `src/dqg/schemas/__init__.py` | 修改（导出 `SourceLocation`） |
| `src/dqg/schemas/phase_q05.py` | 修改（`TCItem` 加两个可选字段） |
| `src/dqg/schemas/phase_q06.py` | 修改（`EutAuditItem`、`FindingItem` 加字段） |
| `src/dqg/quality/checks/auto_checks.py` | 修改（追加 location 校验规则） |
| `skills/unit-test-generation/SKILL.md` | 修改（JSON 示例 + IRON LAW） |
| `skills/unit-test-audit/SKILL.md` | 修改（JSON 示例 + IRON LAW） |
| `tests/test_lineage_tracking.py` | 新建 |

---

## Task 1: 新建 `SourceLocation` 模型

**Files:**
- Create: `src/dqg/schemas/location.py`
- Test: `tests/test_lineage_tracking.py`

- [ ] **Step 1: 写失败测试**

新建 `tests/test_lineage_tracking.py`：

```python
"""Tests for SourceLocation model."""
import pytest
from pydantic import ValidationError
from dqg.schemas.location import SourceLocation


class TestSourceLocation:

    def test_minimal_valid(self):
        loc = SourceLocation(file="OrderServiceTest.java", line_start=45)
        assert loc.file == "OrderServiceTest.java"
        assert loc.line_start == 45
        assert loc.line_end is None
        assert loc.class_name == ""
        assert loc.method_name == ""
        assert loc.repo == ""

    def test_full_fields(self):
        loc = SourceLocation(
            file="com/example/service/OrderServiceTest.java",
            line_start=45,
            line_end=72,
            class_name="OrderServiceTest",
            method_name="testApprove_success",
            repo="car-mrs",
        )
        assert loc.line_end == 72
        assert loc.repo == "car-mrs"

    def test_line_start_must_be_positive(self):
        with pytest.raises(ValidationError):
            SourceLocation(file="Foo.java", line_start=0)

    def test_line_end_must_be_gte_line_start(self):
        with pytest.raises(ValidationError):
            SourceLocation(file="Foo.java", line_start=10, line_end=5)

    def test_file_must_not_be_empty(self):
        with pytest.raises(ValidationError):
            SourceLocation(file="", line_start=1)
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
cd /Users/zhangyiqian/git_dev/dev-quality-gate/dev-quality-gate
python -m pytest tests/test_lineage_tracking.py -v
```

期望：`ImportError` 或 `ModuleNotFoundError`（`location.py` 尚未创建）

- [ ] **Step 3: 创建 `src/dqg/schemas/location.py`**

```python
from __future__ import annotations

from pydantic import BaseModel, Field, model_validator


class SourceLocation(BaseModel):
    """源码坐标，用于行级血缘追踪."""

    file: str = Field(min_length=1)
    line_start: int = Field(ge=1)
    line_end: int | None = Field(default=None, ge=1)
    class_name: str = ""
    method_name: str = ""
    repo: str = ""

    @model_validator(mode="after")
    def line_end_gte_line_start(self) -> "SourceLocation":
        if self.line_end is not None and self.line_end < self.line_start:
            raise ValueError(
                f"line_end ({self.line_end}) must be >= line_start ({self.line_start})"
            )
        return self
```

- [ ] **Step 4: 运行测试，确认全部通过**

```bash
python -m pytest tests/test_lineage_tracking.py::TestSourceLocation -v
```

期望：5 个测试全部 PASS

- [ ] **Step 5: Commit**

```bash
git add src/dqg/schemas/location.py tests/test_lineage_tracking.py
git commit -m "feat: add SourceLocation model for lineage tracking"
```

---

## Task 2: 更新 `schemas/__init__.py` 导出 `SourceLocation`

**Files:**
- Modify: `src/dqg/schemas/__init__.py`

- [ ] **Step 1: 读取当前 `__init__.py` 内容**

读取 `src/dqg/schemas/__init__.py` 确认现有导入列表。

- [ ] **Step 2: 在现有 import 列表末尾追加**

在 `src/dqg/schemas/__init__.py` 的 import 区块末尾加一行：

```python
from dqg.schemas.location import SourceLocation
```

并在 `__all__`（如有）中加入 `"SourceLocation"`。如果没有 `__all__`，只加 import 即可。

- [ ] **Step 3: 验证导入正常**

```bash
python -c "from dqg.schemas import SourceLocation; print(SourceLocation)"
```

期望：打印 `<class 'dqg.schemas.location.SourceLocation'>`

- [ ] **Step 4: Commit**

```bash
git add src/dqg/schemas/__init__.py
git commit -m "feat: export SourceLocation from schemas package"
```

---

## Task 3: 更新 Q05 `TCItem` schema

**Files:**
- Modify: `src/dqg/schemas/phase_q05.py`
- Test: `tests/test_lineage_tracking.py`

- [ ] **Step 1: 写失败测试**

在 `tests/test_lineage_tracking.py` 追加：

```python
from dqg.schemas.phase_q05 import TCItem


class TestTCItemWithLocation:

    def test_tc_item_without_location_is_valid(self):
        item = TCItem(id="TC-001", repo="car-mrs")
        assert item.test_location is None
        assert item.production_location is None

    def test_tc_item_with_test_location(self):
        from dqg.schemas.location import SourceLocation
        loc = SourceLocation(file="OrderServiceTest.java", line_start=45)
        item = TCItem(id="TC-001", repo="car-mrs", test_location=loc)
        assert item.test_location.line_start == 45

    def test_tc_item_with_both_locations(self):
        from dqg.schemas.location import SourceLocation
        item = TCItem(
            id="TC-001",
            repo="car-mrs",
            test_location=SourceLocation(
                file="OrderServiceTest.java",
                line_start=45,
                line_end=72,
                class_name="OrderServiceTest",
                method_name="testApprove",
                repo="car-mrs",
            ),
            production_location=SourceLocation(
                file="OrderService.java",
                line_start=88,
                class_name="OrderService",
                method_name="approve",
                repo="car-mrs",
            ),
        )
        assert item.production_location.method_name == "approve"
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
python -m pytest tests/test_lineage_tracking.py::TestTCItemWithLocation -v
```

期望：`AttributeError: 'TCItem' object has no attribute 'test_location'`

- [ ] **Step 3: 修改 `src/dqg/schemas/phase_q05.py`**

在 `TCItem` 类的字段列表末尾追加两个字段（在 `br: str = ""` 之后）：

```python
from dqg.schemas.location import SourceLocation  # 加到文件顶部 import 区

# 在 TCItem 类末尾追加：
test_location: SourceLocation | None = None
production_location: SourceLocation | None = None
```

- [ ] **Step 4: 运行测试，确认通过**

```bash
python -m pytest tests/test_lineage_tracking.py::TestTCItemWithLocation -v
```

期望：3 个测试全部 PASS

- [ ] **Step 5: 运行全量测试，确认无回归**

```bash
python -m pytest tests/ -v --tb=short 2>&1 | tail -20
```

期望：所有原有测试仍然 PASS

- [ ] **Step 6: Commit**

```bash
git add src/dqg/schemas/phase_q05.py tests/test_lineage_tracking.py
git commit -m "feat: add test_location and production_location to TCItem"
```

---

## Task 4: 更新 Q06 `EutAuditItem` 和 `FindingItem` schema

**Files:**
- Modify: `src/dqg/schemas/phase_q06.py`
- Test: `tests/test_lineage_tracking.py`

- [ ] **Step 1: 写失败测试**

在 `tests/test_lineage_tracking.py` 追加：

```python
from dqg.schemas.phase_q06 import EutAuditItem, FindingItem
from dqg.schemas.location import SourceLocation


class TestEutAuditItemWithLocation:

    def test_eut_audit_item_without_location_is_valid(self):
        item = EutAuditItem(eut_id="EUT-001", status="COVERED")
        assert item.test_location is None
        assert item.production_location is None

    def test_eut_audit_item_with_locations(self):
        item = EutAuditItem(
            eut_id="EUT-001",
            status="COVERED",
            test_location=SourceLocation(
                file="OrderServiceTest.java",
                line_start=52,
                class_name="OrderServiceTest",
                method_name="testApprove_success",
                repo="car-mrs",
            ),
            production_location=SourceLocation(
                file="OrderService.java",
                line_start=88,
                class_name="OrderService",
                method_name="approve",
                repo="car-mrs",
            ),
        )
        assert item.test_location.line_start == 52
        assert item.production_location.class_name == "OrderService"


class TestFindingItemWithLocation:

    def test_finding_item_without_location_is_valid(self):
        item = FindingItem(id="FIND-001", severity="HIGH")
        assert item.production_location is None

    def test_finding_item_with_production_location(self):
        item = FindingItem(
            id="FIND-001",
            severity="HIGH",
            production_location=SourceLocation(
                file="OrderService.java",
                line_start=88,
                repo="car-mrs",
            ),
        )
        assert item.production_location.file == "OrderService.java"
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
python -m pytest tests/test_lineage_tracking.py::TestEutAuditItemWithLocation tests/test_lineage_tracking.py::TestFindingItemWithLocation -v
```

期望：`AttributeError`（字段不存在）

- [ ] **Step 3: 修改 `src/dqg/schemas/phase_q06.py`**

在文件顶部 import 区追加：
```python
from dqg.schemas.location import SourceLocation
```

在 `EutAuditItem` 类末尾（`issues` 字段之后）追加：
```python
test_location: SourceLocation | None = None
production_location: SourceLocation | None = None
```

在 `FindingItem` 类末尾（`recommendation` 字段之后）追加：
```python
production_location: SourceLocation | None = None
```

- [ ] **Step 4: 运行测试，确认通过**

```bash
python -m pytest tests/test_lineage_tracking.py::TestEutAuditItemWithLocation tests/test_lineage_tracking.py::TestFindingItemWithLocation -v
```

期望：5 个测试全部 PASS

- [ ] **Step 5: 运行全量测试，确认无回归**

```bash
python -m pytest tests/ -v --tb=short 2>&1 | tail -20
```

期望：所有原有测试仍然 PASS

- [ ] **Step 6: Commit**

```bash
git add src/dqg/schemas/phase_q06.py tests/test_lineage_tracking.py
git commit -m "feat: add location fields to EutAuditItem and FindingItem"
```

---

## Task 5: Finalize Gate — location 校验规则

**Files:**
- Modify: `src/dqg/quality/checks/auto_checks.py`
- Test: `tests/test_lineage_tracking.py`

- [ ] **Step 1: 写失败测试**

在 `tests/test_lineage_tracking.py` 追加：

```python
import json
import tempfile
from pathlib import Path
from dqg.quality.auto_checks import auto_derive_checks


def _write_q06_json(tmpdir: Path, data: dict) -> Path:
    phase_dir = tmpdir / "test-proj" / "Q06"
    phase_dir.mkdir(parents=True)
    json_path = phase_dir / "phase_c_structured.json"
    json_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return tmpdir


class TestLocationGate:

    def test_covered_without_test_location_is_downgraded(self):
        data = {
            "project_id": "test-proj",
            "audit_items": [
                {
                    "eut_id": "EUT-001",
                    "status": "COVERED",
                    "evidence": "assertEquals(...) [Foo.java:10]",
                    "test_location": None,
                }
            ],
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = _write_q06_json(Path(tmpdir), data)
            errors = auto_derive_checks(output_dir, "test-proj", "Q06")
        assert any("test_location" in e and "PARTIAL" in e for e in errors)

    def test_covered_with_test_location_passes(self):
        data = {
            "project_id": "test-proj",
            "audit_items": [
                {
                    "eut_id": "EUT-001",
                    "status": "COVERED",
                    "evidence": "assertEquals(...) [Foo.java:10]",
                    "test_location": {
                        "file": "FooTest.java",
                        "line_start": 10,
                    },
                }
            ],
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = _write_q06_json(Path(tmpdir), data)
            errors = auto_derive_checks(output_dir, "test-proj", "Q06")
        location_errors = [e for e in errors if "test_location" in e and "PARTIAL" in e]
        assert len(location_errors) == 0

    def test_missing_status_skips_location_check(self):
        data = {
            "project_id": "test-proj",
            "audit_items": [
                {
                    "eut_id": "EUT-001",
                    "status": "MISSING",
                    "test_location": None,
                }
            ],
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = _write_q06_json(Path(tmpdir), data)
            errors = auto_derive_checks(output_dir, "test-proj", "Q06")
        location_errors = [e for e in errors if "test_location" in e and "PARTIAL" in e]
        assert len(location_errors) == 0
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
python -m pytest tests/test_lineage_tracking.py::TestLocationGate -v
```

期望：`AssertionError`（校验规则尚未实现）

- [ ] **Step 3: 在 `auto_checks.py` 追加校验函数**

在 `_check_severity_annotations` 函数之后，`_check_rsm_coverage` 之前，新增：

```python
def _check_location_coverage(validated: BaseModel, phase_id: str) -> list[str]:
    """Q06 COVERED 判定必须有 test_location，否则降级为 PARTIAL."""
    if phase_id != "Q06":
        return []
    errors: list[str] = []
    audit_items = getattr(validated, "audit_items", [])
    for item in audit_items:
        status = getattr(item, "status", None)
        test_location = getattr(item, "test_location", None)
        eut_id = getattr(item, "eut_id", "unknown")
        if str(status) == "COVERED" and test_location is None:
            errors.append(
                f"LOCATION: {eut_id}: status=COVERED 但 test_location 为空，"
                "降级为 PARTIAL。请补充测试代码坐标。"
            )
    return errors
```

- [ ] **Step 4: 在 `auto_derive_checks` 中调用新函数**

在 `auto_derive_checks` 函数的 `# --- 4. 严重等级标注校验 ---` 之后追加：

```python
                # --- 5. Location 覆盖校验（Q06 COVERED 必须有 test_location）---
                errors.extend(_check_location_coverage(validated, phase_id))
```

- [ ] **Step 5: 运行测试，确认通过**

```bash
python -m pytest tests/test_lineage_tracking.py::TestLocationGate -v
```

期望：3 个测试全部 PASS

- [ ] **Step 6: 运行全量测试，确认无回归**

```bash
python -m pytest tests/ -v --tb=short 2>&1 | tail -20
```

期望：所有原有测试仍然 PASS

- [ ] **Step 7: Commit**

```bash
git add src/dqg/quality/checks/auto_checks.py tests/test_lineage_tracking.py
git commit -m "feat: finalize gate — downgrade COVERED to PARTIAL when test_location missing"
```

---

## Task 6: 更新 Q05 Skill Prompt

**Files:**
- Modify: `skills/unit-test-generation/SKILL.md`

- [ ] **Step 1: 在 `phase_b_structured.json` 格式示例中更新 TC 条目**

找到 `### \`phase_b_structured.json\` 格式（必须严格遵守）` 章节下的 JSON 示例，将示例中的 TC 条目替换为：

```json
{
  "id": "TC-001",
  "repo": "car-mrs",
  "status": "COVERED",
  "covered_by": "MrOrderMainServiceTest#testApplyEarlyDelivery_success",
  "scenario": "测试场景描述",
  "se_refs": ["SE-001"],
  "method": "applyEarlyDelivery",
  "class_under_test": "MrOrderMainService",
  "requirement": "BR-001",
  "priority": "P0",
  "test_location": {
    "file": "com/example/service/MrOrderMainServiceTest.java",
    "line_start": 45,
    "line_end": 72,
    "class_name": "MrOrderMainServiceTest",
    "method_name": "testApplyEarlyDelivery_success",
    "repo": "car-mrs"
  },
  "production_location": {
    "file": "com/example/service/MrOrderMainService.java",
    "line_start": 120,
    "line_end": 145,
    "class_name": "MrOrderMainService",
    "method_name": "applyEarlyDelivery",
    "repo": "car-mrs"
  }
}
```

- [ ] **Step 2: 在字段约束列表末尾追加两条**

在 `**字段约束：**` 列表末尾追加：

```
- `test_location`: COVERED 时强烈建议填写，`line_start` 指向断言所在行
- `production_location`: 填写被测方法的实现起始行
```

- [ ] **Step 3: 在 Step 4 自检清单末尾追加一条**

```
- [ ] **COVERED 的 TC 已填写 `test_location`（`line_start` 指向断言行，非方法第一行）**
```

- [ ] **Step 4: Commit**

```bash
git add skills/unit-test-generation/SKILL.md
git commit -m "feat: update Q05 skill prompt with location fields"
```

---

## Task 7: 更新 Q06 Skill Prompt

**Files:**
- Modify: `skills/unit-test-audit/SKILL.md`

- [ ] **Step 1: 在 `phase_c_structured.json` 格式示例中更新 audit_item 条目**

找到 `## phase_c_structured.json 产出格式（强制）` 章节下的 JSON 示例，将 `audit_items` 中的示例条目替换为：

```json
{
  "id": "AUDIT-001",
  "se_id": "SE-001",
  "eut_id": "EUT-001,EUT-002",
  "description": "SE 描述",
  "status": "COVERED|PARTIAL|MISSING|WRONG_TARGET",
  "test_class": "XxxTest",
  "test_method": "method1, method2",
  "evidence": "assertEquals('expected', actual) [XxxTest.java:52]; verify(mock).call() [XxxTest.java:58]",
  "recommendation": "",
  "test_location": {
    "file": "com/example/service/XxxTest.java",
    "line_start": 52,
    "class_name": "XxxTest",
    "method_name": "method1",
    "repo": "car-mrs"
  },
  "production_location": {
    "file": "com/example/service/Xxx.java",
    "line_start": 88,
    "class_name": "Xxx",
    "method_name": "targetMethod",
    "repo": "car-mrs"
  }
}
```

- [ ] **Step 2: 在 `evidence 字段铁律` 之后追加 location 铁律**

在 `## phase_c_structured.json 产出格式（强制）` 章节的 `**evidence 字段铁律：**` 之后追加：

```markdown
**location 字段铁律：**
- COVERED 判定必须填写 `test_location`，`line_start` 指向断言所在行（不是测试方法第一行）
- `production_location` 必须对应被测方法的实现起始行
- 空 `test_location` 的 COVERED 会被 finalize gate 自动降级为 PARTIAL
```

- [ ] **Step 3: 在 Step 9 自检清单末尾追加一条**

```
- [ ] 每个 COVERED 判定已填写 `test_location`（`line_start` 指向断言行）
```

- [ ] **Step 4: Commit**

```bash
git add skills/unit-test-audit/SKILL.md
git commit -m "feat: update Q06 skill prompt with location fields and IRON LAW"
```

---

## Task 8: 运行全量测试 + Ruff lint

- [ ] **Step 1: 运行全量测试**

```bash
python -m pytest tests/ -v --tb=short
```

期望：所有测试 PASS，无新增失败

- [ ] **Step 2: 运行 Ruff lint**

```bash
python -m ruff check src/dqg/schemas/location.py src/dqg/schemas/phase_q05.py src/dqg/schemas/phase_q06.py src/dqg/quality/checks/auto_checks.py
```

期望：无 lint 错误

- [ ] **Step 3: 如有 lint 错误，修复后重新运行**

```bash
python -m ruff check --fix src/dqg/schemas/location.py src/dqg/schemas/phase_q05.py src/dqg/schemas/phase_q06.py src/dqg/quality/checks/auto_checks.py
python -m pytest tests/ -v --tb=short 2>&1 | tail -10
```

- [ ] **Step 4: 最终 commit（如有 lint 修复）**

```bash
git add -p
git commit -m "fix: ruff lint fixes for lineage tracking"
```
