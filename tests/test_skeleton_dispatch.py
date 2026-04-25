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
