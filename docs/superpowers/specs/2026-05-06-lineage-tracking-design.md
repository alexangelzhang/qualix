# 行级血缘追踪设计文档

**日期：** 2026-05-06
**状态：** 已批准
**范围：** Q05a（单测生成）、Q06（单测审计）

## 背景

Qualix Q05a/Q06 产出的质量问题目前只有文本描述，没有结构化的源码坐标。`EutAuditItem.evidence` 字段虽然有 `[文件名:行号]` 的文本约定，但格式不稳定，agent 消费时需要脆弱的正则解析。

目标：为每条审计判定和测试用例附加结构化的双坐标（测试代码位置 + 被测生产代码位置），同时服务于人工 review（可点击跳转）和自动修复 agent（直接读取坐标）。

## 数据模型

### 新增 `SourceLocation`（`src/qualix/schemas/location.py`）

```python
class SourceLocation(BaseModel):
    file: str           # 相对路径，如 com/example/service/OrderServiceTest.java
    line_start: int     # 1-based
    line_end: int | None = None
    class_name: str = ""
    method_name: str = ""
    repo: str = ""      # 多仓库场景必填
```

### Q05a `TCItem` 新增字段（`src/qualix/schemas/phase_q05.py`）

```python
test_location: SourceLocation | None = None       # 测试代码位置
production_location: SourceLocation | None = None  # 被测生产代码位置
```

### Q06 `EutAuditItem` 新增字段（`src/qualix/schemas/phase_q06.py`）

```python
test_location: SourceLocation | None = None
production_location: SourceLocation | None = None
```

### Q06 `FindingItem` 新增字段

```python
production_location: SourceLocation | None = None
```

所有字段均为可选，旧产物不填不报错，保持向后兼容。

## Skill Prompt 更新

### Q05a `phase_b_structured.json` 格式示例

```json
{
  "id": "TC-001",
  "repo": "car-mrs",
  "status": "COVERED",
  "covered_by": "MrOrderMainServiceTest#testApplyEarlyDelivery_success",
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

### Q06 `audit_items` 格式示例

```json
{
  "id": "AUDIT-001",
  "se_id": "SE-001",
  "eut_id": "EUT-001",
  "status": "COVERED",
  "evidence": "assertEquals('APPROVED', status) [XxxTest.java:52]",
  "test_location": {
    "file": "com/example/service/OrderServiceTest.java",
    "line_start": 52,
    "class_name": "OrderServiceTest",
    "method_name": "testApprove_success",
    "repo": "car-mrs"
  },
  "production_location": {
    "file": "com/example/service/OrderService.java",
    "line_start": 88,
    "class_name": "OrderService",
    "method_name": "approve",
    "repo": "car-mrs"
  }
}
```

### 新增 IRON LAW（两个 skill 均加）

> COVERED 判定的 `test_location.line_start` 必须对应断言所在行，不是测试方法第一行。`production_location` 必须对应被测方法的实现起始行。

## Finalize Gate 校验

在 `quality/checks/auto_checks.py` Q05a/Q06 校验段追加：

**规则 1：COVERED 判定必须有 test_location**
- `EutAuditItem.status == COVERED` 且 `test_location is None` → 降级为 `PARTIAL`，写入 `validation_errors`

**规则 2：location 字段基本合法性**
- `file` 不能为空字符串
- `line_start >= 1`
- `line_end`（如填写）必须 `>= line_start`

不做文件实际存在性校验（finalize 阶段不保证有仓库路径）。

## 改动文件清单

| 文件 | 类型 | 说明 |
|------|------|------|
| `src/qualix/schemas/location.py` | 新建 | `SourceLocation` 模型 |
| `src/qualix/schemas/phase_q05.py` | 修改 | `TCItem` 加两个可选字段 |
| `src/qualix/schemas/phase_q06.py` | 修改 | `EutAuditItem`、`FindingItem` 加字段 |
| `src/qualix/schemas/__init__.py` | 修改 | 导出 `SourceLocation` |
| `skills/unit-test-design/SKILL.md` | 修改 | 更新 JSON 格式示例 + 新增 IRON LAW |
| `skills/unit-test-audit/SKILL.md` | 修改 | 更新 JSON 格式示例 + 新增 IRON LAW |
| `src/qualix/quality/checks/auto_checks.py` | 修改 | 追加 location 校验规则 |

## Out of Scope

- 不实现 location 的文件实际存在性验证
- 不改 Q01-Q04、Q07 的 schema
- 不实现基于 location 的自动修复 agent
- 不改 `fact_cache.py` 的 FTS 索引
