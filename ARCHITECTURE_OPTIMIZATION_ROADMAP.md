# 架构级优化路线图

> 面向大量文档、知识库、代码仓库和图片输入场景的架构级优化总表。
> 重点目标：减少重复 I/O、降低 prompt token 浪费、提升证据相关性和执行稳定性。

## 1. 优化目标

1. 把高频读文档/读图片/读代码仓库的成本前移到可复用的检索与缓存层。
2. 把 LLM 调用从“反复生成同类结果”改成“应用层可复用结果 + 可追踪失效”。
3. 把上下文构造从“全文拼接”改成“retrieval-first evidence pack”，优先给证据，再给摘要。
4. 保持现有 Phase 流程不大改，只做可渐进落地的局部优化。

## 2. 优先级总表

| 优先级 | 方向 | 目标 | 收益 | 影响模块 | 风险 | 分阶段推进建议 |
|---|---|---|---|---|---|---|
| P0 | 应用层 LLM result cache | 对相同输入、相同模型、相同上下文版本的结果做读写缓存 | 降低重复 LLM 调用、缩短响应时间、直接省 token 成本 | `agents/`、`quality/`、`commands/`、`reporting/` | 缓存失效不准、命中键设计过宽/过窄、结果可追溯性不足 | 先只缓存纯函数式输出，再逐步扩到评审/总结类结果；命中键必须包含模型、版本、phase、关键上下文摘要 |
| P0 | retrieval-first evidence pack | 先构建证据包，再拼 prompt；优先摘要、摘录、引用，不直接塞全文 | 大幅降低上下文 token、减少证据遗漏、提升评审可解释性 | `context/`、`services/`、`quality/`、`memory/`、`wiki_layer` | 检索召回不足、证据包截断过度、早期实现调试成本高 | 先覆盖 Phase A/A.5/A.6/C 的证据包，再扩到 `agent-run` / `adaptive` / `wiki`；每个 pack 保持固定 schema |
| 高 | 文档/图片/代码的分层检索与摘要复用 | 让同类输入先走缓存和摘要，而不是每次全文扫描 | 降低 I/O、减少 prompt 拼装时间、提升多模态场景稳定性 | `ingest/`、`cache/`、`context/`、`media/`、`memory/` | 索引新鲜度不足、摘要过短导致语义损失 | 先做文档与图片，再做代码仓库；按 source type 分层设预算和 fallback |
| 中 | 证据与结果的可观测性闭环 | 给缓存命中率、证据包大小、上下文 token、LLM 调用次数做统一指标 | 方便定位 token 浪费点，也方便判断优化是否真的生效 | `reporting/`、`store/`、`commands/` | 指标口径不统一、统计本身增加少量开销 | 先记录关键指标，不强制告警；稳定后再补阈值与周报 |
| 低 | Prompt 细节和文档治理 | 统一提示词风格、报告模板、引用格式，减少边角 token 浪费 | 降低噪音、提升可读性、减少重复说明 | `skills/`、`quality/`、`docs/` | 收益较分散，容易做成零碎修补 | 作为 P0/P1 完成后的收尾项，按模块逐步清理 |

## 2.1 当前落地状态

| 项目 | 状态 | 本轮落地说明 |
|---|---|---|
| P0-1 应用层 LLM result cache | 已完成（主执行路径） | `agent-run` / `adaptive` 已统一复用 `Agent.query_cache`，重复 Worker/Judge/Fixer/Critique 调用可直接命中；后续只需扩展到更多 summary 类结果 |
| P0-2 retrieval-first evidence pack | 已完成 | `_upstream_context.md` 已切到固定 evidence pack schema（Pack 概览 + 证据摘要 + 关键引用），并统一 Phase A 当前输入证据与 bug case 去重策略 |
| P1-1 多 Judge 并行投票 | 已完成 | `adaptive` 投票并行化、judge model 去重、单 Judge 失败容错、结果顺序稳定 |
| P1-2 版本感知 cache namespace | 已完成 | `semantic_cache` + `MemoryLayer.search()` 按版本隔离，支持定向失效 |
| P1-3 增量索引 / 变更感知知识层 | 已完成 | `MemoryLayer.index_phase()` 按关键输入签名跳过未变化重建，`finalize` 已统一接入 |
| P1-4 FTS5 中文检索质量 | 已完成 | 边界感知中文分词 + identifier subtoken + 统一 MATCH builder + post-filter 已覆盖 fact/text/image/code |
| P1-5 Phase C 弱断言 sidecar | 已完成 | `execute C` 自动产出 `_internal/_weak_assert_context.{json,md}`，供技能优先读取 `WRONG_TARGET` 候选 |

## 3. 两项 P0 的落地边界

### 3.1 应用层 LLM result cache

- 缓存对象：应用层输出结果、评审结果、可复用总结类结果。
- 关键键值：模型名、prompt 版本、phase、输入摘要、上下文版本、角色。
- 失效原则：只要输入证据变更，就强制失效。
- 先行收益：减少重复调用，尤其适合 finalize / review / lint 这类重复触发场景。

### 3.2 retrieval-first evidence pack

- 证据优先级：结构化事实 > 相关摘录 > 摘要 > 全文。
- pack 目标：把“能验证的证据”先送给 LLM，再给必要的背景信息。
- 先行范围：Phase A、A.5、A.6、C，以及与 wiki / knowledge base 相关的检索入口。
- 失败兜底：召回不足时允许回退到更宽松的摘要层，但不直接回全文。

## 4. 分阶段推进建议

### 阶段 0：立即实施

- 先落 P0 两项，且只覆盖最频繁的应用路径。
- 每次落地都配命中率、token 变化、调用次数变化三类指标。
- 不先追求全量，只追求可验证收益。

### 阶段 1：扩面

- 把证据包从 Phase A 扩到 A.5/A.6/C，再覆盖 `agent-run` / `adaptive`。
- 把 result cache 从单点输出扩到 review chain、lint、summary 这类重复调用。
- 同步补充失效逻辑和回归测试。

### 阶段 2：治理

- 统一采集 token、I/O、缓存命中、检索召回率。
- 以周维度观察收益，避免局部优化把系统复杂度拉高。
- 对低收益但高维护成本的优化项做收敛或撤回。

### 阶段 3：收尾

- 清理重复 prompt、冗余入口和低价值全文读取。
- 把稳定规则沉淀到文档和默认模板中。
- 让优化成果默认生效，而不是靠人工记忆。

## 5. 备注

- 这份路线图和现有 `ROADMAP.md` 配套使用，属于更偏“架构落地顺序”的执行版。
- 后续如果新增高频读源，可以继续按同样的表结构补充。
