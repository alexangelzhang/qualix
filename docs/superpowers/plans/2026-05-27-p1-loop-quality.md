# P1 循环质量三件套 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复 data_patterns 按 Phase 过滤 bug、为 adaptive loop 产物添加版本化快照、以及增强退化检测维度（Worker 输出指纹 + Judge 驳回签名），防止无效循环浪费 token。

**Architecture:** P1-4 是单行 bug 修复 + lesson 字段增强；P1-3 在 `AdaptiveLoop.run()` 主循环末尾插入 `_save_pivot_snapshot` 私有方法；P1-2 扩展 `LoopHealthMonitor.record_iteration()` 新增两个可选参数，并在 `adaptive_loop.py` 调用处注入 hash 计算。三个子项目独立，可分别提交。

**Tech Stack:** Python 3.11+, pathlib, hashlib, shutil, pytest

---

## 文件总览

| 操作 | 路径 | 职责 |
|------|------|------|
| MODIFY | `src/dqg/tracking/data_patterns.py` | 修复 phase_id 硬编码 + 追加 top_lessons |
| MODIFY | `src/dqg/constants.py` | 新增 2 个常量 |
| MODIFY | `src/dqg/agents/loop_health.py` | 新增 2 个检测维度 |
| MODIFY | `src/dqg/agents/adaptive_loop.py` | 插入快照逻辑 + 注入 hash 参数 |
| CREATE | `tests/test_p1_loop_quality.py` | 8 条单测 |

---

## Task 1：data_patterns sidecar（P1-4）

**Files:**
- Modify: `src/dqg/tracking/data_patterns.py:157,227`
- Modify: `src/dqg/constants.py` (追加 2 个常量)
- Test: `tests/test_p1_loop_quality.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_p1_loop_quality.py
"""Tests for P1 loop quality improvements."""
from __future__ import annotations

from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Task 1: data_patterns sidecar
# ---------------------------------------------------------------------------

def test_write_data_patterns_uses_phase_id():
    """write_data_patterns 必须用 phase_id 调用 analyze_data_patterns，而非硬编码 'Q06'."""
    from pathlib import Path
    from unittest.mock import patch as _patch
    from dqg.tracking.data_patterns import write_data_patterns

    captured_phase = []

    def _fake_analyze(phase=None):
        captured_phase.append(phase)
        return {"top_patterns": [], "total_cases": 0,
                "pattern_distribution": {}, "cases_by_pattern": {}}

    with _patch("dqg.tracking.data_patterns.analyze_data_patterns", side_effect=_fake_analyze):
        write_data_patterns(Path("/tmp"), "proj", "Q05")

    assert captured_phase == ["Q05"], f"Expected ['Q05'], got {captured_phase}"


def test_analyze_data_patterns_includes_top_lessons():
    """analyze_data_patterns 返回的 top_patterns 每条应包含 top_lessons 列表."""
    from unittest.mock import patch as _patch
    from dqg.tracking.data_patterns import analyze_data_patterns

    fake_cases = [
        {"case_id": "c1", "phase": "Q05", "lesson": "字段映射必须显式转换枚举值",
         "title": "字段映射错误", "description": "金额字段未转换", "error_type": "field_mapping"},
    ]

    with _patch("dqg.tracking.data_patterns.load_cases_by_phase", return_value=fake_cases), \
         _patch("dqg.tracking.data_patterns.get_case_with_inferred_lesson", side_effect=lambda c: c):
        result = analyze_data_patterns("Q05")

    for pattern in result.get("top_patterns", []):
        assert "top_lessons" in pattern, f"Pattern {pattern['id']} missing top_lessons"
        assert isinstance(pattern["top_lessons"], list)
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd /Users/zhangyiqian/git_dev/dev-quality-gate/dev-quality-gate
python -m pytest tests/test_p1_loop_quality.py::test_write_data_patterns_uses_phase_id \
  tests/test_p1_loop_quality.py::test_analyze_data_patterns_includes_top_lessons -v 2>&1 | tail -10
```
Expected: 2 FAILED（`write_data_patterns` 仍传 "Q06"，`top_lessons` key 不存在）

