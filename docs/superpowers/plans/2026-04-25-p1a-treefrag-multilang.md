# P1-A: TREEFRAG Multi-Language Skeleton Extraction

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend TREEFRAG code skeleton compression from Java-only to TypeScript and Python, so Q07 code review gets 10-18x context compression for all supported languages.

**Architecture:** Add `extract_skeleton()` method to `LanguageProvider` interface with a default regex-based implementation. Override in TypeScript provider using the existing tree-sitter-typescript parser. Create a new Python provider with tree-sitter-python. Refactor `handle_code_skeleton` to dispatch through the provider registry instead of calling Java-specific code directly.

**Tech Stack:** Python, tree-sitter, tree-sitter-typescript (already used in TS ast_analyzer), tree-sitter-python (new optional dep)

---

## File Structure

| Action | File | Responsibility |
|--------|------|----------------|
| Modify | `src/dqg/languages/base.py` | Add `extract_skeleton()` method to LanguageProvider ABC |
| Modify | `src/dqg/languages/java/provider.py` | Implement `extract_skeleton()` delegating to existing code_skeleton.py |
| Modify | `src/dqg/languages/typescript/provider.py` | Implement `extract_skeleton()` using tree-sitter-typescript |
| Create | `src/dqg/languages/typescript/skeleton.py` | TypeScript skeleton extraction logic |
| Modify | `src/dqg/runtime/handlers_execute.py:207-288` | Dispatch through provider registry instead of Java-specific code |
| Modify | `src/dqg/context/code_skeleton.py` | Keep as Java-specific impl, called by JavaProvider |
| Create | `tests/test_skeleton_typescript.py` | TypeScript skeleton extraction tests |
| Create | `tests/test_skeleton_dispatch.py` | Handler dispatch tests |

---

### Task 1: Add `extract_skeleton()` to LanguageProvider interface

**Files:**
- Modify: `src/dqg/languages/base.py:196-203` (after `parse_source`)
- Test: inline verification

- [ ] **Step 1: Write the interface method**

In `src/dqg/languages/base.py`, add after the `parse_source` method (around line 203):

```python
def extract_skeleton(
    self,
    source: str,
    expand_methods: set[str] | None = None,
) -> SkeletonResult | None:
    """Extract code skeleton: signatures + fields, omit method bodies.

    Methods in expand_methods are fully expanded (Oracle annotation).
    Returns None if skeleton extraction is not supported for this language.

    Default: returns None (unsupported). Subclasses override.
    """
    return None
```

Also add the import at the top of base.py (TYPE_CHECKING block):

```python
if TYPE_CHECKING:
    from dqg.context.code_skeleton import SkeletonResult
```

And add a runtime import guard in the method docstring or use a string annotation.

Actually, since `SkeletonResult` is a dataclass in `code_skeleton.py`, and we want to avoid circular imports, use a string annotation:

```python
def extract_skeleton(
    self,
    source: str,
    expand_methods: set[str] | None = None,
) -> "SkeletonResult | None":
```

- [ ] **Step 2: Verify no import errors**

Run: `cd /Users/zhangyiqian/git_dev/dev-quality-gate/dev-quality-gate && python -c "from dqg.languages.base import LanguageProvider; print('OK')"`
Expected: OK

- [ ] **Step 3: Commit**

```bash
git add src/dqg/languages/base.py
git commit -m "feat(languages): add extract_skeleton() to LanguageProvider interface"
```

---

### Task 2: Implement `extract_skeleton()` in JavaProvider

**Files:**
- Modify: `src/dqg/languages/java/provider.py`
- Test: `tests/test_skeleton_dispatch.py` (new)

- [ ] **Step 1: Write the failing test**

Create `tests/test_skeleton_dispatch.py`:

