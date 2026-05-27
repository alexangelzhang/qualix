# Evidence Contract 硬化 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 对 Q01 SE.source、Q05a EUT→code_target、Q06 COVERED 三个维度添加证据验证器，防止 LLM 编造行号/类名/测试位置。

**Architecture:** 新建 `evidence_contract.py` 提供纯函数验证逻辑（可独立测试）；通过现有 `register_handler` / `run_finalize_checks` 扩展点接入，不修改任何已有函数签名。错误字符串用 `BLOCKED:`/`WARNING:` 前缀，由 `build_verdict()` 自动转为 `CheckItem(level=HARD/SOFT)`。

**Tech Stack:** Python 3.11+, Pydantic v2, pytest, pathlib, subprocess (grep)

**Spec:** `docs/superpowers/specs/2026-05-27-evidence-contract-hardening-design.md`

---

## 文件总览

| 操作 | 路径 | 职责 |
|------|------|------|
| CREATE | `src/dqg/quality/checks/evidence_contract.py` | 纯函数：`verify_se_sources` + `check_eut_code_target_traceability` |
| MODIFY | `src/dqg/runtime/handlers/handlers_finalize.py` | 新增 `handle_se_source_evidence` handler + 注册 |
| MODIFY | `src/dqg/quality/checks/finalize_checks.py` | Q05a 分支调用 `check_eut_code_target_traceability` |
| MODIFY | `src/dqg/quality/checks/q06_structure_checks.py` | 新增 `_check_covered_evidence_fields` + 在 `run_q06_structure_checks` 调用 |
| CREATE | `tests/test_evidence_contract.py` | 10 条单测 |
| MODIFY | `ROADMAP.md` | 标记 Evidence Contract P0 已完成，方案 B 加入未来规划 |

---

## Task 1：SE.source 跨引用校验

### 纯函数 `verify_se_sources` + 单测（TDD）

**Files:**
- Create: `src/dqg/quality/checks/evidence_contract.py`
- Create: `tests/test_evidence_contract.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_evidence_contract.py
"""Tests for Evidence Contract verifiers."""
from __future__ import annotations
import json
from pathlib import Path
import pytest
from dqg.quality.checks.evidence_contract import verify_se_sources


def _write_ingest_file(tmp_path: Path, filename: str, lines: list[str]) -> None:
    ingest_dir = tmp_path / "ingest"
    ingest_dir.mkdir(parents=True, exist_ok=True)
    (ingest_dir / filename).write_text("\n".join(lines), encoding="utf-8")


def test_verify_se_sources_ok(tmp_path):
    """source='plain_text.txt:2' 指向真实行 → status=ok, no errors."""
    _write_ingest_file(tmp_path, "plain_text.txt", ["line1", "line2 PRD内容", "line3"])
    se_list = [{"se_id": "SE-001", "source": "plain_text.txt:2"}]
    errors, entries = verify_se_sources(tmp_path, se_list)
    assert errors == []
    assert len(entries) == 1
    assert entries[0]["status"] == "ok"
    assert entries[0]["line_text"] == "line2 PRD内容"


def test_verify_se_sources_empty_source(tmp_path):
    """source='' → status=empty_source, WARNING."""
    se_list = [{"se_id": "SE-002", "source": ""}]
    errors, entries = verify_se_sources(tmp_path, se_list)
    assert any("WARNING" in e for e in errors)
    assert entries[0]["status"] == "empty_source"


def test_verify_se_sources_file_missing(tmp_path):
    """source='nonexist.txt:1' 文件不存在 → BLOCKED."""
    se_list = [{"se_id": "SE-003", "source": "nonexist.txt:1"}]
    errors, entries = verify_se_sources(tmp_path, se_list)
    assert any("BLOCKED" in e for e in errors)
    assert entries[0]["status"] == "file_missing"


def test_verify_se_sources_line_oob(tmp_path):
    """source='plain_text.txt:999' 行号超出 → BLOCKED."""
    _write_ingest_file(tmp_path, "plain_text.txt", ["only one line"])
    se_list = [{"se_id": "SE-004", "source": "plain_text.txt:999"}]
    errors, entries = verify_se_sources(tmp_path, se_list)
    assert any("BLOCKED" in e for e in errors)
    assert entries[0]["status"] == "line_oob"
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd /Users/zhangyiqian/git_dev/dev-quality-gate/dev-quality-gate
python -m pytest tests/test_evidence_contract.py -v 2>&1 | head -30
```
Expected: `ImportError: cannot import name 'verify_se_sources'`