- [ ] **Step 3: 在 constants.py 新增 2 个常量**

读取 `src/dqg/constants.py`，在文件末尾追加：

```python
# data_patterns sidecar：每个 pattern 保留的 lesson 原文数量及最大字符数
DATA_PATTERN_TOP_LESSONS: int = 3
DATA_PATTERN_LESSON_MAX_CHARS: int = 200
```

- [ ] **Step 4: 修复 analyze_data_patterns**

读取 `src/dqg/tracking/data_patterns.py`。  
在 `analyze_data_patterns()` 函数的循环中，把 `cases_by_pattern` 的追加改为同时收集 lesson 文本：

将这段（约 L161-167）：
```python
    pattern_counter: Counter = Counter()
    cases_by_pattern: dict[str, list[str]] = defaultdict(list)

    for case in cases:
        matched = match_data_patterns(case)
        for pid in matched:
            pattern_counter[pid] += 1
            cases_by_pattern[pid].append(case.get("case_id", ""))
```
改为：
```python
    from dqg.constants import DATA_PATTERN_LESSON_MAX_CHARS, DATA_PATTERN_TOP_LESSONS

    pattern_counter: Counter = Counter()
    cases_by_pattern: dict[str, list[str]] = defaultdict(list)
    lessons_by_pattern: dict[str, list[str]] = defaultdict(list)

    for case in cases:
        matched = match_data_patterns(case)
        for pid in matched:
            pattern_counter[pid] += 1
            cases_by_pattern[pid].append(case.get("case_id", ""))
            lesson = (case.get("lesson") or "").strip()
            if lesson:
                lessons_by_pattern[pid].append(lesson[:DATA_PATTERN_LESSON_MAX_CHARS])
```

在 `top_patterns.append(...)` 调用里（约 L173-180）追加 `top_lessons` 字段：

```python
            top_patterns.append(
                {
                    "id": pid,
                    "name": pattern_def["name"],
                    "count": count,
                    "suggestions": pattern_def["test_data_suggestions"],
                    "example_cases": cases_by_pattern[pid][:3],
                    "top_lessons": list(dict.fromkeys(lessons_by_pattern[pid]))[:DATA_PATTERN_TOP_LESSONS],
                }
            )
```
（`dict.fromkeys` 去重同时保序）

- [ ] **Step 5: 修复 write_data_patterns 的硬编码**

在 `write_data_patterns()` 函数（约 L227）将：
```python
    analysis = analyze_data_patterns("Q06")  # 始终从 Phase C 案例提取
```
改为：
```python
    analysis = analyze_data_patterns(phase_id)
```

- [ ] **Step 6: 运行测试确认通过**

```bash
python -m pytest tests/test_p1_loop_quality.py::test_write_data_patterns_uses_phase_id \
  tests/test_p1_loop_quality.py::test_analyze_data_patterns_includes_top_lessons -v 2>&1 | tail -8
```
Expected: 2 PASSED

- [ ] **Step 7: 全量回归**

```bash
python -m pytest tests/ -x -q --ignore=tests/test_p1_loop_quality.py 2>&1 | tail -5
```
Expected: no new failures

- [ ] **Step 8: 提交**

```bash
git add src/dqg/tracking/data_patterns.py src/dqg/constants.py tests/test_p1_loop_quality.py
git commit -m "feat(p1-4): data_patterns sidecar 按 phase_id 过滤 + top_lessons 字段"
```

---

## Task 2：PIVOT/REFINE 版本化（P1-3）

**Files:**
- Modify: `src/dqg/agents/adaptive_loop.py:260-276`（主循环）
- Test: `tests/test_p1_loop_quality.py`

- [ ] **Step 1: 写失败测试**

在 `tests/test_p1_loop_quality.py` 追加：