```python
"""Test skeleton extraction dispatch through LanguageProvider."""
from __future__ import annotations


def test_java_provider_extract_skeleton():
    """JavaProvider.extract_skeleton() should produce a SkeletonResult."""
    from dqg.languages.java.provider import JavaProvider

    provider = JavaProvider()
    source = '''
package com.example;

public class Foo {
    private int count;

    public void bar(String name) {
        System.out.println(name);
        count++;
    }

    public int getCount() {
        return count;
    }
}
'''
    result = provider.extract_skeleton(source)
    assert result is not None
    assert result.skeleton_lines < result.total_lines
    assert result.compression_ratio > 1.0
    assert "bar" not in result.skeleton_text or "{ ... }" in result.skeleton_text
    # With expand_methods, bar should be fully expanded
    result2 = provider.extract_skeleton(source, expand_methods={"bar"})
    assert result2 is not None
    assert "bar" in result2.expanded_methods
    assert "System.out.println" in result2.skeleton_text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_skeleton_dispatch.py::test_java_provider_extract_skeleton -v`
Expected: FAIL — JavaProvider has no extract_skeleton method

- [ ] **Step 3: Implement in JavaProvider**

In `src/dqg/languages/java/provider.py`, add:

```python
def extract_skeleton(
    self,
    source: str,
    expand_methods: set[str] | None = None,
) -> "SkeletonResult | None":
    """Extract Java code skeleton using tree-sitter (regex fallback)."""
    from dqg.context.code_skeleton import extract_skeleton
    return extract_skeleton(source, expand_methods)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_skeleton_dispatch.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/dqg/languages/java/provider.py tests/test_skeleton_dispatch.py
git commit -m "feat(java): implement extract_skeleton() in JavaProvider"
```

---

### Task 3: Implement TypeScript skeleton extraction

**Files:**
- Create: `src/dqg/languages/typescript/skeleton.py`
- Modify: `src/dqg/languages/typescript/provider.py`
- Test: `tests/test_skeleton_typescript.py` (new)

- [ ] **Step 1: Write the failing test**

Create `tests/test_skeleton_typescript.py`:

```python
"""Test TypeScript skeleton extraction."""
from __future__ import annotations


TS_SOURCE = '''
import { Injectable } from '@nestjs/common';
import { Repository } from 'typeorm';

interface UserDTO {
    id: number;
    name: string;
    email: string;
}

@Injectable()
export class UserService {
    private readonly repo: Repository<User>;

    constructor(repo: Repository<User>) {
        this.repo = repo;
    }

    async findById(id: number): Promise<UserDTO | null> {
        const user = await this.repo.findOne({ where: { id } });
        if (!user) return null;
        return { id: user.id, name: user.name, email: user.email };
    }

    async create(dto: UserDTO): Promise<UserDTO> {
        const entity = this.repo.create(dto);
        const saved = await this.repo.save(entity);
        return { id: saved.id, name: saved.name, email: saved.email };
    }

    private validate(dto: UserDTO): boolean {
        return dto.name.length > 0 && dto.email.includes('@');
    }
}
'''


def test_ts_skeleton_basic():
    """TypeScript skeleton should preserve signatures, omit bodies."""
    from dqg.languages.typescript.provider import TypeScriptProvider

    provider = TypeScriptProvider()
    result = provider.extract_skeleton(TS_SOURCE)
    if result is None:
        import pytest
        pytest.skip("tree-sitter-typescript not available")

    assert result.skeleton_lines < result.total_lines
    assert result.compression_ratio > 1.0
    # Interface should be preserved fully
    assert "UserDTO" in result.skeleton_text
    # Method signatures should be present
    assert "findById" in result.skeleton_text
    assert "create" in result.skeleton_text
    assert "validate" in result.skeleton_text
    # Method bodies should be collapsed
    assert "{ ... }" in result.skeleton_text
    # Imports should be preserved
    assert "import" in result.skeleton_text


def test_ts_skeleton_expand_methods():
    """Oracle-marked methods should be fully expanded."""
    from dqg.languages.typescript.provider import TypeScriptProvider

    provider = TypeScriptProvider()
    result = provider.extract_skeleton(TS_SOURCE, expand_methods={"findById"})
    if result is None:
        import pytest
        pytest.skip("tree-sitter-typescript not available")

    assert "findById" in result.expanded_methods
    assert "findOne" in result.skeleton_text  # body content visible
    # Other methods still collapsed
    assert result.skeleton_text.count("{ ... }") >= 2


def test_ts_skeleton_empty_source():
    """Empty source should return minimal result."""
    from dqg.languages.typescript.provider import TypeScriptProvider

    provider = TypeScriptProvider()
    result = provider.extract_skeleton("")
    # Either None or empty result is acceptable
    if result is not None:
        assert result.total_lines == 0 or result.skeleton_text == ""
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_skeleton_typescript.py -v`
Expected: FAIL or SKIP