- [ ] **Step 3: 实现 `verify_se_sources`**

新建 `src/dqg/quality/checks/evidence_contract.py`：

```python
"""Evidence Contract 验证器：SE.source 跨引用 + EUT code_target grep."""
from __future__ import annotations

import hashlib
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from dqg.log import get_logger

log = get_logger(__name__)


def verify_se_sources(
    phase_root: Path,
    se_list: list[dict[str, Any]],
) -> tuple[list[str], list[dict[str, Any]]]:
    """验证每条 SE.source 指向的 ingest 文件行号真实存在。

    Args:
        phase_root: Q01 phase 目录（含 ingest/ 子目录）
        se_list:    phase_a_structured.json 中的 semantic_expectations 列表

    Returns:
        (errors, evidence_entries)
        errors: BLOCKED:/WARNING: 字符串列表，直接 extend 到 result.errors
        evidence_entries: 写入 _se_source_evidence.json 的条目列表
    """
    errors: list[str] = []
    entries: list[dict[str, Any]] = []
    ingest_dir = phase_root / "ingest"
    verified_at = datetime.now(UTC).isoformat()

    for se in se_list:
        se_id = se.get("se_id", "?")
        source_raw = (se.get("source") or "").strip()

        if not source_raw:
            entries.append({"se_id": se_id, "source_raw": "", "status": "empty_source", "verified_at": verified_at})
            errors.append(
                f"WARNING: [evidence_contract] {se_id} source 未填写，无法追溯 PRD 原始依据"
            )
            continue

        # 解析 "file:N" 格式
        if ":" not in source_raw:
            entries.append({"se_id": se_id, "source_raw": source_raw, "status": "invalid_format", "verified_at": verified_at})
            errors.append(
                f"WARNING: [evidence_contract] {se_id} source '{source_raw}' 格式无效，期望 'file.txt:行号'"
            )
            continue

        last_colon = source_raw.rfind(":")
        filename = source_raw[:last_colon]
        try:
            line_num = int(source_raw[last_colon + 1:])
        except ValueError:
            entries.append({"se_id": se_id, "source_raw": source_raw, "status": "invalid_format", "verified_at": verified_at})
            errors.append(
                f"WARNING: [evidence_contract] {se_id} source '{source_raw}' 行号非整数"
            )
            continue

        file_path = ingest_dir / filename
        if not file_path.exists():
            entries.append({
                "se_id": se_id, "source_raw": source_raw,
                "source_file": filename, "source_line": line_num,
                "status": "file_missing", "verified_at": verified_at,
            })
            errors.append(
                f"BLOCKED: [evidence_contract] {se_id} source '{source_raw}' 指向的 ingest 文件不存在"
            )
            continue

        all_lines = file_path.read_text(encoding="utf-8", errors="replace").splitlines()
        if line_num < 1 or line_num > len(all_lines):
            entries.append({
                "se_id": se_id, "source_raw": source_raw,
                "source_file": filename, "source_line": line_num,
                "status": "line_oob", "verified_at": verified_at,
                "file_total_lines": len(all_lines),
            })
            errors.append(
                f"BLOCKED: [evidence_contract] {se_id} source '{source_raw}' 行号超出范围"
                f" (文件共 {len(all_lines)} 行)"
            )
            continue

        # 成功：提取行文本 + 上下文
        line_text = all_lines[line_num - 1]
        ctx_start = max(0, line_num - 3)
        ctx_end = min(len(all_lines), line_num + 2)
        context_lines = all_lines[ctx_start:ctx_end]
        context_hash = hashlib.sha256(line_text.encode()).hexdigest()[:16]

        entries.append({
            "se_id": se_id,
            "source_raw": source_raw,
            "source_file": filename,
            "source_line": line_num,
            "line_text": line_text,
            "context_lines": context_lines,
            "context_hash": context_hash,
            "status": "ok",
            "verified_at": verified_at,
        })

    return errors, entries
```