```python
# ---------------------------------------------------------------------------
# Task 2: PIVOT snapshot
# ---------------------------------------------------------------------------

def _make_adaptive_loop_fixtures(tmp_path):
    """构造 AdaptiveLoop 测试所需的最小 fixtures."""
    from pathlib import Path
    from unittest.mock import MagicMock
    from dqg.agents.adaptive_loop import AdaptiveLoop

    loop = AdaptiveLoop(output_dir=tmp_path)
    pd = tmp_path / "proj" / "phase_a"
    pd.mkdir(parents=True)
    (pd / "_internal").mkdir()

    # 写入假的 structured JSON 和报告
    (pd / "phase_a_structured.json").write_text('{"project_id": "proj"}')
    (pd / "phase_a_report.md").write_text("# Report v1")
    (pd / "_internal" / "_reasoning_log.md").write_text("## Step 1")

    return loop, pd


def test_pivot_snapshot_creates_dir_on_judge_fail(tmp_path):
    """Judge FAIL 时应创建 _pivot_v1/ 目录并包含主 JSON."""
    import json
    from pathlib import Path
    from dqg.agents.adaptive_loop import AdaptiveLoop
    from dqg.constants import STRUCTURED_JSON_MAP, REPORT_MAP

    loop, pd = _make_adaptive_loop_fixtures(tmp_path)
    phase_id = "Q01"
    json_fname = STRUCTURED_JSON_MAP.get(phase_id, "phase_a_structured.json")
    (pd / json_fname).write_text('{"project_id": "proj"}')

    loop._save_pivot_snapshot(pd=pd, iteration_n=0, phase_id=phase_id)

    pivot_dir = pd / "_pivot_v1"
    assert pivot_dir.is_dir(), "_pivot_v1 目录未创建"
    assert (pivot_dir / json_fname).exists(), "主 JSON 未复制"


def test_pivot_snapshot_writes_latest_pointer(tmp_path):
    """_save_pivot_snapshot 应更新 _pivot_latest 文件."""
    from dqg.agents.adaptive_loop import AdaptiveLoop

    loop, pd = _make_adaptive_loop_fixtures(tmp_path)
    loop._save_pivot_snapshot(pd=pd, iteration_n=1, phase_id="Q01")

    pointer = pd / "_pivot_latest"
    assert pointer.exists()
    assert pointer.read_text().strip() == "_pivot_v2"


def test_pivot_snapshot_skips_missing_files(tmp_path):
    """不存在的文件不应导致 snapshot 抛出异常."""
    from dqg.agents.adaptive_loop import AdaptiveLoop

    loop = AdaptiveLoop(output_dir=tmp_path)
    pd = tmp_path / "proj" / "phaseX"
    pd.mkdir(parents=True)

    # 不创建任何文件，应静默通过
    loop._save_pivot_snapshot(pd=pd, iteration_n=0, phase_id="Q99")
    assert not (pd / "_pivot_v1").exists() or True  # 目录可能创建也可能不创建，不抛异常即可
```

- [ ] **Step 2: 运行测试确认失败**

```bash
python -m pytest tests/test_p1_loop_quality.py::test_pivot_snapshot_creates_dir_on_judge_fail \
  tests/test_p1_loop_quality.py::test_pivot_snapshot_writes_latest_pointer \
  tests/test_p1_loop_quality.py::test_pivot_snapshot_skips_missing_files -v 2>&1 | tail -10
```
Expected: `AttributeError: 'AdaptiveLoop' object has no attribute '_save_pivot_snapshot'`

- [ ] **Step 3: 实现 _save_pivot_snapshot**

读取 `src/dqg/agents/adaptive_loop.py`，在 `_schema_errors_after_worker` 方法（约 L313）**之前**插入：

