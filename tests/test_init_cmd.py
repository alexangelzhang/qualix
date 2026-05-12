"""dqg-run init (workspace-level) 命令测试."""

from dqg.commands.init import GUARDRAIL_BEGIN, GUARDRAIL_END, _detect_code_repos, run_init


def test_init_creates_workspace(tmp_path):
    rc = run_init(project_root=tmp_path, profile="java-ddd", force=False)
    assert rc == 0
    assert (tmp_path / ".dqg" / "output").is_dir()
    settings = (tmp_path / ".dqg" / "settings.yaml").read_text()
    assert "profile: java-ddd" in settings
    assert "dqg_version:" in settings
    claude_md = (tmp_path / "CLAUDE.md").read_text()
    assert GUARDRAIL_BEGIN in claude_md
    assert GUARDRAIL_END in claude_md


def test_init_idempotent_claude_md(tmp_path):
    """重跑 init --force 时 CLAUDE.md marker 节被替换而非重复追加."""
    (tmp_path / "CLAUDE.md").write_text("# 我的原始 CLAUDE.md\n\n已有内容\n")
    run_init(project_root=tmp_path, profile="java-ddd", force=False)
    run_init(project_root=tmp_path, profile="java-ddd", force=True)
    second = (tmp_path / "CLAUDE.md").read_text()
    assert "# 我的原始 CLAUDE.md" in second
    assert "已有内容" in second
    assert second.count(GUARDRAIL_BEGIN) == 1
    assert second.count(GUARDRAIL_END) == 1


def test_init_refuses_existing_without_force(tmp_path):
    (tmp_path / ".dqg").mkdir()
    rc = run_init(project_root=tmp_path, profile="java-ddd", force=False)
    assert rc != 0


def test_init_force_clobbers_existing(tmp_path):
    (tmp_path / ".dqg").mkdir()
    (tmp_path / ".dqg" / "stale.txt").write_text("old")
    rc = run_init(project_root=tmp_path, profile="java-ddd", force=True)
    assert rc == 0
    assert (tmp_path / ".dqg" / "output").is_dir()


def test_init_force_preserves_output(tmp_path):
    """--force 只重置配置文件，output/ 下的项目产物不受影响."""
    # 先 init 一次
    run_init(project_root=tmp_path, profile="java-ddd", force=False)
    # 写入假产物
    proj_dir = tmp_path / ".dqg" / "output" / "my-project"
    proj_dir.mkdir(parents=True)
    (proj_dir / "state.json").write_text('{"phase": "Q01"}')
    # --force 重跑
    rc = run_init(project_root=tmp_path, profile="java-ddd", force=True)
    assert rc == 0
    # 产物仍在
    assert (proj_dir / "state.json").exists()
    assert (proj_dir / "state.json").read_text() == '{"phase": "Q01"}'
    # 配置文件已重建
    settings = (tmp_path / ".dqg" / "settings.yaml").read_text()
    assert "dqg_version:" in settings


def test_init_appends_gitignore(tmp_path):
    (tmp_path / ".gitignore").write_text("node_modules/\n")
    run_init(project_root=tmp_path, profile="java-ddd", force=False)
    content = (tmp_path / ".gitignore").read_text()
    assert ".dqg/output/" in content
    assert "node_modules/" in content


def test_init_creates_gitignore_if_absent(tmp_path):
    run_init(project_root=tmp_path, profile="java-ddd", force=False)
    content = (tmp_path / ".gitignore").read_text()
    assert ".dqg/output/" in content


def test_init_skips_duplicate_gitignore_entry(tmp_path):
    (tmp_path / ".gitignore").write_text(".dqg/output/\n")
    run_init(project_root=tmp_path, profile="java-ddd", force=False)
    content = (tmp_path / ".gitignore").read_text()
    assert content.count(".dqg/output/") == 1


def test_init_new_claude_md_created_when_absent(tmp_path):
    """原来没 CLAUDE.md 时 init 新建一份只含 guardrail 的."""
    run_init(project_root=tmp_path, profile="java-ddd", force=False)
    claude_md = (tmp_path / "CLAUDE.md").read_text()
    assert GUARDRAIL_BEGIN in claude_md
    assert GUARDRAIL_END in claude_md


def test_detect_code_repos_finds_git_subdirs(tmp_path):
    """_detect_code_repos 应返回直接子目录中含 .git/ 的路径."""
    (tmp_path / "repo-a" / ".git").mkdir(parents=True)
    (tmp_path / "repo-b" / ".git").mkdir(parents=True)
    (tmp_path / "not-a-repo").mkdir()
    repos = _detect_code_repos(tmp_path)
    assert str(tmp_path / "repo-a") in repos
    assert str(tmp_path / "repo-b") in repos
    assert str(tmp_path / "not-a-repo") not in repos


def test_detect_code_repos_empty_when_none(tmp_path):
    """无 git 子目录时返回空列表."""
    (tmp_path / "docs").mkdir()
    assert _detect_code_repos(tmp_path) == []


def test_init_writes_detected_repos_to_settings(tmp_path):
    """init 时自动扫描到的 git 子仓库应写入 settings.yaml code_repos."""
    (tmp_path / "service-a" / ".git").mkdir(parents=True)
    (tmp_path / "service-b" / ".git").mkdir(parents=True)
    run_init(project_root=tmp_path, profile="java-ddd", force=False)
    settings = (tmp_path / ".dqg" / "settings.yaml").read_text()
    assert "service-a" in settings
    assert "service-b" in settings
    assert "code_repos:" in settings


def test_init_empty_code_repos_when_no_git_subdirs(tmp_path):
    """无 git 子目录时 settings.yaml 保留空 code_repos 占位."""
    run_init(project_root=tmp_path, profile="java-ddd", force=False)
    settings = (tmp_path / ".dqg" / "settings.yaml").read_text()
    assert "code_repos: []" in settings


def test_install_claude_commands_copies_md_files(tmp_path, monkeypatch):
    """_install_claude_commands 应把 claude_commands 目录下的 .md 文件复制到 .claude/commands/."""
    from dqg.commands.init import _install_claude_commands

    # 构造一个假的 claude_commands 源目录
    fake_src = tmp_path / "fake_pkg" / "claude_commands"
    fake_src.mkdir(parents=True)
    (fake_src / "dqg-starter.md").write_text("# dqg-starter")
    (fake_src / "other.txt").write_text("not md")

    # monkeypatch ResourceResolver.resolve_dir 返回假目录
    from dqg.core import resource_resolver

    monkeypatch.setattr(
        resource_resolver.ResourceResolver,
        "resolve_dir",
        lambda self, cat: fake_src if cat == "claude_commands" else (_ for _ in ()).throw(FileNotFoundError()),
    )

    dest_root = tmp_path / "project"
    dest_root.mkdir()
    installed = _install_claude_commands(dest_root)

    assert "dqg-starter.md" in installed
    assert (dest_root / ".claude" / "commands" / "dqg-starter.md").exists()
    assert not (dest_root / ".claude" / "commands" / "other.txt").exists()


def test_install_claude_commands_graceful_when_missing(tmp_path, monkeypatch):
    """claude_commands 目录不存在时静默返回空列表."""
    from dqg.commands.init import _install_claude_commands
    from dqg.core import resource_resolver

    monkeypatch.setattr(
        resource_resolver.ResourceResolver,
        "resolve_dir",
        lambda self, cat: (_ for _ in ()).throw(FileNotFoundError()),
    )
    result = _install_claude_commands(tmp_path)
    assert result == []