- [ ] **Step 4: 运行测试确认通过**

```bash
python -m pytest tests/test_evidence_contract.py::test_verify_se_sources_ok \
  tests/test_evidence_contract.py::test_verify_se_sources_empty_source \
  tests/test_evidence_contract.py::test_verify_se_sources_file_missing \
  tests/test_evidence_contract.py::test_verify_se_sources_line_oob -v
```
Expected: 4 PASSED

- [ ] **Step 5: 提交**

```bash
git add src/dqg/quality/checks/evidence_contract.py tests/test_evidence_contract.py
git commit -m "feat(evidence-contract): verify_se_sources 纯函数 + 4 条单测"
```

---

### `handle_se_source_evidence` handler

**Files:**
- Modify: `src/dqg/runtime/handlers/handlers_finalize.py`

- [ ] **Step 6: 写 handler 测试**

在 `tests/test_evidence_contract.py` 追加：

```python
def _make_ctx(tmp_path: Path, phase_id: str = "Q01"):
    from unittest.mock import MagicMock
    ctx = MagicMock()
    ctx.output_dir = tmp_path
    ctx.project_id = "test"
    ctx.phase_id = phase_id
    ctx.phase_root = tmp_path / "test" / phase_id
    ctx.phase_root.mkdir(parents=True, exist_ok=True)
    ctx.internal_dir = ctx.phase_root / "_internal"
    ctx.internal_dir.mkdir(parents=True, exist_ok=True)
    ctx.shared = {}
    return ctx


def _make_result():
    from unittest.mock import MagicMock
    r = MagicMock()
    r.errors = []
    return r


def test_handler_writes_evidence_file_and_blocks_on_invalid_source(tmp_path):
    """handle_se_source_evidence: 行号超出 → BLOCKED + evidence 文件落盘."""
    import json, time
    from dqg.runtime.handlers.handlers_finalize import handle_se_source_evidence

    ctx = _make_ctx(tmp_path)
    # 写 phase_a_structured.json
    structured = {
        "project_id": "test",
        "requirements": [{"req_id": "REQ-001", "description": "x"}],
        "semantic_expectations": [
            {"se_id": "SE-001", "description": "d", "source": "plain_text.txt:999"},
        ],
    }
    (ctx.phase_root / "phase_a_structured.json").write_text(json.dumps(structured))
    # 写 ingest/plain_text.txt（只有 1 行）
    ingest = ctx.phase_root / "ingest"
    ingest.mkdir()
    (ingest / "plain_text.txt").write_text("only one line")

    result = _make_result()
    handle_se_source_evidence(ctx, result)

    assert any("BLOCKED" in e for e in result.errors)
    # 等待异步写盘
    time.sleep(0.1)
    ev_path = ctx.internal_dir / "_se_source_evidence.json"
    assert ev_path.exists()
    data = json.loads(ev_path.read_text())
    assert data["entries"][0]["status"] == "line_oob"
```

- [ ] **Step 7: 运行确认失败**

```bash
python -m pytest tests/test_evidence_contract.py::test_handler_writes_evidence_file_and_blocks_on_invalid_source -v
```
Expected: `ImportError: cannot import name 'handle_se_source_evidence'`

- [ ] **Step 8: 实现 handler**

读取 `handlers_finalize.py` 当前内容（必须先 Read 再 Edit）。在 `handle_hard_gate` 函数（L22）**之前**插入新函数：