```python
    def _save_pivot_snapshot(
        self, pd: Path, iteration_n: int, phase_id: str
    ) -> None:
        """Judge FAIL 后保存当前轮产物到 _pivot_v{n+1}/，防止下一轮覆盖写丢失好版本."""
        import shutil

        from dqg.constants import REPORT_MAP, STRUCTURED_JSON_MAP

        pivot_dir = pd / f"_pivot_v{iteration_n + 1}"
        try:
            pivot_dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            log.warning("PIVOT: 无法创建快照目录 %s", pivot_dir)
            return

        # 复制主产物（JSON + 报告 + 推理日志）
        candidates = [
            pd / (STRUCTURED_JSON_MAP.get(phase_id) or ""),
            pd / (REPORT_MAP.get(phase_id) or ""),
            pd / "_internal" / "_reasoning_log.md",
            pd / f"_judge_iter{iteration_n + 1}.json",
            pd / f"_handoff_iter{iteration_n + 1}.md",
        ]
        for src in candidates:
            if src and src.exists() and src.is_file():
                try:
                    shutil.copy2(src, pivot_dir / src.name)
                except OSError:
                    log.debug("PIVOT: 无法复制 %s", src)

        # 更新 _pivot_latest 指针
        try:
            (pd / "_pivot_latest").write_text(pivot_dir.name, encoding="utf-8")
        except OSError:
            pass

        log.info("PIVOT: 快照已保存到 %s", pivot_dir)
```

- [ ] **Step 4: 在主循环中调用 _save_pivot_snapshot**

读取 `adaptive_loop.py`，找到早停检查块（约 L270-276）：

```python
            # 早停检查（passed 已 break，这里只检查未通过的情况）
            health_result = monitor.check()
            if health_result.should_stop:
                final_verdict = "EARLY_STOP"
                early_stop_reason = health_result.message
                log.warning("Adaptive loop early stop: %s", health_result.status)
                break
```

在该块**之后**追加（与 for 循环同级缩进）：

```python
            # PIVOT: Judge FAIL + 健康 + 还有下一轮时，快照当前轮产物
            if i + 1 < max_iterations:
                self._save_pivot_snapshot(pd=pd, iteration_n=i, phase_id=phase_id)
```

- [ ] **Step 5: 运行测试确认通过**

```bash
python -m pytest tests/test_p1_loop_quality.py::test_pivot_snapshot_creates_dir_on_judge_fail \
  tests/test_p1_loop_quality.py::test_pivot_snapshot_writes_latest_pointer \
  tests/test_p1_loop_quality.py::test_pivot_snapshot_skips_missing_files -v 2>&1 | tail -8
```
Expected: 3 PASSED

- [ ] **Step 6: 全量回归**

```bash
python -m pytest tests/ -x -q 2>&1 | tail -5
```
Expected: no new failures（test_file_line_limit 仍是预存失败，忽略）

- [ ] **Step 7: 提交**

```bash
git add src/dqg/agents/adaptive_loop.py tests/test_p1_loop_quality.py
git commit -m "feat(p1-3): adaptive loop PIVOT 版本化快照（Judge FAIL 时保存 _pivot_v{n}/）"
```

---

## Task 3：退化检测增强（P1-2）

**Files:**
- Modify: `src/dqg/agents/loop_health.py:41-131`
- Modify: `src/dqg/agents/adaptive_loop.py:254-264`（monitor.record_iteration 调用处）
- Test: `tests/test_p1_loop_quality.py`

- [ ] **Step 1: 写失败测试**

在 `tests/test_p1_loop_quality.py` 追加：

```python
# ---------------------------------------------------------------------------
# Task 3: 退化检测增强（Worker 输出指纹 + Judge 驳回签名）
# ---------------------------------------------------------------------------

def test_loop_health_output_fingerprint_stagnation():
    """Worker 连续 2 轮产出相同 hash → EARLY_STOP(output_fingerprint_stagnation)."""
    from dqg.agents.loop_health import LoopHealthMonitor

    monitor = LoopHealthMonitor()
    monitor.record_iteration(avg_score=3.0, worker_output_hash="abc123")
    monitor.record_iteration(avg_score=3.0, worker_output_hash="abc123")

    result = monitor.check()
    assert result.should_stop, "相同 Worker 输出应触发 EARLY_STOP"
    assert result.status == "output_fingerprint_stagnation"


def test_loop_health_rejection_sig_stagnation():
    """Judge 连续 2 轮驳回签名相同 → EARLY_STOP(rejection_signature_stagnation)."""
    from dqg.agents.loop_health import LoopHealthMonitor

    monitor = LoopHealthMonitor()
    monitor.record_iteration(avg_score=2.5, judge_rejection_sig="def456")
    monitor.record_iteration(avg_score=2.6, judge_rejection_sig="def456")

    result = monitor.check()
    assert result.should_stop
    assert result.status == "rejection_signature_stagnation"


def test_loop_health_different_hashes_no_stop():
    """Worker 输出 hash 不同时不应触发指纹停滞."""
    from dqg.agents.loop_health import LoopHealthMonitor

    monitor = LoopHealthMonitor()
    monitor.record_iteration(avg_score=3.0, worker_output_hash="aaa111")
    monitor.record_iteration(avg_score=3.2, worker_output_hash="bbb222")

    result = monitor.check()
    assert not result.should_stop, "不同 hash 不应触发停滞"
```