- [ ] **Step 3: Create TypeScript skeleton extraction module**

Create `src/dqg/languages/typescript/skeleton.py`:

```python
"""TypeScript TREEFRAG skeleton extraction using tree-sitter.

Extracts class/interface/function signatures, omits method bodies.
Oracle-marked methods are fully expanded.
"""
from __future__ import annotations

from dqg.context.code_skeleton import SkeletonClass, SkeletonMethod, SkeletonResult
from dqg.log import get_logger

log = get_logger(__name__)


def extract_skeleton_ts(
    source: str,
    expand_methods: set[str] | None = None,
) -> SkeletonResult | None:
    """Extract TypeScript code skeleton using tree-sitter.

    Returns None if tree-sitter-typescript is not available.
    """
    from dqg.languages.typescript.ast_analyzer import _ensure_parser, _parser

    if not _ensure_parser() or _parser is None:
        return None

    expand = expand_methods or set()
    source_bytes = source.encode("utf-8")
    tree = _parser.parse(source_bytes)
    root = tree.root_node

    skeleton_parts: list[str] = []
    classes: list[SkeletonClass] = []
    expanded: list[str] = []

    # Collect imports
    imports: list[str] = []
    for node in root.children:
        if node.type == "import_statement":
            imports.append(_node_text(node, source_bytes))
    if imports:
        skeleton_parts.append("\n".join(imports))

    # Process top-level declarations
    for node in root.children:
        if node.type == "import_statement":
            continue
        elif node.type == "interface_declaration":
            # Interfaces: keep fully (they're already signatures)
            skeleton_parts.append(_node_text(node, source_bytes))
        elif node.type in ("class_declaration", "abstract_class_declaration"):
            cls, cls_text, cls_expanded = _extract_class(node, source_bytes, expand)
            classes.append(cls)
            skeleton_parts.append(cls_text)
            expanded.extend(cls_expanded)
        elif node.type == "export_statement":
            # Check if export wraps a class or interface
            for child in node.children:
                if child.type in ("class_declaration", "abstract_class_declaration"):
                    decorators = _collect_decorators(node, source_bytes)
                    cls, cls_text, cls_expanded = _extract_class(child, source_bytes, expand)
                    classes.append(cls)
                    prefix = "\n".join(decorators) + "\n" if decorators else ""
                    skeleton_parts.append(prefix + "export " + cls_text)
                    expanded.extend(cls_expanded)
                elif child.type == "interface_declaration":
                    skeleton_parts.append("export " + _node_text(child, source_bytes))
                elif child.type in ("function_declaration", "lexical_declaration"):
                    text, fn_expanded = _extract_top_level_function(child, source_bytes, expand)
                    skeleton_parts.append("export " + text)
                    expanded.extend(fn_expanded)
        elif node.type in ("function_declaration", "lexical_declaration"):
            text, fn_expanded = _extract_top_level_function(node, source_bytes, expand)
            skeleton_parts.append(text)
            expanded.extend(fn_expanded)

    skeleton_text = "\n\n".join(skeleton_parts)
    total_lines = len(source.splitlines())
    skeleton_lines = len(skeleton_text.splitlines())

    return SkeletonResult(
        skeleton_text=skeleton_text,
        full_text=source,
        classes=classes,
        total_lines=total_lines,
        skeleton_lines=skeleton_lines,
        expanded_methods=expanded,
        compression_ratio=round(total_lines / max(skeleton_lines, 1), 1),
    )


def _node_text(node, source_bytes: bytes) -> str:
    return source_bytes[node.start_byte:node.end_byte].decode("utf-8", errors="replace")


def _collect_decorators(node, source_bytes: bytes) -> list[str]:
    """Collect decorator nodes preceding a declaration."""
    decorators = []
    for child in node.children:
        if child.type == "decorator":
            decorators.append(_node_text(child, source_bytes))
    return decorators


def _find_body(node) -> object | None:
    """Find the statement_block (body) child of a node."""
    for child in node.children:
        if child.type == "statement_block":
            return child
    return None


def _find_name(node, source_bytes: bytes) -> str:
    """Extract identifier name from a declaration node."""
    for child in node.children:
        if child.type in ("identifier", "type_identifier", "property_identifier"):
            return _node_text(child, source_bytes)
    return ""


def _extract_class(node, source_bytes: bytes, expand: set[str]):
    """Extract class skeleton: signature + fields + method signatures."""
    name = _find_name(node, source_bytes)
    body = _find_body(node)

    # Signature: from node start to body start
    if body:
        sig = source_bytes[node.start_byte:body.start_byte].decode("utf-8", errors="replace").strip()
    else:
        sig = _node_text(node, source_bytes)

    cls = SkeletonClass(
        name=name,
        signature=sig,
        line_start=node.start_point[0] + 1,
        line_end=node.end_point[0] + 1,
    )

    lines: list[str] = [sig + " {"]
    expanded_names: list[str] = []

    if body:
        for child in body.children:
            if child.type == "public_field_definition":
                cls.fields.append(_node_text(child, source_bytes))
                lines.append(f"    {_node_text(child, source_bytes)}")
            elif child.type in ("method_definition", "public_field_definition"):
                method = _extract_method(child, source_bytes, expand)
                cls.methods.append(method)
                if method.is_expanded:
                    lines.append(f"    {method.signature} {method.body}")
                    expanded_names.append(method.name)
                else:
                    lines.append(f"    {method.signature} {{ ... }}")
            elif child.type == "property_definition":
                cls.fields.append(_node_text(child, source_bytes))
                lines.append(f"    {_node_text(child, source_bytes)}")

    lines.append("}")
    return cls, "\n".join(lines), expanded_names


def _extract_method(node, source_bytes: bytes, expand: set[str]) -> SkeletonMethod:
    """Extract method skeleton from a method_definition node."""
    name = _find_name(node, source_bytes)
    body = _find_body(node)

    if body:
        sig = source_bytes[node.start_byte:body.start_byte].decode("utf-8", errors="replace").strip()
        body_text = _node_text(body, source_bytes)
    else:
        sig = _node_text(node, source_bytes)
        body_text = ""

    should_expand = name in expand or any(name.lower() == e.lower() for e in expand)

    return SkeletonMethod(
        name=name,
        signature=sig,
        body=body_text,
        line_start=node.start_point[0] + 1,
        line_end=node.end_point[0] + 1,
        is_expanded=should_expand,
    )


def _extract_top_level_function(node, source_bytes: bytes, expand: set[str]):
    """Extract top-level function/const arrow function skeleton."""
    name = _find_name(node, source_bytes)
    body = _find_body(node)

    if body:
        sig = source_bytes[node.start_byte:body.start_byte].decode("utf-8", errors="replace").strip()
        body_text = _node_text(body, source_bytes)
    else:
        # Might be an arrow function in a const declaration
        return _node_text(node, source_bytes), []

    should_expand = name in expand or any(name.lower() == e.lower() for e in expand)

    if should_expand:
        return f"{sig} {body_text}", [name]
    return f"{sig} {{ ... }}", []
```

