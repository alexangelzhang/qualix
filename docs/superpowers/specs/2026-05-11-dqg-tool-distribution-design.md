# DQG 工具化分发 — 设计文档

> 对应 ROADMAP §F「规模化分发边界」。采纳 L1 备选路径（install.sh + `~/.dqg/`），不发 PyPI。实施切片 A：物理边界先行，工作区和 doctor 后续。

## 背景与目标

DQG 当前只能 `git clone` 后在仓库内运行，工具源码与用户项目处在同一 cwd。外部用户接入时 Claude 会把 DQG bug 当作"顺手修源码"的任务处理，带来:

1. 用户 patch 随 `git pull` 被冲掉
2. Claude 把 `src/dqg/` 误读为用户代码，消耗 token 并误建议
3. 维护者分不清"真 bug"和"用户自己改出的 bug"

目标是建立物理分发边界：用户项目 cwd 看不到 DQG 源码，Claude 读不到就不会改。

VAF(`vibe-agentic-flow`) 已用 `install.sh + ~/.vcb` 验证过这种模式；DQG 借鉴它的拷贝流程，补上 Python 包安装环节。

## 关键决策概览

| 决策点 | 结论 | 理由 |
|-------|------|------|
| 覆盖 ROADMAP §F 哪几层 | L1 备选 + L2 + L3 全覆盖 | 三层都是分发边界的一部分 |
| Python 代码怎么装 | `pip install --user` 到 site-packages | 与 L1 正版 PyPI 路径兼容，升级顺滑 |
| 资源放哪里 | `~/.dqg/` + site-packages 兜底 | 跨项目共享，VAF 验证过 |
| 资源查找顺序 | 项目 `.dqg/` → `~/.dqg/` → `importlib.resources` | 高优先级覆盖低优先级 |
| 用户工作区 `.dqg/` | `output/` + `settings.yaml`；`profiles/` / `skill-overrides/` 按需自建 | 工具低心智成本，能力保留但入口不推销 |
| 开发者 vs 用户 | `install.sh --dev` 用 symlink + `pip install -e .` | 改源码即时生效 |
| CLAUDE.md guardrail | 默认静默追加（marker 包裹） | L3 软防御直达效果 |
| 版本号单一源 | 根目录 `VERSION` 文件，`pyproject.toml` dynamic 读 | 从 0.1.0 盘活 |
| `regression/` 归属 | 全局 `~/.dqg/regression/` | 失败样例库跨项目共享 |
| issue 上传机制 | 借助 `glab` CLI，不可用时 fallback 手动 | DQG 不管 token 生命周期 |
| issue URL 单一源 | `pyproject.toml [project.urls].Issues` | 标准位置，工具代码动态读 |

## 架构

### 三类目录

```
DQG 仓库（维护者）          ~/.dqg/（全局）              用户项目（外部用户）
─────────────────           ────────────                 ──────────────────
src/dqg/*.py   ──装包──▶    site-packages/dqg/           .dqg/
skills/        ──拷贝──▶    ~/.dqg/skills/                 ├── output/        运行输出
references/    ──拷贝──▶    ~/.dqg/references/             └── settings.yaml  DQG 版本 pin + 偏好
profiles/      ──拷贝──▶    ~/.dqg/profiles/
regression/    ──拷贝──▶    ~/.dqg/regression/
VERSION        ──读取──▶    ~/.dqg/VERSION
pyproject.toml ──dynamic──▶ 从 VERSION 读版本
install.sh     ──执行──▶    编排以上拷贝 + pip 安装
```

### 三类角色

| 角色 | 安装命令 | cwd | `~/.dqg/` | site-packages |
|------|---------|-----|-----------|---------------|
| 维护者 | `./install.sh --dev` | DQG repo 根 | symlink 指回 repo | `pip install -e .` |
| 外部用户 | `./install.sh` | 用户项目 | 真实文件拷贝 | `pip install --user .` |
| CI 环境 | 同用户，`--output-root` 可改 | 构建工作区 | 按 `--output-root` 放 | 同用户 |

### 运行时资源查找顺序

1. 项目级覆盖：`<cwd>/.dqg/skill-overrides/` 或 `<cwd>/.dqg/profiles/`（用户手动 mkdir 创建，init 不预建）
2. 全局：`~/.dqg/skills/`、`~/.dqg/references/`、`~/.dqg/profiles/`
3. 包内兜底：`importlib.resources.files("dqg")/skills/` 等

`regression/` 走 1→2，不放包内（体积大）。`output/` 固定写项目级 `.dqg/output/`。

### 统一资源解析器

所有路径推导收口到 `src/dqg/core/resource_resolver.py`:

