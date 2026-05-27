# P1 循环质量三件套设计文档

**日期**: 2026-05-27  
**状态**: 待实施  
**对应 ROADMAP**: §7 #1 PIVOT版本化 / #7 data_patterns sidecar / #3 退化检测增强

---

## 范围

三个独立子项目，可并行开发，共享测试文件。

| 子项目 | 文件改动 | 估算 |
|--------|---------|------|
| P1-3 PIVOT版本化 | `adaptive_loop.py` (新增私有方法) | 2h |
| P1-4 data_patterns sidecar | `data_patterns.py` (2行改动+lesson增强) | 1.5h |
| P1-2 退化检测增强 | `loop_health.py` (新增2维度) + `adaptive_loop.py` (传参) | 2.5h |

---

## P1-3：PIVOT/REFINE 版本化（最小形态）

### 背景

`adaptive_loop.py` 的每轮 iteration 覆盖写 structured JSON、报告。若第 1 轮产出高分但第 2 轮 Worker 改坏了，下游无法回退到第 1 轮。

### 设计

**新私有方法** `AdaptiveLoop._save_pivot_snapshot(pd, iteration_n, record)`:

```python
def _save_pivot_snapshot(self, pd: Path, iteration_n: int, record: IterationRecord) -> None:
    """Judge FAIL 后、下一轮 Worker 启动前，快照当前轮产物到 _pivot_v{n}/."""
```

- 目标目录：`pd / f"_pivot_v{iteration_n + 1}"`（n 从 0 开始，v1 = 第1轮快照）
- 复制文件（存在才复制，不抛出异常）：
  - `pd / STRUCTURED_JSON_MAP[phase_id]`（主结构化 JSON）
  - `pd / REPORT_MAP[phase_id]`（主报告）
  - `pd / "_internal" / "_reasoning_log.md"`
  - `pd / f"_judge_iter{iteration_n+1}.json"`（若存在）
  - `pd / f"_handoff_iter{iteration_n+1}.md"`（若存在）
- 写入 `pd / "_pivot_latest"` 文件（纯文本），内容为当前最新快照目录名（如 `_pivot_v1`）

**调用时机**（在 `adaptive_loop.py::run()` 的主循环内）：

```python
# 在 health_result.should_stop 检查之后，下一轮 iteration 开始之前
if not passed and not health_result.should_stop and (i + 1) < max_iterations:
    self._save_pivot_snapshot(pd, i, record)
```

**不复制的内容**：`_internal/` 下的大文件（`_upstream_context.md`、`_evidence_*.json`）——这些是输入，不是产物，复制没有意义。

### 错误处理

snapshot 失败（磁盘满/权限错误）→ 记录 WARNING 日志，不中断循环。

---

## P1-4：data_patterns sidecar

### 背景

`write_data_patterns` 硬编码 `analyze_data_patterns("Q06")`，对所有 Phase 写出的都是 Q06 的数据模式，与当前 Phase 无关。此外，输出只有 case_id，不含实际经验教训文本，Agent 需要额外查询。

### 设计

**修复 #1**（1行）：

```python
# 改前
analysis = analyze_data_patterns("Q06")  # 始终从 Phase C 案例提取
# 改后
analysis = analyze_data_patterns(phase_id)
```

**增强 #2**：在 `analyze_data_patterns` 的 `top_patterns` 输出中追加 `top_lessons` 字段：

```python
# 每个 pattern 条目增加：
{
    "id": "DP-FIELD-MAPPING",
    "count": 18,
    "suggestions": [...],
    "example_cases": ["case_001", "case_002", "case_003"],
    "top_lessons": [          # 新增：前 N 条 lesson 原文（截断到 200 字符）
        "字段赋值必须区分 null 和空字符串，否则...",
        "跨系统字段映射时必须显式转换枚举值..."
    ]
}
```

**实现**：在 `analyze_data_patterns` 的循环里，为每个 pattern 取关联 case 的 `lesson` 字段（已通过 `get_case_with_inferred_lesson` 填充），去重后保留前 3 条，截断至 200 字符。

**可配置参数**（常量）：`DATA_PATTERN_TOP_LESSONS = 3`，`DATA_PATTERN_LESSON_MAX_CHARS = 200`，在 `constants.py` 新增。

---

## P1-2：退化检测增强

### 背景

`LoopHealthMonitor` 已有分数停滞、issue 重复、infra failure 三维检测。缺"Worker 产出没变"和"Judge 驳回理由没变"两个更精确的检测——它们能捕获 Worker 实质无改变（而分数可能因随机性小幅波动）的 doom loop。

