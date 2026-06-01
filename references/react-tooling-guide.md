# ReAct Tooling Guide — Q01 Evidence Gathering Loop

> 本文档规定 Q01 Step 2.5 ReAct 工具调用阶段的使用规则。  
> 适用场景：在 PRD 通读（Step 2）之后、需求结构化（Step 3）之前执行有界工具调用。

---

## 1. Purpose

Q01 的单次 LLM 分析对跨文档引用、未完整的状态机和模糊异常路径存在天然盲区：

- **跨文档引用**：PRD 常出现"详见接口规范文档"或"参考流程说明"，但引用内容不在当前 PRD 里。
- **状态机缺口**：状态节点来源于图片，但触发条件、边的标签可能散落在附录文档。
- **异常路径模糊**：PRD 描述了操作，但没有提供具体错误码或响应格式。

插入 ReAct 循环的目标是在结构化前主动消解这些盲区，避免最终产物中出现"推断性 SE"或大量低质量 OPEN。实验数据表明，即使只有 1-2 轮有效工具调用，SE 的覆盖率和具体化程度也会显著提升。

---

## 2. When to Use

满足以下**任一条件**时，进入 ReAct 阶段（Step 2.5）：

| 条件 | 示例触发词 |
|------|-----------|
| 发现跨文档引用 | "详见xx文档"、"参考接口规范"、"见附录"、"根据平台规范" |
| 状态机节点触发条件来源不明 | 图片里有状态节点，但 PRD 文本没有说明触发条件 |
| 异常路径缺少具体错误码/响应 | "系统报错"、"校验失败"等无具体码值的描述 |

**不满足上述条件**时，Step 2.5 是可选的——可直接跳过进入 Step 3。  
跳过时在 `_reasoning_log.md` 简短记录原因（如"Step 2 通读未发现跨文档引用，跳过 ReAct"）即可。

---

## 3. Tool Selection Guide

每轮 ReAct 调用前，按如下规则选择工具：

### `Read` — 已知文件路径时使用

**适用**：PRD 中直接提到了文件名或相对路径（如"详见 docs/api-spec.md"），evidence pack 里存在该文件。

```
Read("output/<id>/Q01/ingest/assets/api-spec.md")
```

- 精确读取引用内容，效率最高
- 如文件不存在，记录"无新发现"，不要猜路径反复重试

### `Grep` — 需要跨文件搜索关键词时使用

**适用**：PRD 提到了一个术语、状态名或错误码，但没有说明在哪个文档里。

```
Grep("APPROVAL_TIMEOUT", "output/<id>/Q01/ingest/")
```

- 用于在 evidence pack 目录下搜索关键词出现位置
- 关键词尽量精确（枚举值、错误码、接口名），避免用通用词导致结果噪音

### `AskUserQuestion` — 阻塞性歧义，整个 ReAct 阶段最多一次

**适用**：遇到最高优先级的 OPEN 项，工具调用无法自行解决，且该歧义会直接影响多个 SE 的生成。

典型场景：
- "500 阈值是否包含边界？"（影响 SE 的精确断言值）
- "拒绝后能否重新申请？"（影响状态机分支数量）

**限制**：
- 整个 ReAct 阶段只能使用一次
- 不得用于非阻塞性问题（如"这个字段好不好看"）
- 在提问前，先确认工具调用确实无法找到答案

---

## 4. Stopping Rules

满足**任一退出条件**时，立即退出 ReAct 阶段，进入 Step 3：

| 退出条件 | 说明 |
|---------|------|
| 连续 2 轮均未发现新的 SE 候选 | 证据收益递减，继续调用意义不大 |
| 已执行 5 轮工具调用 | 硬性上限，防止过度消耗 context |
| 所有已知跨文档引用已解析 | 主动触发的引用全部处理完毕 |

**不要等到所有疑问都解决才退出**——残余的模糊项应进入 OPEN，由人工审核阶段处理。

---

## 5. Evidence Format

每轮工具调用结束后，将结果追加到 `_reasoning_log.md` 的 `## ReAct Evidence` 块。  
`## ReAct Evidence` 块应紧跟在 Step 2 的记录之后。

**格式**：

```markdown
## ReAct Evidence

### Round 1
- Tool: Read
- Query: output/<id>/Q01/ingest/assets/api-spec.md（PRD 第 34 行引用的接口规范）
- Finding: 找到错误码定义：APPROVAL_TIMEOUT=408，DUPLICATE_REQUEST=409
- New SE candidates: SE 并发幂等（DUPLICATE_REQUEST=409）、SE 超时降级（APPROVAL_TIMEOUT=408）

### Round 2
- Tool: Grep
- Query: "状态流转" in output/<id>/Q01/ingest/
- Finding: 无新发现（关键词仅出现在已读 PRD 文本中）
- New SE candidates: 无
```

**字段说明**：
- `Tool`：实际使用的工具名（Read/Grep/AskUserQuestion）
- `Query`：具体的查询参数或问题，足够详细以便审计
- `Finding`：本轮发现了什么；找到具体内容时摘录关键数值/状态/码；无发现时直接写"无新发现"
- `New SE candidates`：本轮新发现的 SE 候选，使用 SE ID 格式（SE-001 等）；无候选写"无"

---

## 6. Anti-Patterns

以下行为会降低 ReAct 的有效性，必须避免：

| 反模式 | 后果 | 正确做法 |
|--------|------|---------|
| 对同一文档重复读取 | 浪费轮次，触发连续无新发现退出 | 第一轮读取后，直接引用已读内容，不再重复 |
| 用 AskUserQuestion 问非阻塞问题 | 消耗唯一提问机会，后续遇到真正阻塞项无法再问 | 只有工具调用无法解决的 P0 歧义才用 AskUserQuestion |
| 超过 5 轮强制退出后继续调用 | 破坏硬性上限约定，context 膨胀影响 Step 3 质量 | 5 轮到达后无论是否解决全部引用，立即退出进入 Step 3 |
| 遗漏 `## ReAct Evidence` 记录 | finalize_checks 可能无法识别 ReAct 证据，跳过 bonus 注解 | 每轮结束后立即追加记录，不要等所有轮次结束后批量补写 |
| 把 ReAct 阶段用于验证已知内容 | SE 候选必须来自新发现，不是复述 PRD | 只对 Step 2 通读中未解决的引用发起工具调用 |

---

## 7. Integration with finalize_checks

当 `_reasoning_log.md` 包含 `## ReAct Evidence` 块且至少有一个有效 Round 时，`finalize_checks.py` 会在 Q01 的 source annotation completeness 检查中附加说明：

```
INFO: ReAct Evidence 已记录（N 轮），source annotation 质量检查包含额外证据来源。
```

此注解**不改变 BLOCKED/WARNING 阈值**，仅作为产物质量的透明度说明。

---

*本文档对应 SKILL.md Step 2.5，参见 `skills/requirement-structuring/SKILL.md`。*