```python
def handle_se_source_evidence(ctx: ExecutionContext, result: PhaseResult) -> None:
    """Q01: 校验每条 SE.source 指向的 ingest 文件行号真实存在，落盘 _se_source_evidence.json."""
    from dqg.json_utils import load_json
    from dqg.quality.checks.evidence_contract import verify_se_sources
    from dqg.text_utils import STRUCTURED_JSON_MAP

    json_fname = STRUCTURED_JSON_MAP.get("Q01", "phase_a_structured.json")
    if not ctx.phase_root:
        return
    json_path = ctx.phase_root / json_fname
    if not json_path.exists():
        return  # hard_gate 会捕获

    data = load_json(json_path) or {}
    se_list = data.get("semantic_expectations", [])
    if not se_list:
        return

    errors, entries = verify_se_sources(ctx.phase_root, se_list)
    result.errors.extend(errors)

    evidence = {"verified_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(), "entries": entries}
    if ctx.internal_dir:
        async_write_json(ctx.internal_dir / "_se_source_evidence.json", evidence)
```

在 `register_finalize_handlers()` 函数的 Group 1 循环**之前**（order=57，先于 hard_gate 的 58）插入注册行：

```python
    # SE.source 跨引用校验：Q01 专属，必须在 hard_gate 之前（order=57）
    register_handler(
        "se_source_evidence",
        handle_se_source_evidence,
        stage="finalize",
        order=57,
        phases={"Q01"},
        required=True,
    )
```

- [ ] **Step 9: 运行测试确认通过**

```bash
python -m pytest tests/test_evidence_contract.py -v
```
Expected: 5 PASSED

- [ ] **Step 10: 全量回归**

```bash
python -m pytest tests/ -x -q 2>&1 | tail -5
```
Expected: all passed, 0 failed

- [ ] **Step 11: 提交**

```bash
git add src/dqg/runtime/handlers/handlers_finalize.py tests/test_evidence_contract.py
git commit -m "feat(evidence-contract): handle_se_source_evidence handler (Q01 finalize, order=57)"
```

---

## Task 2：EUT → SE.code_target grep（Q05a）

**Files:**
- Modify: `src/dqg/quality/checks/evidence_contract.py`
- Modify: `src/dqg/quality/checks/finalize_checks.py`
- Modify: `tests/test_evidence_contract.py`

- [ ] **Step 1: 写失败测试**

在 `tests/test_evidence_contract.py` 追加：