```python
class ResourceResolver:
    """三层回退资源查找"""
    def __init__(self, project_root: Path | None = None):
        self.project_root = project_root or Path.cwd()
        self.project_dqg = self.project_root / ".dqg"
        self.global_dqg = Path.home() / ".dqg"

    def resolve(self, category: str, relative: str) -> Path:
        """按 项目级 → 全局 → 包内 顺序查找"""
```

`context_loader.py` / `skill_loader.py` / `phase_registry.py` 等原先用 `Path(__file__).parents[N]` 拼路径的地方全部迁到 ResourceResolver。

## 核心组件

### `install.sh`

#### 命令签名

```
./install.sh [--dev] [--output-root PATH] [--source-root PATH] [--dry-run] [--skip-pip]
```

| 参数 | 默认 | 作用 |
|------|------|------|
| `--dev` | 否 | 维护者模式：`~/.dqg/*` 用 symlink 指回 source-root；pip 走 `-e .` |
| `--output-root` | `~/.dqg` | 资源根目录。CI 可改 |
| `--source-root` | install.sh 所在目录 | DQG 仓库根 |
| `--dry-run` | 否 | 只打印计划不落盘 |
| `--skip-pip` | 否 | 只拷资源不装包 |

#### 执行步骤（非 --dev）

1. 定位 source-root，校验 `skills/ references/ profiles/ regression/ VERSION pyproject.toml` 都存在，缺任一报错退出
2. 读 `VERSION`，打印 banner `DQG version: <version>`
3. 四类资源逐个拷到 `~/.dqg/<name>/`，覆盖式（先删旧 dest 再 copytree）
4. `VERSION` 拷到 `~/.dqg/VERSION`
5. 跑 `pip install --user <source-root>`（非 --dev）或 `pip install --user -e <source-root>`（--dev）
6. 打印 next steps：`cd 你的项目目录; dqg-run init`

#### --dev 模式差异

- 步骤 3/4 改为 `os.symlink(source-root/<name>, ~/.dqg/<name>)`
- 重跑时发现 `~/.dqg/<name>` 已是 symlink 指向当前 source-root 则跳过
- 发现是真实目录（之前跑过非 dev）则报错要求先 `rm -rf ~/.dqg/<name>`（不自动覆盖防误删）

#### 不做

- 不做 `--uninstall`（靠 `rm -rf ~/.dqg/ && pip uninstall dev-quality-gate`）
- 不做升级子命令（重跑 install.sh 即升级）
- 不自动写 `~/.zshrc`（`pip install --user` 装的命令默认在 PATH；不在则在 next steps 提示）

### `dqg-run init`

#### 命令签名

```
dqg-run init [--profile PROFILE_NAME] [--force]
```

| 参数 | 默认 | 作用 |
|------|------|------|
| `--profile` | `java-ddd` | 写入 settings.yaml 的默认 profile |
| `--force` | 否 | 删除已有 `.dqg/` 后重建；settings.yaml 的 code_repos 会丢失，执行前打印 warning 让用户二次确认 |

#### 执行步骤

1. 检查 cwd 是否已有 `.dqg/`，有且无 `--force` 则报错退出
2. 创建目录结构：
   ```
   .dqg/
   ├── output/
   └── settings.yaml
   ```
3. 写 `settings.yaml`：
   ```yaml
   # DQG 项目配置 — 由 dqg-run init 生成
   dqg_version: "0.2.0-dev.20260511"   # 自动写入，勿手改
   profile: java-ddd
   code_repos: []   # 填写代码仓绝对路径
   ```
4. 向 cwd 的 `CLAUDE.md` 末尾追加 guardrail 章节（marker 包裹，幂等替换）：
   ```markdown
   <!-- DQG-GUARDRAIL-BEGIN -->
   ## DQG 使用规约

   DQG 是通过 install.sh 安装的工具，**不要修改它的源码**。

   遇到 DQG 报错时：
   1. 跑 `dqg-run doctor` 生成 issue bundle
   2. 把 bundle 提交给 DQG 维护者

   相关资源：
   - `dqg-run --help` — CLI 完整参数
   - `dqg-run path <skills|references|profiles>` — 查看内置资源
   <!-- DQG-GUARDRAIL-END -->
   ```
   - CLAUDE.md 不存在时新建只含该段的文件
   - 已有 marker 则替换而非重复追加
5. 向 `.gitignore` 追加 `.dqg/output/`（若未包含）
6. 打印 next steps

#### 不做

- 不预建 `.dqg/profiles/` / `.dqg/skill-overrides/`（能力保留，入口不推销；用户需要时手动 mkdir 就会被 ResourceResolver 捡起）
- 不拷 profile 模板（避免副本幽灵化）
- 不做 `dqg-run deinit`（用户自行 `rm -rf`）
- 不做 `.dqg/cache/` 或 `.dqg/knowledge/`

