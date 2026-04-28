"""Test skeleton extraction dispatch through LanguageProvider."""

from __future__ import annotations


def test_java_provider_extract_skeleton():
    """JavaProvider.extract_skeleton() should produce a SkeletonResult."""
    from dqg.languages.java.provider import JavaProvider

    provider = JavaProvider()
    source = """\
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
"""
    result = provider.extract_skeleton(source)
    assert result is not None
    assert result.skeleton_lines < result.total_lines
    assert result.compression_ratio > 1.0
    # bar body should be collapsed
    assert "{ ... }" in result.skeleton_text

    # With expand_methods, bar should be fully expanded
    result2 = provider.extract_skeleton(source, expand_methods={"bar"})
    assert result2 is not None
    assert "bar" in result2.expanded_methods
    assert "System.out.println" in result2.skeleton_text


def test_handle_code_skeleton_dispatches_through_provider(monkeypatch, tmp_path):
    """handle_code_skeleton should dispatch through LanguageProvider registry."""
    from types import SimpleNamespace

    from dqg.context.code_skeleton import SkeletonResult
    from dqg.json_utils import save_json

    # Setup: create a fake TypeScript file and demand trace
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    ts_file = repo_dir / "service.ts"
    ts_file.write_text("export class Foo { bar() { return 1; } }", encoding="utf-8")

    output_dir = tmp_path / "output"
    phase_dir = output_dir / "test-proj" / "Q07" / "_internal"
    phase_dir.mkdir(parents=True)

    save_json(
        phase_dir / "_demand_trace.json",
        {
            "traced_files": ["service.ts"],
            "traced_methods": [{"method": "Foo.bar", "file": "service.ts"}],
        },
    )

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

    # Mock registry — patch on the module that get_registry is imported from
    import dqg.languages.registry as reg_mod

    mock_registry = SimpleNamespace(get=lambda lang_id: MockProvider() if lang_id == "typescript" else None)
    monkeypatch.setattr(reg_mod, "get_registry", lambda: mock_registry)

    # Build ctx and result
    artifacts = {}

    ctx = SimpleNamespace(
        code_repo=str(repo_dir),
        code_repos=[str(repo_dir)],
        output_dir=output_dir,
        project_id="test-proj",
        shared={"language_id": "typescript"},
    )
    phase_result = SimpleNamespace(
        artifacts=artifacts,
        add_artifact=lambda k, v: artifacts.update({k: v}),
    )

    from dqg.runtime.handlers_execute import handle_code_skeleton

    handle_code_skeleton(ctx, phase_result)

    assert len(extract_calls) == 1
    assert extract_calls[0]["expand"] == {"bar"}
    assert "code_skeleton_md" in artifacts
