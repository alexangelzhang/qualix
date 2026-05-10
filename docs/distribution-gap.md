# DQG 分发边界 Gap 诊断

> 2026-05-10 创建。触发自 DQG 第一个外部用户接入时观察到的行为模式。

## 触发症状

外部用户用 Claude Code 跑 DQG 时，遇到工具错误后 **Claude 直接修改 `src/dqg/` 源码**——而不是报 bug 给 DQG 维护者。

症状的二次危害：
1. **用户心智错了**：用户以为"在用工具"，实际"在二次开发工具"。下次 DQG 升级（`git pull`），自己的 patch 全被冲掉
2. **Claude 工作错了**：把 `src/dqg/` 当用户代码加进 context 消耗 token；可能基于过期源码给误建议
3. **维护者工作错了**：用户报的 bug 混着"他自己改出来的 bug" + "DQG 真 bug"，无法分流

## 根因诊断

**DQG 当前只能 `git clone` + 在仓库里运行**：

| 证据 | 位置 |
|------|------|
| `pyproject.toml` 是 `version = "0.1.0"`，从未发过 PyPI | `pyproject.toml` |
| ROADMAP `仍待推进（P1）` 里有 "PyPI 发布" 一条（已提升至 P0） | ROADMAP §3.C |
| `dqg-run` CLI 默认从 cwd 读 `skills/` `references/` `profiles/` `regression/` `output/` | `src/dqg/core/runner.py` |
| `SKILL.md` / `references/` / `profiles/` 和 `src/dqg/` 源码**同仓库** | 仓库根 |
| 用户自带的 CLAUDE.md 是 DQG 维护者视角（"怎么开发 DQG"），不是用户视角（"怎么用 DQG"） | `CLAUDE.md` |

**Claude 看到这个布局时的推理**：
- cwd 是一个 git repo
- 有 CLI 入口
- CLI 报错
- 附近有 `src/dqg/` 源码
- `CLAUDE.md` 讲"怎么改 DQG"
- → **修 bug 是合理的下一步**

这是用户/Claude 的合理推理，不是 bug。问题在于**当前架构默认让工具和用户项目在同一个 repo 里**。

## 为什么这是 P0，不是 P1

规模化接入的前置条件必须是分发边界。在没有边界时，以下 P1 工作**都在放大问题**：

| P1 工作 | 放大后果 |
|--------|---------|
| CI/PR 门禁模板化 | 每个团队接入 = 一份团队 fork 的 DQG，最终 N 个分叉 |
| 飞书 Bot 通知 | Bot 报错指向哪个 DQG 版本？用户自己改过的那个 |
| 团队聚合看板 | 看板聚合跨项目的 Phase 通过率，但项目 A 改过 schema，项目 B 没改，口径不统一 |
| 失败样例库扩容 | 用户自改的 DQG 产生的 failure 回流到主库污染 |

**每新增一个接入方都会产生新的"Claude 改 DQG 代码"事件**。必须先堵住。

## 修复路径（三层）

层层独立，但建议同一 session 一起做。

### L1 — PyPI 发布（最硬的边界）

```bash
pip install dev-quality-gate
```

之后用户目录下 `ls` **看不到 DQG 源码**。Claude 读不到源码 → 默认行为从"修 bug"变成"汇报 bug"。

实施要点：
- `pyproject.toml` 声明 `[tool.hatch.build.targets.wheel.force-include]` 把 `skills/` `references/` 打进 wheel 资源
- 所有路径推导从 `Path(__file__).parents[N]` 改为 `importlib.resources.files("dqg")`
- `dqg-run path skills` 等 CLI 帮用户查资源位置（只读，不鼓励进入）
- 版本号从 `0.1.0` 升到 `0.2.0`（破坏性布局变更）

### L2 — `dqg-run init` 分离用户工作区

```bash
cd my-project
dqg-run init
# 生成 .dqg/
#   profiles/           # 用户自定义 profile
#   skill-overrides/    # 用户覆盖的 skill 片段
#   output/             # DQG 运行输出
#   settings.yaml       # 用户偏好
```