```python
def test_check_eut_code_target_found(tmp_path):
    """SE.code_target 类名在 code_repo 中能 grep 到 → 无 warning."""
    from dqg.quality.checks.evidence_contract import check_eut_code_target_traceability

    # 建 Q01 产物
    q01_dir = tmp_path / "test" / "Q01"
    q01_dir.mkdir(parents=True)
    q01_data = {
        "project_id": "test",
        "requirements": [{"req_id": "REQ-001", "description": "x"}],
        "semantic_expectations": [
            {"se_id": "SE-001", "description": "d", "code_target": "OrderService"},
        ],
    }
    import json
    (q01_dir / "phase_a_structured.json").write_text(json.dumps(q01_data))

    # 建 Q05a 产物
    q05a_dir = tmp_path / "test" / "Q05a"
    q05a_dir.mkdir(parents=True)
    q05a_data = {
        "eut_items": [{"eut_id": "EUT-001", "bound_item": "SE-001", "given": "g", "when": "w", "then": "assertEquals(x, y)", "route_type": "HAPPY_PATH"}],
    }
    (q05a_dir / "phase_b_structured.json").write_text(json.dumps(q05a_data))

    # 建 code_repo：含 OrderService.java
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "OrderService.java").write_text("public class OrderService {}")

    errors = check_eut_code_target_traceability(tmp_path, "test", [str(repo)])
    assert errors == []


def test_check_eut_code_target_not_found(tmp_path):
    """SE.code_target 在 code_repo 中 grep 不到 → WARNING."""
    from dqg.quality.checks.evidence_contract import check_eut_code_target_traceability
    import json

    q01_dir = tmp_path / "test" / "Q01"
    q01_dir.mkdir(parents=True)
    q01_data = {
        "project_id": "test",
        "requirements": [{"req_id": "REQ-001", "description": "x"}],
        "semantic_expectations": [
            {"se_id": "SE-001", "description": "d", "code_target": "GhostService"},
        ],
    }
    (q01_dir / "phase_a_structured.json").write_text(json.dumps(q01_data))

    q05a_dir = tmp_path / "test" / "Q05a"
    q05a_dir.mkdir(parents=True)
    q05a_data = {
        "eut_items": [{"eut_id": "EUT-001", "bound_item": "SE-001", "given": "g", "when": "w", "then": "assertEquals(x, y)", "route_type": "HAPPY_PATH"}],
    }
    (q05a_dir / "phase_b_structured.json").write_text(json.dumps(q05a_data))

    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "OrderService.java").write_text("public class OrderService {}")

    errors = check_eut_code_target_traceability(tmp_path, "test", [str(repo)])
    assert any("WARNING" in e for e in errors)
    assert any("GhostService" in e for e in errors)


def test_check_eut_code_target_empty_skips(tmp_path):
    """SE.code_target='' → skip, 无 warning."""
    from dqg.quality.checks.evidence_contract import check_eut_code_target_traceability
    import json

    q01_dir = tmp_path / "test" / "Q01"
    q01_dir.mkdir(parents=True)
    q01_data = {
        "project_id": "test",
        "requirements": [{"req_id": "REQ-001", "description": "x"}],
        "semantic_expectations": [
            {"se_id": "SE-001", "description": "d", "code_target": ""},
        ],
    }
    (q01_dir / "phase_a_structured.json").write_text(json.dumps(q01_data))

    q05a_dir = tmp_path / "test" / "Q05a"
    q05a_dir.mkdir(parents=True)
    q05a_data = {"eut_items": [{"eut_id": "EUT-001", "bound_item": "SE-001", "given": "g", "when": "w", "then": "assertEquals(x, y)", "route_type": "HAPPY_PATH"}]}
    (q05a_dir / "phase_b_structured.json").write_text(json.dumps(q05a_data))

    errors = check_eut_code_target_traceability(tmp_path, "test", [str(tmp_path / "repo")])
    assert errors == []
```

- [ ] **Step 2: 运行确认失败**

```bash
python -m pytest tests/test_evidence_contract.py::test_check_eut_code_target_found \
  tests/test_evidence_contract.py::test_check_eut_code_target_not_found \
  tests/test_evidence_contract.py::test_check_eut_code_target_empty_skips -v
```
Expected: `ImportError: cannot import name 'check_eut_code_target_traceability'`

- [ ] **Step 3: 实现 `check_eut_code_target_traceability`**

在 `evidence_contract.py` 尾部追加：