- [ ] **Step 4: Wire up TypeScriptProvider.extract_skeleton()**

In `src/dqg/languages/typescript/provider.py`, add:

```python
def extract_skeleton(
    self,
    source: str,
    expand_methods: set[str] | None = None,
) -> "SkeletonResult | None":
    """Extract TypeScript code skeleton using tree-sitter."""
    from dqg.languages.typescript.skeleton import extract_skeleton_ts
    return extract_skeleton_ts(source, expand_methods)
```

- [ ] **Step 5: Run tests**

Run: `python -m pytest tests/test_skeleton_typescript.py tests/test_skeleton_dispatch.py -v`
Expected: PASS (or SKIP if tree-sitter-typescript not installed)

- [ ] **Step 6: Commit**

```bash
git add src/dqg/languages/typescript/skeleton.py src/dqg/languages/typescript/provider.py tests/test_skeleton_typescript.py
git commit -m "feat(typescript): add TREEFRAG skeleton extraction for TypeScript"
```

---

### Task 4: Refactor `handle_code_skeleton` to dispatch through provider registry

**Files:**
- Modify: `src/dqg/runtime/handlers_execute.py:207-288`
- Modify: `tests/test_skeleton_dispatch.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_skeleton_dispatch.py`:

```python
def test_handle_code_skeleton_uses_provider(monkeypatch, tmp_path):
    """handle_code_skeleton should dispatch through LanguageProvider, not hardcode Java."""
    from pathlib import Path
    from types import SimpleNamespace

    from dqg.context.code_skeleton import SkeletonResult
    from dqg.json_utils import save_json

    # Setup: create a fake TypeScript file and demand trace
    project_id = "test-proj"
    output_dir = tmp_path / "output"
    phase_dir = output_dir / project_id / "phaseD" / "_internal"
    phase_dir.mkdir(parents=True)

    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    ts_file = repo_dir / "service.ts"
    ts_file.write_text("export class Foo { bar() { return 1; } }", encoding="utf-8")

    save_json(phase_dir / "_demand_trace.json", {
        "traced_files": ["service.ts"],
        "traced_methods": [{"method": "Foo.bar", "file": "service.ts"}],
    })

    # Mock provider that records calls
    extract_calls = []

    class MockProvider:
        language_id = "typescript"

        def extract_skeleton(self, source, expand_methods=None):
            extract_calls.append({"source_len": len(source), "expand": expand_methods})
            return SkeletonResult(
                skeleton_text="export class Foo { bar() { ... } }",
                full_text=source,
                total_lines=1,
                skeleton_lines=1,
                expanded_methods=list(expand_methods or []),
                compression_ratio=1.0,
            )

    # Mock registry
    monkeypatch.setattr(
        "dqg.runtime.handlers_execute.get_registry",
        lambda: SimpleNamespace(get=lambda lang_id: MockProvider() if lang_id == "typescript" else None),
    )

    ctx = SimpleNamespace(
        code_repo=str(repo_dir),
        output_dir=output_dir,
        project_id=project_id,
        shared={"language_id": "typescript"},
        internal_dir=phase_dir,
    )
    result = SimpleNamespace(artifacts={}, add_artifact=lambda k, v: result.artifacts.update({k: v}))

    from dqg.runtime.handlers_execute import handle_code_skeleton
    handle_code_skeleton(ctx, result)

    assert len(extract_calls) == 1
    assert extract_calls[0]["expand"] == {"bar"}
    assert "code_skeleton_md" in result.artifacts
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_skeleton_dispatch.py::test_handle_code_skeleton_uses_provider -v`
Expected: FAIL — handler still calls Java-specific `extract_skeleton_for_files`