用户的所有定制走 `.dqg/`，和 pip 装的工具本体隔离。DQG 升级时工具本体被 pip 覆盖，`.dqg/` 原样保留。

### L3 — CLAUDE.md guardrail 样板（软防御）

`dqg-run init` 在用户项目 `CLAUDE.md` 末尾追加：

```markdown
## DQG 使用规约

DQG 是通过 `pip install dev-quality-gate` 安装的工具，**不要修改它的源码**。

遇到 DQG 报错时：
1. 跑 `dqg-run doctor` 生成 issue bundle
2. 把 bundle 提交给 DQG 维护者，**而不是自己 patch**
3. 需要定制行为 → 改 `.dqg/` 里的 profile 或 skill override

相关资源：
- `dqg-run path skills`  — 只读查看内置 skill
- `dqg-run --help`       — CLI 完整参数
```

这层是软防御，真正起作用的是 L1 + L2 造成的物理隔离。

## 验收标准

完成后应该满足：

- [ ] 用户 cwd 里 `ls` 看不到 DQG 源码（只有 `.dqg/` 和用户项目文件）
- [ ] Claude 在用户项目里跑 DQG 时，默认不读 `site-packages/dqg/*.py`
- [ ] `dqg-run doctor` 产出可上报的 issue bundle：错误 stack + 输入摘要（脱敏）+ `dqg --version` + 相关 `_internal/` 产物
- [ ] CLI 每个错误信息末尾带"请报告 issue: https://.../issues/new" 明示分工
- [ ] 新用户接入时，典型 Claude Agent 行为是"读 `.dqg/settings.yaml` + 跑 `dqg-run`"，而非"读 `src/dqg/` + 改源码"

## 风险与取舍

**不推荐的做法**：

- ~~只往 DQG 仓库的 CLAUDE.md 加"不要改源码"~~ — 在用户 cwd 里跑时，DQG repo 的 CLAUDE.md 优先级最高，它的内容是"怎么开发 DQG"，反而明确告诉 Claude 怎么改
- ~~只做 L3 不做 L1 L2~~ — 软防御对 Claude 没有约束力；只有**物理读不到源码**才是硬边界

**真实权衡**：

- **破坏性升级** — 从 `0.1.0` 升到 `0.2.0` 是重大布局变更，老用户需要迁移（写迁移脚本 + 文档）
- **开发流 vs 使用流分化** — DQG 开发者还是 `git clone + pip install -e .`，但最终用户只能 `pip install`。这两路在 `pyproject.toml` 里需要明确分开（开发依赖 extras + editable 安装说明）
- **资源加载复杂化** — 从文件路径变成 `importlib.resources`，所有"读 skill 文件"的地方都要改；测试 fixture 需要同步调整

## 工作量与依赖

预估：**3-5 工作日**（不含真实发 PyPI 后的用户迁移支持）

- `pyproject.toml` 资源声明 + `importlib.resources` 改造：1-1.5 天
- `dqg-run init` 命令 + `.dqg/` 目录约定 + 用户工作区解析：1 天
- 路径推导全面审计（当前散在 `context_loader.py` / `skill_loader.py` / `phase_registry.py` / `handlers_*.py` 多处）：0.5-1 天
- 发 PyPI + 迁移文档 + 升级指南：0.5 天
- `dqg-run doctor` 扩展为 issue bundle 生成器：0.5-1 天

建议单独 session 执行，不和其他 feature 混。

## 与 ROADMAP 的关系

本文档对应 ROADMAP §3.F。在本文档落地前，以下 ROADMAP 条目都应该**缓一缓不要做**：

- CI/PR 门禁模板化（§3.D）—— 有了分发边界后模板才有固定目标
- 团队聚合看板 —— 跨项目聚合前得先保证每个项目的工具版本一致
- 飞书 Bot 通知 —— Bot 报错指向的 DQG 版本需要是 pinned 版本

反过来可以继续做：

- Anti-Rat Guard 精度评估 P1（纯数据分析，不涉及分发）
- Skill Evolution ReplayExecutor（内部基础设施）
- Bug Case compress（内部基础设施）

---

*最后更新：2026-05-10*