### 设计

**`LoopHealthMonitor` 新增两个维度**：

新增存储字段：
```python
self._worker_output_hashes: list[str] = []   # sha256(worker_output[:2000])
self._judge_rejection_sigs: list[str] = []   # sha256(sorted top-3 issue codes)
```

`record_iteration()` 新增两个可选参数（向后兼容，默认 None）：
```python
def record_iteration(
    self,
    avg_score: float,
    issues: list[dict] | None = None,
    judge_health: str = "HEALTHY",
    worker_output_hash: str | None = None,   # 新增
    judge_rejection_sig: str | None = None,  # 新增
) -> None:
```

`check()` 新增两个检测（在已有检测之后，return HealthCheckResult() 之前）：

```python
# 4. Worker 产出指纹停滞
if len(self._worker_output_hashes) >= 2:
    if (self._worker_output_hashes[-1]
        and self._worker_output_hashes[-1] == self._worker_output_hashes[-2]):
        return HealthCheckResult(
            should_stop=True,
            status="output_fingerprint_stagnation",
            message="Worker 连续 2 轮产出完全相同（指纹不变），修正无效",
        )

# 5. Judge 驳回签名停滞
if len(self._judge_rejection_sigs) >= 2:
    if (self._judge_rejection_sigs[-1]
        and self._judge_rejection_sigs[-1] == self._judge_rejection_sigs[-2]):
        return HealthCheckResult(
            should_stop=True,
            status="rejection_signature_stagnation",
            message="Judge 连续 2 轮驳回相同 issue（签名不变），Worker 未解决根本问题",
        )
```

**`adaptive_loop.py` 的计算逻辑**（在 `monitor.record_iteration()` 调用处注入）：

```python
# 计算 Worker 产出指纹
_worker_hash = None
_json_fname = STRUCTURED_JSON_MAP.get(phase_id)
if _json_fname:
    _json_path = pd / _json_fname
    if _json_path.exists():
        import hashlib
        _raw = _json_path.read_text(encoding="utf-8", errors="replace")[:2000]
        _worker_hash = hashlib.sha256(_raw.encode()).hexdigest()[:16]

# 计算 Judge 驳回签名
_rejection_sig = None
if record.judge_result is not None and not passed:
    _top_codes = sorted(
        {(v.get("code") or v.get("dimension") or "") for v in all_issues if v}
    )[:3]
    if _top_codes:
        import hashlib
        _rejection_sig = hashlib.sha256("|".join(_top_codes).encode()).hexdigest()[:16]

monitor.record_iteration(
    avg_score=record.judge_result.avg_score,
    issues=all_issues,
    judge_health=health,
    worker_output_hash=_worker_hash,
    judge_rejection_sig=_rejection_sig,
)
```

**`get_summary()` 扩展**：追加 `output_fingerprint_history` 和 `rejection_sig_history` 字段（记录每轮 hash 前 8 位，方便 debug）。

---

## 测试计划

| 测试 | 覆盖点 |
|------|--------|
| `test_pivot_snapshot_creates_dir` | FAIL 时 `_pivot_v1/` 目录生成 |
| `test_pivot_snapshot_copies_json_and_report` | 主 JSON 和报告被复制 |
| `test_pivot_snapshot_skips_on_pass` | PASS 时不生成快照 |
| `test_write_data_patterns_uses_phase_id` | `analyze_data_patterns(phase_id)` 而非 "Q06" |
| `test_analyze_data_patterns_includes_lessons` | top_lessons 不为空，长度 ≤ 200 |
| `test_loop_health_output_fingerprint_stagnation` | 相同 hash 连续 2 轮 → EARLY_STOP |
| `test_loop_health_rejection_sig_stagnation` | 相同 sig 连续 2 轮 → EARLY_STOP |
| `test_loop_health_different_hashes_no_stop` | hash 不同 → 继续 |

---

## 验收口径

- Q05 执行后 `_data_patterns.md` 包含 Q05 相关 bug case 的模式（而非 Q06 的）
- adaptive loop 在 Worker 连续 2 轮输出相同 JSON 时触发 EARLY_STOP
- adaptive loop 在 Judge 连续驳回相同 issue 时触发 EARLY_STOP
- Judge FAIL 且有下一轮时，`_pivot_v{n}/` 目录存在并包含该轮的 JSON+报告