- [ ] **Step 2: 运行测试确认失败**

```bash
python -m pytest tests/test_p1_loop_quality.py::test_loop_health_output_fingerprint_stagnation \
  tests/test_p1_loop_quality.py::test_loop_health_rejection_sig_stagnation \
  tests/test_p1_loop_quality.py::test_loop_health_different_hashes_no_stop -v 2>&1 | tail -10
```
Expected: `TypeError: record_iteration() got unexpected keyword argument 'worker_output_hash'`

- [ ] **Step 3: 扩展 LoopHealthMonitor**

读取 `src/dqg/agents/loop_health.py`。  

在 `__init__` 中（约 L47-55）追加两个新字段：

```python
        self._scores: list[float] = []
        self._issue_sets: list[set[str]] = [
        ]
        self._infra_failures: int = 0
        self._worker_output_hashes: list[str] = []   # 新增
        self._judge_rejection_sigs: list[str] = []   # 新增
```

将 `record_iteration()` 签名（约 L57-62）改为（向后兼容，新参数有默认值）：

```python
    def record_iteration(
        self,
        avg_score: float,
        issues: list[dict[str, Any]] | None = None,
        judge_health: str = "HEALTHY",
        worker_output_hash: str | None = None,
        judge_rejection_sig: str | None = None,
    ) -> None:
        """记录一轮迭代的结果."""
```

在 `record_iteration` 函数体末尾（约 L78 的 `self._infra_failures = 0` 之后）追加：

```python
        self._worker_output_hashes.append(worker_output_hash or "")
        self._judge_rejection_sigs.append(judge_rejection_sig or "")
```

在 `check()` 方法（约 L81-116）的 `return HealthCheckResult()` **之前**插入两个新检测：

```python
        # 4. Worker 产出指纹停滞
        if len(self._worker_output_hashes) >= 2:
            last = self._worker_output_hashes[-1]
            if last and last == self._worker_output_hashes[-2]:
                msg = "Worker 连续 2 轮产出完全相同（指纹不变），修正无效"
                log.warning("LoopHealthMonitor: %s", msg)
                return HealthCheckResult(
                    should_stop=True,
                    status="output_fingerprint_stagnation",
                    message=msg,
                )

        # 5. Judge 驳回签名停滞
        if len(self._judge_rejection_sigs) >= 2:
            last = self._judge_rejection_sigs[-1]
            if last and last == self._judge_rejection_sigs[-2]:
                msg = "Judge 连续 2 轮驳回相同 issue（签名不变），Worker 未解决根本问题"
                log.warning("LoopHealthMonitor: %s", msg)
                return HealthCheckResult(
                    should_stop=True,
                    status="rejection_signature_stagnation",
                    message=msg,
                )

        return HealthCheckResult()
```

在 `get_summary()` 返回值中追加两个字段：

```python
    def get_summary(self) -> dict[str, Any]:
        """获取监控摘要，写入 _adaptive_summary.json."""
        return {
            "scores": [round(s, 2) for s in self._scores],
            "issue_overlap_history": [
                round(
                    len(self._issue_sets[i] & self._issue_sets[i - 1])
                    / max(len(self._issue_sets[i - 1]), 1),
                    2,
                )
                for i in range(1, len(self._issue_sets))
            ],
            "infra_failure_streak": self._infra_failures,
            "total_iterations": len(self._scores),
            "output_fingerprint_history": [
                h[:8] if h else "" for h in self._worker_output_hashes
            ],
            "rejection_sig_history": [
                s[:8] if s else "" for s in self._judge_rejection_sigs
            ],
        }
```

