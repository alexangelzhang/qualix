# Evidence Contract 硬化设计（方案 A）

**日期**: 2026-05-27  
**状态**: 待实施  
**对应 ROADMAP**: §C P0 防幻觉架构 — Evidence Contract 硬化

---

## 背景

DQG 产物存在三类幻觉风险：

| 维度 | 当前状态 | 风险 |
|------|---------|------|
| Q01 SE.source | 字段存在但从不校验真实性 | LLM 可捏造行号 |
| Q05 EUT → impl class | EUT 的 bound_item 链接到 SE，SE.code_target 标注实现类，但无 grep 验证 | 测试描述指向不存在的类 |
| Q06 COVERED | test_class/test_location 字段可填可不填，即使 COVERED 也无强制证据 | 覆盖审计结论无可追溯证据 |

## 范围

**本次（方案 A）**：纯 verifier，零 schema 变更，零已有 handler 签名变更。  
**未来（方案 B）**：EutItem 加 `impl_class` 字段 + EutAuditItem COVERED 强制 `test_class` — 见 ROADMAP §未来架构优化。

---

## 设计

### 1. Q01 SE.source 跨引用校验

**新 handler**: `handle_se_source_evidence`  
**注册位置**: `handlers_finalize.py::register_finalize_handlers()`  
**注册参数**: `stage="finalize"`, `order=57`, `phases={"Q01"}`, `required=True`

**逻辑**:

```
读 phase_a_structured.json → 遍历 semantic_expectations
  SE.source == "" → 记录 status=empty_source (WARNING)
  SE.source == "file:N" →
    路径: ctx.phase_root / "ingest" / file
    文件不存在 → BLOCKED: evidence_contract_se_source_file_missing
    N > 文件行数 → BLOCKED: evidence_contract_se_source_line_oob
    成功 → 提取 line_text + ±2 行上下文 + sha256(line_text) → status=ok
写入 _internal/_se_source_evidence.json
```

**输出格式** (`_se_source_evidence.json`):

```json
{
  "verified_at": "2026-05-27T...",
  "entries": [
    {
      "se_id": "SE-001",
      "source_raw": "plain_text.txt:79",
      "source_file": "plain_text.txt",
      "source_line": 79,
      "line_text": "...",
      "context_lines": ["line77", "line78", "line79", "line80", "line81"],
      "context_hash": "abc123",
      "status": "ok"
    },
    {
      "se_id": "SE-005",
      "source_raw": "",
      "status": "empty_source"
    }
  ]
}
```

**Gate 策略**:

| 状态 | 级别 | 说明 |
|------|------|------|
| `ok` | 通过 | 行号真实存在 |
| `empty_source` | WARNING | SE 未填写 source，无法追溯 PRD 原始依据 |
| `file_missing` | BLOCKED | source 指向不存在的 ingest 文件 |
| `line_oob` | BLOCKED | 行号超出文件实际行数 |

**error 格式** (进入 result.errors):

```
BLOCKED: [evidence_contract] SE-003 source "plain_text.txt:999" 行号超出范围 (文件共 420 行)
WARNING: [evidence_contract] SE-007 source 未填写，无法追溯 PRD 原始依据
```

---

### 2. Q05a EUT → SE.code_target grep 验证

**新函数**: `check_eut_code_target_traceability(output_dir, project_id, code_repos) -> list[str]`  
**文件**: `src/dqg/quality/checks/q05_structure_checks.py`  
**调用位置**: `finalize_checks.py::run_finalize_checks()` — 在 `phase_id == "Q05a"` 条件下

**逻辑**:

```
读 phase_a_structured.json → build SE_ID → code_target 映射
读 Q05a JSON (phase_b_structured.json) → 遍历 eut_items
  EutItem.bound_item 以 "SE-" 开头 →
    查 SE.code_target
    code_target == "" → skip（SE 未定义 impl 目标）
    code_target 非空 →
      提取类名（取第一个 "." 前的部分，如 "OrderService"）
      对每个 code_repo 做 subprocess grep -rl -F <class_name>
      所有 repo 均未找到 → WARNING: eut_impl_not_found
返回 warning 列表
```

