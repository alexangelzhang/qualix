# DQG vs VAF 操作体验对比分析

*2026-04-16 | 基于 VAF v2.3.1 使用说明文档 + DQG 当前实现*

## 定位差异

| 维度 | DQG | VAF |
|------|-----|-----|
| 核心定位 | 质量门禁（审计+防漏） | 全流程自动化（需求→代码→测试） |
| 覆盖范围 | 需求结构化 → 单测 → 代码评审 | 需求采集 → 技术设计 → 编码 → 单测 → 集成 → E2E |
| 产出物 | 审计报告 + 结构化 JSON | 实际代码 + 测试 + 文档 |
| 用户角色 | 单人（QA/架构师视角） | 多人协作（DPM + 多开发者） |

## 上手体验（差距最大的地方）

| 维度 | VAF | DQG | 差距 |
|------|-----|-----|------|
| 初始化 | `vaf init hub --feature xxx` 一行搞定 | 需要理解 project_id、output 目录、profiles、state.json 的关系 | VAF 大幅领先 |
| 环境配置 | `vaf config init` + `vaf config check` + `vaf deps upgrade` | 无统一配置命令，依赖散落在 scripts/ 下 | VAF 大幅领先 |
| 快速上手 | 5 分钟视频教程 + 分角色阅读指引 | 无快速上手指南，需要读 CLAUDE.md + AGENTS.md + dqg_starter.md | VAF 大幅领先 |
| 版本升级 | `vaf update` + `vaf init xxx-workspace` | 无升级机制，手动 git pull | VAF 领先 |
| 版本管理 | `.vibe/version.json` 自动检测版本差异 | 无版本概念 | VAF 领先 |

## 日常操作体验

| 维度 | VAF | DQG | 分析 |
|------|-----|-----|------|
| 入口统一性 | `@vaf_starter.md 执行`，Hub/Service 自动检测 | `@dqg-starter` 或 `dqg-run startup`，需要手动指定 project_id | VAF 略优 |
| 菜单交互 | `v` 详情模式 / `g` 全局进度 / 数字选择 | 数字选择 + 已完成 Phase 详情页 | VAF 略优（多了全局视图） |
| 阶段命名 | P01 需求采集、S03 代码实现（直觉） | Phase A、Phase A.5（需要记忆映射） | VAF 更友好 |
| 放行机制 | 输入 `y` 放行 → 自动 git commit + push + 解锁下一阶段 | approve → 手动刷新菜单，不自动 git | VAF 更流畅 |
| 阶段依赖 | 线性链 P01→P02→...→S01→...→T01，简单清晰 | DAG 结构（A→A.3→A.6→A.5，B/C 并行），灵活但复杂 | 各有优劣 |
| 多服务协作 | 原生支持（Hub 协调 + P06-A/B/C 门禁） | 不支持 | VAF 独有能力 |
| Git 集成 | 放行时自动 commit + push + rebase | 不自动操作 git | VAF 更省心 |

## 质量保障深度（DQG 的优势区）

| 维度 | DQG | VAF | 分析 |
|------|-----|-----|------|
| 需求防漏 | REQ/BR/SE/GAP/OPEN 五层结构 + 图片语义解析 + 状态机 Mermaid 转换 | P03 PRD 标准化 + 原子功能清单 | DQG 更深 |
| 质量审计 | 四层审计（有没有/全不全/好不好/准不准）+ 变异测试 + 弱断言检测 | S04 单元测试（生成为主） | DQG 远超 |
| 代码评审 | 调用链路级评审 + 资金安全五步法 + 12 类异常矩阵 | S06 代码审查（通用） | DQG 远超 |
| 反幻觉 | 每条结论标注来源+置信度 + Anti-Rationalization 表格 + 放水检测 | 无显式机制 | DQG 独有 |
| 推理可追溯 | `_reasoning_log.md` 强制交付 + Judge/Critique 双重审视 | 无 | DQG 独有 |
| 自动进化 | SkillReflector + SkillFactory + Eval Baseline 自动对比 | 无 | DQG 独有 |
| Phase Contract | 每次执行自动生成验证目标，Judge 按 contract 逐条打分 | 无 | DQG 独有 |

## 为什么 VAF 使用体验更佳——核心原因

1. **"做事"vs"审事"的体验差异**
   - VAF 每个阶段都有明确产出（PRD.md、tech_design.md、代码文件），用户能看到"东西在变多"
   - DQG 每个阶段产出的是审计报告，用户看到的是"问题在变多"，心理负担更重

2. **操作闭环的完整度**
   - VAF：选择阶段 → AI 执行 → 审查产物 → 输入 y → 自动 commit + 解锁下一步。一个循环 2 次交互
   - DQG：选择阶段 → 收集输入（逐步） → AI 执行 → 自检 → Judge/Critique → 修正 → finalize → approve → 刷新菜单。一个循环 5-8 次交互

3. **认知负荷**
   - VAF 阶段命名直觉（P01 需求采集），依赖链线性
   - DQG 阶段命名抽象（A.5 是覆盖度审计还是质量评审？），DAG 依赖需要记忆

4. **容错友好度**
   - VAF FAQ 覆盖了 38.5% 最高痛点（AI 产物不符合预期），给了具体的 prompt 调优技巧
   - DQG 的错误恢复是面向系统的（Stop-the-Line + Triage 五步法），不是面向用户的

5. **工具链完整度**
   - VAF 有完整 CLI（init/config/update/version/deps），用户不需要理解内部结构
   - DQG 的 `dqg-run` 只管状态，初始化/配置/升级都需要手动操作

## 可借鉴的改进方向

| VAF 优势 | DQG 可借鉴的做法 | 复杂度 |
|---------|----------------|--------|
| `vaf init` 一键初始化 | 增加 `dqg-run init <project_id> --profile java-ddd-tmf` | 中 |
| `vaf config check` | 增加 `dqg-run doctor` 检查环境/依赖/配置 | 低 |
| 放行自动 git commit | approve 后可选自动 commit 产物 | 低 |
| 阶段直觉命名 | 菜单中显示中文名而非 Phase ID（已有，但 skill 引用仍用 A/A.5） | 低 |
| 全局进度视图 | `dqg-run status` 输出全 Phase 进度 + 耗时 + 质量分 | 中 |
| 5 分钟快速上手 | 写一个 `docs/quickstart.md`，从 clone 到跑完 Phase A 的最短路径 | 低 |
| FAQ 痛点覆盖 | 收集实际使用中的高频问题，写入 FAQ | 低 |
| `v` 详情 / `g` 全局 | 菜单增加快捷键切换视图 | 中 |