```python
def check_eut_code_target_traceability(
    output_dir: Path,
    project_id: str,
    code_repos: list[str],
) -> list[str]:
    """Q05a: 对每条 EUT，追踪 bound_item → SE.code_target → grep 代码仓库。

    SE.code_target 为空时跳过（SE 未定义 impl 目标）。
    grep 不到始终是 WARNING（不 BLOCKED），因为 TDD 场景下 impl 可能尚未存在。
    """
    from dqg.constants import STRUCTURED_JSON_MAP
    from dqg.core.phase_registry import PHASE_DEFS
    from dqg.core.state_machine import phase_dir as _phase_dir
    from dqg.json_utils import load_json

    if not code_repos:
        return []

    # 加载 Q01 SE → code_target 映射
    phase_def_q01 = PHASE_DEFS.get("Q01")
    if not phase_def_q01:
        return []
    q01_json = _phase_dir(output_dir, project_id, phase_def_q01) / STRUCTURED_JSON_MAP.get("Q01", "phase_a_structured.json")
    q01_data = load_json(q01_json) if q01_json.is_file() else {}
    se_code_target: dict[str, str] = {
        se["se_id"]: se.get("code_target", "")
        for se in (q01_data or {}).get("semantic_expectations", [])
        if se.get("se_id")
    }

    # 加载 Q05a EUT 列表
    phase_def_q05a = PHASE_DEFS.get("Q05a")
    if not phase_def_q05a:
        return []
    q05a_json = _phase_dir(output_dir, project_id, phase_def_q05a) / STRUCTURED_JSON_MAP.get("Q05a", "phase_b_structured.json")
    q05a_data = load_json(q05a_json) if q05a_json.is_file() else {}
    eut_items = (q05a_data or {}).get("eut_items", [])

    errors: list[str] = []
    for eut in eut_items:
        eut_id = eut.get("eut_id", "?")
        bound = (eut.get("bound_item") or eut.get("bound_se") or "").strip()
        if not bound.startswith("SE-"):
            continue
        code_target = se_code_target.get(bound, "")
        if not code_target:
            continue  # SE 未定义 impl 目标，跳过

        # 提取类名（取第一个 '.' 前的部分）
        class_name = code_target.split(".")[0].strip()
        if not class_name:
            continue

        # grep 所有 code_repos
        found = False
        for repo_str in code_repos:
            repo_path = Path(repo_str).expanduser().resolve()
            if not repo_path.is_dir():
                continue
            try:
                result = subprocess.run(
                    ["grep", "-rl", "-F", class_name, str(repo_path)],
                    capture_output=True, text=True, timeout=10,
                )
                if result.stdout.strip():
                    found = True
                    break
            except (subprocess.TimeoutExpired, FileNotFoundError):
                log.debug("grep failed for %s in %s", class_name, repo_path)

        if not found:
            errors.append(
                f"WARNING: [evidence_contract] {eut_id} bound {bound}.code_target"
                f" '{class_name}' 在代码仓库中未找到，请确认实现类名"
            )

    return errors
```

- [ ] **Step 4: 运行测试确认通过**

```bash
python -m pytest tests/test_evidence_contract.py::test_check_eut_code_target_found \
  tests/test_evidence_contract.py::test_check_eut_code_target_not_found \
  tests/test_evidence_contract.py::test_check_eut_code_target_empty_skips -v
```
Expected: 3 PASSED

- [ ] **Step 5: 接入 `finalize_checks.py`**

读取 `finalize_checks.py`，在 `run_finalize_checks` 中找到 `if phase_id in ("Q05", "Q05a"):` 的结构合规块（约 L194），在其**之后**插入 Q05a 的 code_target 检查：

```python
    # Q05a: EUT → SE.code_target 可追溯性检查（始终 WARNING）
    if phase_id == "Q05a":
        from dqg.quality.checks.evidence_contract import check_eut_code_target_traceability

        phase_def_q05a = PHASE_DEFS.get("Q05a")
        if phase_def_q05a:
            int_dir_q05a = _internal_dir(output_dir, project_id, phase_def_q05a)
            inputs_data_q05a = load_json(int_dir_q05a / "_inputs.json") if (int_dir_q05a / "_inputs.json").is_file() else {}
            code_repos_q05a: list[str] = inputs_data_q05a.get("code_repos", []) if isinstance(inputs_data_q05a, dict) else []
            if not code_repos_q05a and isinstance(inputs_data_q05a, dict) and inputs_data_q05a.get("code_repo"):
                code_repos_q05a = [inputs_data_q05a["code_repo"]]
            errors.extend(check_eut_code_target_traceability(output_dir, project_id, code_repos_q05a))
```

- [ ] **Step 6: 全量回归**

```bash
python -m pytest tests/ -x -q 2>&1 | tail -5
```
Expected: all passed

- [ ] **Step 7: 提交**

```bash
git add src/dqg/quality/checks/evidence_contract.py \
        src/dqg/quality/checks/finalize_checks.py \
        tests/test_evidence_contract.py
git commit -m "feat(evidence-contract): check_eut_code_target_traceability (Q05a WARNING)"
```

---

## Task 3：Q06 COVERED 证据字段强制

**Files:**
- Modify: `src/dqg/quality/checks/q06_structure_checks.py`
- Modify: `tests/test_evidence_contract.py`

- [ ] **Step 1: 写失败测试**

