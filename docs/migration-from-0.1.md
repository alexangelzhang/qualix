# DQG 0.1 → 0.2 迁移指南

> 0.2 引入了工具化分发边界：DQG 源码与你的项目物理隔离。

## 变化

- DQG 源码不再在你的 cwd 下；通过 `pip install --user` 装到 site-packages
- 资源（skills/references/profiles/regression）拷贝到 `~/.dqg/`
- 你的项目下新建 `.dqg/` 工作区（output + settings）
- `CLAUDE.md` 会被追加一段 DQG 使用规约（marker 包裹）

## 从 0.1 迁移步骤

### 1. 安装新版 DQG

```bash
cd <DQG repo 目录>
git pull
./install.sh            # 非 dev 用户
# 或
./install.sh --dev      # 你是 DQG 维护者
```

### 2. 在你的项目目录初始化工作区

```bash
cd <你的项目目录>
qualix-run init
```

这会创建：
- `.dqg/output/` — 运行输出写这里
- `.dqg/settings.yaml` — profile、code_repos 等
- `.gitignore` 追加 `.dqg/output/`
- `CLAUDE.md` 追加 guardrail 段落

### 3. 迁移自定义配置（如果有）

| 0.1 放哪里 | 0.2 放哪里 |
|-----------|------------|
| DQG repo 下 `profiles/your-profile/` | `<你的项目>/.dqg/profiles/your-profile/` |
| DQG repo 下你改过的 skills 片段 | `<你的项目>/.dqg/skill-overrides/` |
| DQG repo 下 `output/<pid>/` | `<你的项目>/.dqg/output/<pid>/` |

`.dqg/profiles/` 和 `.dqg/skill-overrides/` 子目录 `init` 不会预建；有需要手动 `mkdir` 后放进去，`ResourceResolver` 会自动检测并优先使用。

### 4. 填写 settings.yaml 的 code_repos

```yaml
code_repos:
  - /absolute/path/to/your-service
```

### 5. 验证

```bash
qualix-run status --json
```

预期：正常输出，无 deprecation warning。

## 常见问题

### deprecation warning 出现

表示 cwd 里仍有 `src/dqg/` 和 `skills/` 共存的老布局。按上面步骤换到新工作区。3 个月后 warning 升级为 error。

### `~/.dqg/` 要不要手动清理

重跑 `./install.sh` 会覆盖资源目录，不会删额外文件。要彻底清理运行 `rm -rf ~/.dqg`。

### 多项目复用

一次 `install.sh` 后，每个项目分别 `cd` 进去跑 `qualix-run init`，各自有独立 `.dqg/output/`，共享 `~/.dqg/` 资源。

### 如何回滚到 0.1

```bash
pip uninstall qualix
rm -rf ~/.dqg
cd <DQG repo>
git checkout <0.1 tag>
pip install -e .
```

## 相关文档

- 设计背景: `docs/superpowers/specs/2026-05-11-dqg-tool-distribution-design.md`
- 实施 plan: `docs/superpowers/plans/2026-05-11-dqg-tool-distribution.md`
- ROADMAP §F