**始终 WARNING**（非 BLOCKED），理由：
- TDD 场景：测试先于 impl 存在
- code_target 可能是简写，不等于完整文件名
- 代码仓库可能未传入

**error 格式**:

```
WARNING: [evidence_contract] EUT-012 bound SE-005.code_target "PaymentService" 在代码仓库中未找到，请确认实现类名
```

---

### 3. Q06 COVERED 条目证据强制

**新函数**: `check_covered_evidence(output_dir, project_id, code_repos) -> list[str]`  
**文件**: `src/dqg/quality/checks/q06_structure_checks.py`  
**调用位置**: `finalize_checks.py::run_finalize_checks()` — 在 `phase_id == "Q06"` 条件下，复用已有的 `code_repos` 读取逻辑

**逻辑**:

```
读 phase_c_structured.json → 遍历 audit_items
  status == COVERED →
    test_class == "" AND test_location is None → WARNING: covered_no_evidence
    test_location.file 非空 →
      在 code_repos 中查找该文件 →
      所有 repo 均未找到 → BLOCKED: covered_test_location_invalid
      找到 → 验证 test_location.line_start 在文件行数范围内 →
              超出 → WARNING: covered_test_location_line_oob
```

**Gate 策略**:

| 情况 | 级别 |
|------|------|
| COVERED 无 test_class 且无 test_location | WARNING |
| test_location.file 不存在于代码仓库 | BLOCKED |
| test_location.line_start 超出文件行数 | WARNING |

---

## 接入方式

三个检查全部通过现有扩展点接入，不修改已有函数签名：

```
handle_se_source_evidence  →  register_handler() in handlers_finalize.py
check_eut_code_target_traceability  →  run_finalize_checks() Q05a 分支
check_covered_evidence  →  run_finalize_checks() Q06 分支（已有 code_repos 读取）
```

错误字符串 `BLOCKED:` / `WARNING:` 前缀进入 `result.errors`，由 `build_verdict()` 转换为 `CheckItem(level=HARD/SOFT)`。

---

## 测试计划

| 测试 | 覆盖点 |
|------|--------|
| `test_se_source_evidence_ok` | source="plain_text.txt:5"，文件第 5 行存在 |
| `test_se_source_evidence_empty` | source=""，产生 WARNING |
| `test_se_source_evidence_file_missing` | source="nonexist.txt:1"，产生 BLOCKED |
| `test_se_source_evidence_line_oob` | 行号超出文件长度，产生 BLOCKED |
| `test_eut_code_target_found` | SE.code_target 在 code_repo 中 grep 到，无 warning |
| `test_eut_code_target_not_found` | grep 不到，产生 WARNING |
| `test_eut_code_target_empty` | SE.code_target=="" → skip |
| `test_covered_no_evidence` | COVERED + 无 test_class/location → WARNING |
| `test_covered_location_invalid` | test_location.file 不在 repo → BLOCKED |
| `test_covered_location_line_oob` | line_start > 文件行数 → WARNING |

---

## 方案 B（未来架构优化，入 ROADMAP）

本次不实施，记录为后续优化：

1. `EutItem` 加 `impl_class: str = ""` 显式字段，替代通过 SE.code_target 间接推导
2. `EutAuditItem` 当 `status=COVERED` 时 `test_class` 强制非空（Pydantic validator）
3. 统一 Claim Registry / Evidence Registry — 见 ROADMAP §C P1

---

## 验收口径

- Q01 finalize 后 `_internal/_se_source_evidence.json` 生成，每条 SE 有 status 记录
- source 填写了错误行号的 SE → finalize BLOCKED，approve 被阻断
- Q05a finalize 时 SE.code_target 不为空且 grep 不到 → WARNING 出现在 gate_verdict
- Q06 finalize 时 COVERED 条目的 test_location.file 填了但文件不存在 → BLOCKED
- 新增 10 条单测全绿，无已有测试回归