在 `tests/test_evidence_contract.py` 追加：

```python
def test_covered_no_evidence_warns(tmp_path):
    """COVERED + test_class='' + test_location=None → WARNING."""
    from dqg.quality.checks.q06_structure_checks import _check_covered_evidence_fields

    data = {
        "audit_items": [
            {"eut_id": "EUT-001", "status": "COVERED", "test_class": "", "test_method": "", "test_location": None},
        ]
    }
    errors = _check_covered_evidence_fields(data, [])
    assert any("WARNING" in e for e in errors)


def test_covered_with_test_class_passes(tmp_path):
    """COVERED + test_class 有值 → 无 error."""
    from dqg.quality.checks.q06_structure_checks import _check_covered_evidence_fields

    data = {
        "audit_items": [
            {"eut_id": "EUT-001", "status": "COVERED", "test_class": "OrderServiceTest", "test_location": None},
        ]
    }
    errors = _check_covered_evidence_fields(data, [])
    assert errors == []


def test_covered_test_location_file_not_found_blocks(tmp_path):
    """COVERED + test_location.file 在 code_repo 中找不到 → BLOCKED."""
    from dqg.quality.checks.q06_structure_checks import _check_covered_evidence_fields

    repo = tmp_path / "repo"
    repo.mkdir()
    data = {
        "audit_items": [
            {
                "eut_id": "EUT-001",
                "status": "COVERED",
                "test_class": "",
                "test_location": {"file": "src/test/OrderTest.java", "line_start": 5},
            },
        ]
    }
    errors = _check_covered_evidence_fields(data, [str(repo)])
    assert any("BLOCKED" in e for e in errors)
```

- [ ] **Step 2: 运行确认失败**

```bash
python -m pytest tests/test_evidence_contract.py::test_covered_no_evidence_warns \
  tests/test_evidence_contract.py::test_covered_with_test_class_passes \
  tests/test_evidence_contract.py::test_covered_test_location_file_not_found_blocks -v
```
Expected: `ImportError: cannot import name '_check_covered_evidence_fields'`

- [ ] **Step 3: 实现 `_check_covered_evidence_fields`**

读取 `q06_structure_checks.py`，在 `_check_test_class_method_exists` 函数（L260）**之前**插入：

```python
def _check_covered_evidence_fields(
    data: dict[str, Any],
    code_repos: list[str],
) -> list[str]:
    """G10: COVERED 条目必须提供 test_class 或 test_location 作为证据位置。

    - test_class='' 且 test_location=None → WARNING（无证据）
    - test_location.file 设置了但在 code_repos 中找不到 → BLOCKED（幻觉文件路径）
    """
    errors: list[str] = []
    covered_items = [
        i for i in data.get("audit_items", [])
        if isinstance(i, dict) and str(i.get("status", "")) == "COVERED"
    ]
    if not covered_items:
        return []

    for item in covered_items:
        eut_id = item.get("eut_id", "?")
        test_class = (item.get("test_class") or "").strip()
        test_location = item.get("test_location")
        loc_file = ""
        if isinstance(test_location, dict):
            loc_file = (test_location.get("file") or "").strip()

        if not test_class and not loc_file:
            errors.append(
                f"WARNING: [evidence_contract] {eut_id} COVERED 但未提供"
                " test_class 或 test_location，无可追溯的测试证据"
            )
            continue

        if loc_file and code_repos:
            found = any(
                list(Path(r).expanduser().resolve().rglob(Path(loc_file).name))
                for r in code_repos
                if Path(r).expanduser().resolve().is_dir()
            )
            if not found:
                errors.append(
                    f"BLOCKED: [evidence_contract] {eut_id} COVERED test_location.file"
                    f" '{loc_file}' 在代码仓库中不存在，疑似幻觉路径"
                )

    return errors
```

- [ ] **Step 4: 在 `run_q06_structure_checks` 中调用**

读取 `q06_structure_checks.py`，在 `run_q06_structure_checks` 的 `errors.extend(_check_test_class_method_exists(...))` 行（约 L253）**之后**追加：