### `dqg-run doctor`

#### 命令签名

```
dqg-run doctor [--output PATH] [--redact/--no-redact] [--include-internal/--no-include-internal] [--no-upload] [--title TITLE]
```

| 参数 | 默认 | 作用 |
|------|------|------|
| `--output` | `.dqg/doctor-bundle-<ts>.tgz` | bundle 路径 |
| `--redact` | 是 | 脱敏绝对路径、用户名、token 前缀 |
| `--include-internal` | 是 | 含最近一次 `output/<project>/_internal/` |
| `--no-upload` | 否 | 只生成 bundle，不调 glab |
| `--title` | 交互式提示 | issue 标题；非 TTY 用 `[doctor] <last-error-oneline>` 兜底 |

#### bundle 内容

```
doctor-bundle-20260511-142301.tgz
├── manifest.json       # 版本/时间/触发原因/脱敏摘要
├── env.txt             # dqg --version、python、pip list、OS
├── settings.yaml       # .dqg/settings.yaml 副本（脱敏）
├── recent-errors/      # 最近一次 dqg-run 的 stderr / exceptions
├── state.json          # output/<project>/state.json（脱敏）
├── _internal/          # 最近 phase 的 _reasoning_log.md 等
└── input-summary.txt   # 输入文件列表 + 大小（不含内容）
```

#### 数据来源

- **last-run marker**: `dqg-run` 启动时 atomic-write 一份 `.dqg/last-run.json`（cmd、ts、cwd、exit-code、tail-stderr），doctor 主要读这个
- **state.json**: 当前 project 的状态快照
- `_internal/`: 按 state.json 里最近的 phase 取
- **settings.yaml**: 直接拷贝后脱敏

#### 脱敏策略

- 绝对路径中的用户名用 `<user>` 替换
- 字符串中的 token 前缀（`sk-`、`claude-`、`Bearer `）打码
- 不扫文档原文（防泄露业务信息），`input-summary.txt` 只列文件名/大小
- `--no-redact` 跳过脱敏，仅用于本地自查；与上传互斥（强制禁止）

#### 版本一致性检查

对比三处：`pip show dev-quality-gate`、`~/.dqg/VERSION`、`.dqg/settings.yaml` 的 `dqg_version`。不一致时 `manifest.json` 标 `version_mismatch: true` 并提示重跑 `install.sh`。

#### 自动上传（基于 glab）

1. `shutil.which("glab")` + `glab auth status` 退出码检测。失败则 fallback 到手动模式（打印 bundle 路径 + issue URL），退出 0 不报错
2. TTY 环境问标题，非 TTY 兜底
3. `glab issue create --repo <path> --title ... --description ...` 创建 issue 并附文件。新版 glab 支持 `-F/--file`；旧版 fallback 到"创建 issue → `glab api projects/:id/uploads`"两步
4. 解析 stdout 得到 issue URL，打印

glab 缺失提示：
```
⚠  未检测到 glab CLI 或未登录 (`glab auth status` 失败)
   bundle 已生成，请手动上传到:
   https://github.com/your-org/rd-gate/-/issues/new
   安装 glab 后可启用自动上传: brew install glab && glab auth login -h your-gitlab-host
```

#### 边界

- `--no-upload` 留逃生口
- `--redact=false` + 上传 → 组合禁止，报错退出
- glab 调用超时 30s，超时后 fallback 手动
- glab 退出非零且 stderr 含 `permission denied` → 提示"token 权限不够，需要 `api` scope，重跑 `glab auth login --scopes api`"

### 版本管理

- 根目录新增 `VERSION` 文件，内容仅为版本字符串（如 `0.2.0-dev.20260511`），无其他格式
- `pyproject.toml` 改为：
  ```toml
  [project]
  name = "dev-quality-gate"
  dynamic = ["version"]

  [project.urls]
  Homepage = "https://github.com/your-org/rd-gate"
  Issues = "https://github.com/your-org/rd-gate/-/issues"
  Source = "https://github.com/your-org/rd-gate"

  [tool.hatch.version]
  path = "VERSION"
  pattern = "(?P<version>.+)"

  [tool.hatch.build.targets.wheel.force-include]
  "skills" = "dqg/skills"
  "references" = "dqg/references"
  "profiles" = "dqg/profiles"
  ```
  注：hatchling ≥ 1.18 支持从纯文本文件读版本（regex source + pattern 匹配整行）。
- `src/dqg/__init__.py`：`__version__ = importlib.metadata.version("dev-quality-gate")`
- `install.sh` 读 `VERSION` 文件打 banner + 拷到 `~/.dqg/VERSION`
- 所有代码读版本/URL 统一走 `importlib.metadata`，不硬编码

## 数据流

### 用户首次接入