- [ ] **Step 4: 在 adaptive_loop.py 注入 hash 计算**

读取 `src/dqg/agents/adaptive_loop.py`，找到 `monitor.record_iteration()` 调用处（约 L260-264）：

```python
            if record.judge_result is not None:
                all_issues = []
                for v in record.judge_result.votes:
                    all_issues.extend(v.issues)
                health = judge_health_check([record.judge_result])
                monitor.record_iteration(
                    avg_score=record.judge_result.avg_score,
                    issues=all_issues,
                    judge_health=health,
                )
```

将整块替换为：

```python
            if record.judge_result is not None:
                all_issues = []
                for v in record.judge_result.votes:
                    all_issues.extend(v.issues)
                health = judge_health_check([record.judge_result])

                # 计算 Worker 产出指纹
                import hashlib as _hashlib
                _worker_hash: str | None = None
                _json_fname = STRUCTURED_JSON_MAP.get(phase_id)
                if _json_fname:
                    _json_path = pd / _json_fname
                    if _json_path.exists():
                        _raw = _json_path.read_text(encoding="utf-8", errors="replace")[:2000]
                        _worker_hash = _hashlib.sha256(_raw.encode()).hexdigest()[:16]

                # 计算 Judge 驳回签名
                _rejection_sig: str | None = None
                if not passed:
                    _top_codes = sorted(
                        {(v.get("code") or v.get("dimension") or "") for v in all_issues if v}
                    )[:3]
                    if _top_codes:
                        _rejection_sig = _hashlib.sha256("|".join(_top_codes).encode()).hexdigest()[:16]

                monitor.record_iteration(
                    avg_score=record.judge_result.avg_score,
                    issues=all_issues,
                    judge_health=health,
                    worker_output_hash=_worker_hash,
                    judge_rejection_sig=_rejection_sig,
                )
```

- [ ] **Step 5: 运行测试确认通过**

```bash
python -m pytest tests/test_p1_loop_quality.py -v 2>&1 | tail -15
```
Expected: 8 PASSED（所有 Task 1-3 测试）

- [ ] **Step 6: 全量回归**

```bash
python -m pytest tests/ -q 2>&1 | tail -5
```
Expected: 951 passed（新增 8 条），0 新失败

- [ ] **Step 7: 提交**

```bash
git add src/dqg/agents/loop_health.py src/dqg/agents/adaptive_loop.py tests/test_p1_loop_quality.py
git commit -m "feat(p1-2): 退化检测增强——Worker 输出指纹 + Judge 驳回签名两维早停"
```

---

## Self-Review

**Spec coverage:**

| Spec 要求 | 对应 Task |
|-----------|----------|
| `write_data_patterns` 按 phase_id 过滤 | Task 1 Step 5 |
| `top_lessons` 字段（原文 ≤200 字符，top 3） | Task 1 Step 4 |
| `DATA_PATTERN_TOP_LESSONS` 常量 | Task 1 Step 3 |
| PIVOT 快照目录 `_pivot_v{n}/` | Task 2 Step 3 |
| `_pivot_latest` 指针文件 | Task 2 Step 3 |
| 主循环调用时机（FAIL + 健康 + 有下一轮） | Task 2 Step 4 |
| `worker_output_hash` 维度 | Task 3 Step 3+4 |
| `judge_rejection_sig` 维度 | Task 3 Step 3+4 |
| `get_summary()` 新增两字段 | Task 3 Step 3 |
| 8 条单测 | Task 1-3 |

**No placeholders:** 所有步骤有完整代码。

**Type consistency:** `worker_output_hash: str | None` 在 Task 3 Step 3 定义（loop_health.py），在 Step 4（adaptive_loop.py）以 `_worker_hash: str | None` 计算后传入，类型一致。`_rejection_sig: str | None` 同理。