```python
    # G10: COVERED 条目证据字段强制
    errors.extend(_check_covered_evidence_fields(data, code_repos))
```

- [ ] **Step 5: 运行测试确认通过**

```bash
python -m pytest tests/test_evidence_contract.py -v
```
Expected: 10 PASSED

- [ ] **Step 6: 全量回归**

```bash
python -m pytest tests/ -x -q 2>&1 | tail -5
```
Expected: all passed, 0 failed

- [ ] **Step 7: 提交**

```bash
git add src/dqg/quality/checks/q06_structure_checks.py tests/test_evidence_contract.py
git commit -m "feat(evidence-contract): _check_covered_evidence_fields (Q06 G10)"
```

---

## Task 4：ROADMAP 更新

**Files:**
- Modify: `ROADMAP.md`

- [ ] **Step 1: 在 `ROADMAP.md` §C 防幻觉架构 P0 部分标记完成**

找到 `2026-05-19 规划（统一 claim/evidence/verifier/gate 防幻觉架构）` 下的 P0 三项，在段落开头追加：

```markdown
2026-05-27 完成（Evidence Contract 硬化 方案 A）：

- SE.source 跨引用校验：`handle_se_source_evidence`（Q01 finalize order=57）读取 ingest 文件行号，source 非空但无效 → BLOCKED，落盘 `_internal/_se_source_evidence.json`
- EUT → SE.code_target grep：`check_eut_code_target_traceability`（Q05a finalize）grep 代码仓库，未找到 → WARNING
- Q06 COVERED 证据字段：`_check_covered_evidence_fields`（G10）无 test_class 且无 test_location → WARNING，test_location.file 不存在 → BLOCKED
- 实现：`src/dqg/quality/checks/evidence_contract.py` + 10 条单测（`tests/test_evidence_contract.py`）
```

在同一 §C 的 `P1` 规划块末尾追加（方案 B 记录）：

```markdown
- **方案 B Evidence Contract（未来架构优化）** — EutItem 加 `impl_class: str = ""` 显式字段（替代通过 SE.code_target 间接推导）；EutAuditItem 当 `status=COVERED` 时 `test_class` Pydantic validator 强制非空。触发条件：Q05a 出现 >20% impl 未找到且确认不是 TDD 场景；或 LLM 频繁填写 ghost impl_class 的具体案例。
```

- [ ] **Step 2: 提交 ROADMAP**

```bash
git add ROADMAP.md
git commit -m "docs(roadmap): 标记 Evidence Contract P0 已完成，方案 B 记入未来规划"
```

---

## Self-Review

**Spec coverage check：**

| Spec 要求 | 对应 Task |
|-----------|----------|
| Q01 SE.source → 真实 PRD 行号 | Task 1: `verify_se_sources` + handler |
| source 非空但无效 → BLOCKED | Task 1: `line_oob` / `file_missing` 分支 |
| source 空 → WARNING | Task 1: `empty_source` 分支 |
| `_se_source_evidence.json` 落盘 | Task 1: Step 8 handler |
| Q05a EUT → SE.code_target grep | Task 2: `check_eut_code_target_traceability` |
| 未找到 → WARNING（非 BLOCKED） | Task 2 设计 |
| Q06 COVERED 无 test_class/location → WARNING | Task 3: G10 |
| test_location.file 不存在 → BLOCKED | Task 3: G10 |
| 10 条单测 | Tasks 1-3 测试步骤 |
| ROADMAP 更新 | Task 4 |

**No placeholders：** 所有步骤有完整代码，无 TBD/TODO。

**Type consistency：** `verify_se_sources` 签名 `(phase_root: Path, se_list: list[dict]) -> tuple[list[str], list[dict]]` 在 Task 1 Step 3 定义，在 Task 1 Step 8 handler 中调用，签名一致。`check_eut_code_target_traceability` 签名 `(output_dir, project_id, code_repos) -> list[str]` 在 Task 2 Step 3 定义，在 finalize_checks.py 调用一致。