- [ ] **Step 3: Refactor handle_code_skeleton**

In `src/dqg/runtime/handlers_execute.py`, replace the `handle_code_skeleton` function:

```python
def handle_code_skeleton(ctx: ExecutionContext, result: PhaseResult) -> None:
    """Phase Q07: TREEFRAG code skeleton compression via LanguageProvider."""
    if not ctx.code_repo:
        return

    from pathlib import Path as _Path

    from dqg.constants import PHASE_DIR_MAP
    from dqg.json_utils import load_json, save_json
    from dqg.languages.registry import get_registry

    lang_id = ctx.shared.get("language_id", "java")
    provider = get_registry().get(lang_id)

    # Fallback: if provider has no extract_skeleton, use Java code_skeleton directly
    if provider is None or not hasattr(provider, "extract_skeleton"):
        from dqg.context.code_skeleton import extract_skeleton_for_files
        _handle_code_skeleton_legacy(ctx, result)
        return

    dir_suffix = PHASE_DIR_MAP.get("Q07", "phaseD")
    int_dir = ctx.output_dir / ctx.project_id / dir_suffix / "_internal"

    target_files: list[_Path] = []
    se_code_mapping: dict[str, list[str]] = {}

    trace_path = int_dir / "_demand_trace.json"
    if trace_path.exists():
        trace_data = load_json(trace_path)
        if trace_data:
            repo = _Path(ctx.code_repo).resolve()
            for f in trace_data.get("traced_files", []):
                fp = repo / f
                if fp.exists():
                    target_files.append(fp)
            for t in trace_data.get("traced_methods", []):
                method = t.get("method", "")
                file_path = t.get("file", "")
                if method and file_path:
                    full = str(repo / file_path)
                    method_name = method.split(".")[-1] if "." in method else method
                    se_code_mapping.setdefault(full, []).append(method_name)

    if not target_files:
        return

    target_files = target_files[:30]

    # Extract skeletons through provider
    from dqg.context.code_skeleton import SkeletonResult
    results: dict[str, SkeletonResult] = {}
    for fp in target_files:
        try:
            source = fp.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        expand = set(se_code_mapping.get(str(fp), []))
        skel = provider.extract_skeleton(source, expand)
        if skel is not None:
            results[str(fp)] = skel

    if not results:
        return

    int_dir.mkdir(parents=True, exist_ok=True)

    skeleton_data = {
        "file_count": len(results),
        "total_lines": sum(r.total_lines for r in results.values()),
        "skeleton_lines": sum(r.skeleton_lines for r in results.values()),
        "expanded_methods": sum(len(r.expanded_methods) for r in results.values()),
        "files": {
            fp: {
                "total_lines": r.total_lines,
                "skeleton_lines": r.skeleton_lines,
                "compression_ratio": r.compression_ratio,
                "expanded_methods": r.expanded_methods,
            }
            for fp, r in results.items()
        },
    }
    json_path = int_dir / "_code_skeleton.json"
    save_json(json_path, skeleton_data)

    md_parts = ["## CODE_SKELETON — TREEFRAG 代码骨架（自动生成）\n"]
    for fp, r in results.items():
        filename = _Path(fp).name
        md_parts.append(f"### {filename} ({r.skeleton_lines}/{r.total_lines} lines, {r.compression_ratio}x)")
        md_parts.append(f"```{lang_id}\n{r.skeleton_text}\n```\n")

    md_path = int_dir / "_code_skeleton.md"
    md_path.write_text("\n".join(md_parts), encoding="utf-8")

    result.add_artifact("code_skeleton_json", str(json_path))
    result.add_artifact("code_skeleton_md", str(md_path))
```

Keep the old implementation as `_handle_code_skeleton_legacy` for fallback (rename the original function body).

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_skeleton_dispatch.py tests/test_skeleton_typescript.py -v`
Expected: ALL PASS

- [ ] **Step 5: Run full test suite**

Run: `python -m pytest tests/ -x -q`
Expected: ALL PASS

- [ ] **Step 6: Commit**

```bash
git add src/dqg/runtime/handlers_execute.py tests/test_skeleton_dispatch.py
git commit -m "refactor(skeleton): dispatch through LanguageProvider registry instead of hardcoded Java"
```

---

## Cost Impact

- Non-Java projects (TypeScript, Python) currently inject full source code into Q07 context
- With TREEFRAG: 10-18x compression on code context
- For a typical 50-file TypeScript PR: ~500K chars → ~30-50K chars of skeleton
- Saves ~$3-5 per Q07 run on non-Java projects
