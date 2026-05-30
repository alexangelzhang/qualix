"""Test TypeScript skeleton extraction."""

from __future__ import annotations

import pytest

TS_SOURCE = """\
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
"""


def _skip_if_no_ts():
    from qualix.languages.typescript.ast_analyzer import is_available

    if not is_available():
        pytest.skip("tree-sitter-typescript not available")


def test_ts_skeleton_basic():
    """TypeScript skeleton should preserve signatures, omit bodies."""
    _skip_if_no_ts()
    from qualix.languages.typescript.provider import TypeScriptProvider

    provider = TypeScriptProvider()
    result = provider.extract_skeleton(TS_SOURCE)
    assert result is not None
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
    _skip_if_no_ts()
    from qualix.languages.typescript.provider import TypeScriptProvider

    provider = TypeScriptProvider()
    result = provider.extract_skeleton(TS_SOURCE, expand_methods={"findById"})
    assert result is not None
    assert "findById" in result.expanded_methods
    assert "findOne" in result.skeleton_text  # body content visible
    # Other methods still collapsed
    assert result.skeleton_text.count("{ ... }") >= 2


def test_ts_skeleton_empty_source():
    """Empty source should return minimal result."""
    _skip_if_no_ts()
    from qualix.languages.typescript.provider import TypeScriptProvider

    provider = TypeScriptProvider()
    result = provider.extract_skeleton("")
    if result is not None:
        assert result.total_lines == 0 or result.skeleton_text == ""