```
1. git clone + ./install.sh
   → 资源拷 ~/.dqg/，pip install --user .，dqg-run 进 ~/.local/bin/
2. cd 用户项目 + dqg-run init
   → 建 .dqg/output/，写 settings.yaml，注入 CLAUDE.md，追 .gitignore
3. 用户填 .dqg/settings.yaml 的 code_repos
4. dqg-run <project_id> startup
   → ResourceResolver 查资源：.dqg/ → ~/.dqg/ → site-packages
   → output 写到 .dqg/output/
5. 遇错：dqg-run doctor
   → 生成脱敏 bundle → glab 创建 issue（或 fallback 打印路径）
```

### 用户升级

```
1. git pull DQG repo
2. ./install.sh 重跑
   → ~/.dqg/* 被覆盖，site-packages 覆盖，VERSION 更新
3. dqg-run 启动检测 settings.yaml 的 dqg_version ≠ ~/.dqg/VERSION
   → 打印 warning：建议 dqg-run init --force 同步，不 block
```

### 维护者日常

```
1. DQG repo 根执行 ./install.sh --dev
   → ~/.dqg/* 变 symlink，pip install --user -e .
2. 改 skills/*.md 或 src/dqg/*.py 立即生效
3. cd 到测试项目跑 dqg-run，无需重装
```

## 迁移

老用户（原先在 DQG repo 内 `pip install -e .`）按 `docs/migration-from-0.1.md` 手工操作：

1. 家目录外新建"用户项目"工作区
2. 原 `profiles/custom.yaml` 等自定义文件拷到新工作区 `.dqg/profiles/`
3. `dqg-run init` 建 `.dqg/output/` + settings
4. 原 `output/` 历史产物拷到 `.dqg/output/`

第一版不做迁移脚本。VERSION 跳到 `0.2.0` 明示破坏性。老路径（cwd 含 `src/dqg/`）保留 3 个月兼容期：ResourceResolver 查找时发现 `<cwd>/skills/` + `<cwd>/src/dqg/` 共存，打印 deprecation warning 继续跑。

## 实施切片（对应 writing-plans 三批）

### 第一批：物理边界

- `VERSION` 文件
- `pyproject.toml` dynamic version + project.urls + wheel force-include
- `ResourceResolver` 统一收口，迁移所有 `Path(__file__).parents[N]` 调用
- `install.sh`（含 `--dev` / `--dry-run` / `--skip-pip`）
- 老路径 deprecation warning

### 第二批：用户工作区

- `dqg-run init`（建 `.dqg/output/` + settings.yaml + 注入 CLAUDE.md + 追 .gitignore）
- `dqg-run path <skills|references|profiles>` 只读入口
- settings.yaml 加载与 code_repos 字段接入
- 版本一致性 warning

### 第三批：doctor

- last-run marker 记录
- bundle 生成 + 脱敏
- glab 集成 + fallback 手动
- `--no-upload` / `--redact` / `--title` 参数
- CLAUDE.md guardrail 文案终稿

## Definition of Done

物理边界验收:

- [ ] 新用户执行 `git clone && ./install.sh && cd <别的项目> && dqg-run init` 后,`<别的项目>/` 下 `ls` 看不到 DQG 源码
- [ ] `dqg-run init` 幂等：重跑不重复写 CLAUDE.md marker 节段，不重建已有 `.dqg/`
- [ ] `dqg-run --version` 返回 VERSION 文件内容
- [ ] `pyproject.toml` 的 `version` 为 dynamic，build wheel 时读 VERSION
- [ ] `dqg-run doctor` 无 glab 时打印 bundle 路径 + issue URL，退出 0
- [ ] `dqg-run doctor` 有 glab 时创建 issue 并打印 URL
- [ ] 老路径（cwd 含 `src/dqg/`）触发 deprecation warning 但仍可跑通至少 Q01
- [ ] `./install.sh --dev` 在 repo 根跑后，改 `skills/` 文件立即在 `~/.dqg/skills/` 可见（symlink）
- [ ] `./install.sh --dry-run` 输出符合第 2 节样本格式
- [ ] 单元测试覆盖 ResourceResolver 三层查找、version 一致性检查、install.sh 核心函数

## Out of Scope

- 发布 PyPI（留给 L1 正版路径）
- `dqg-run deinit` / `--uninstall`
- 迁移脚本（人工指引为主）
- bundle 自动上传到飞书或其他平台
- profile 模板拷贝到 `.dqg/profiles/`
- `.dqg/cache/` / `.dqg/knowledge/`
- 自动安装 glab CLI
- 上传失败自动重试

## 参考

- ROADMAP §F 规模化分发边界
- docs/distribution-gap.md 诊断文档
- VAF 仓库 install.sh（`~/git_dev/vibe-agentic-flow/install.sh`）
