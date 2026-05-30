---
name: "trace-reflect"
description: "从 session 执行轨迹蒸馏 skill 改进，结合 ASI 诊断、成功模式和 Reflective Mutation。用于 /trace-reflect、轨迹反思、深度反思。"
---

# Trace-Reflect — 从执行轨迹蒸馏 Skill 改进

综合 Trace2Skill (arXiv:2603.25158)、Skill-Insight (openEuler) 和 GEPA (arXiv:2507.19457) 的方法，从当前 session 的完整执行轨迹中提取可复用的经验，生成 skill 改进建议。

与 `/reflect` 的区别：
- `/reflect` 关注用户纠正和偏好（"不要这样做"→ 记住）
- `/trace-reflect` 关注执行效果（"这样做成功了/失败了"→ 为什么 → 怎么改进 skill）

## 数据源

### 1. 对话轨迹（主要）
回顾当前 session 的所有操作。

### 2. ASI 诊断数据（辅助）
LoopDetector hook 自动捕获的 Actionable Side Information，存储在 `/tmp/claude-loop-state-*.json` 的 `asi` 字段中。包含：
- 每次工具调用的成功/失败状态
- 错误类型分类（not_found / permission / timeout / exception）
- 错误片段（前 200 字符）
- effect 工具的操作目标（文件路径、命令预览）

读取方式：
```bash
python3 -c "
import json, glob
for f in glob.glob('/tmp/claude-loop-state-*.json'):
    data = json.load(open(f))
    asi = data.get('asi', [])
    if asi:
        print(f'=== {f}: {len(asi)} ASI entries ===')
        for e in asi[-20:]:
            status = e.get('status', '?')
            tool = e.get('tool', '?')
            err = e.get('error_type', '')
            target = e.get('target', e.get('command_preview', ''))
            print(f'  {status:7s} {tool:10s} {err:12s} {target[:60]}')
"
```

如果 ASI 数据存在，优先用它来辅助失败分析——它提供了对话上下文中可能被压缩掉的错误细节。

## 执行步骤

### 1. 轨迹分类 + 分级打分

回顾当前 session 的所有操作，将执行轨迹分为三个等级（Hermes Agent 的分级打分模式）：

**1.0 — 完全成功 (T+)**：达成目标，无弯路
- 标志：用户确认完成、测试通过、文件成功创建、无报错无重试

**0.5 — 部分完成 (T±)**：有产出但走了弯路或有瑕疵
- 标志：最终完成但中间有报错重试、方案被否定后换了方向、产出物需要手动修正

**0.0 — 失败 (T-)**：未达成目标
- 标志：任务放弃、用户明确否定、反复失败无法推进

同时读取 ASI 数据中的 `session_completion` 字段作为辅助判断：
```bash
python3 -c "
import json, glob
for f in glob.glob('/tmp/claude-loop-state-*.json'):
    data = json.load(open(f))
    sc = data.get('session_completion', {})
    print(f'Score: {sc.get(\"score\", \"?\")} | Reason: {sc.get(\"reason\", \"?\")}')
"
```

### 2. 成功轨迹分析（Success Analyst）

对每条成功轨迹，单次提取：

```markdown
## 成功模式: {模式名}

**场景**: {什么任务/什么条件下}
**操作序列**: {关键步骤，不超过 5 步}
**为什么有效**: {一句话原因}
**可泛化程度**: 高/中/低
**关联 skill**: {如果有对应 skill，写 skill 名}
```

重点提取：
- 工具选择决策（为什么用 A 而不是 B）
- 操作顺序（先做什么后做什么很重要的情况）
- 参数选择（特定配置/flag 的使用）

### 3. 失败轨迹分析（Error Analyst）

对每条失败轨迹，执行多轮诊断：

**第一轮：现象描述**
- 什么操作失败了？
- 错误信息是什么？
- 在哪个步骤开始偏离？

**第二轮：根因定位 + 归因分类**

先定位根因类别：
- 是工具选择错误？（用了不合适的工具）
- 是参数错误？（路径/配置/flag 不对）
- 是顺序错误？（依赖没满足就执行）
- 是 skill 指令不清晰？（skill 没说清楚边界条件）
- 是信息不足？（需要先读取某些文件但没读）

然后做偏差归因（基于 Skill-Insight 的归因框架）：

| 归因类别 | 判断标准 | 改进方向 |
|---------|---------|---------|
| **模型能力不足** | skill 指令清晰但 LLM 执行错误（如计算错误、格式不对、遗漏步骤） | 在 skill 中加更详细的 step-by-step 或 example |
| **Skill 定义缺陷** | skill 指令本身有歧义、遗漏边界条件、或假设了不存在的前提 | 修改 skill body |
| **环境/上下文问题** | skill 和模型都没问题，但运行环境不满足（依赖缺失、权限不足、文件不存在） | 在 skill 中加前置检查步骤 |
| **用户意图偏差** | 用户的实际需求和 skill 的设计目标不匹配 | 改进 skill 的 description/trigger 或创建新 skill |

**第三轮：修复建议**

```markdown
## 失败诊断: {问题名}

**根因**: {一句话根因}
**归因**: {模型能力不足 / Skill 定义缺陷 / 环境问题 / 意图偏差}
**影响的 skill**: {skill 名，如果有}
**建议修改**:
- [ ] {具体修改 1}
- [ ] {具体修改 2}
**修改原则**: 定点修补，只改出问题的部分，不要全量重写（防止幻觉误伤正常代码）
**预防措施**: {怎么避免下次再犯}
```

### 4. Reflective Mutation — 生成具体修改 Diff

**核心约束 — 单一资产原则（来自 darwin-skill）：**
每次只改一个 SKILL.md。如果多个 skill 需要改进，按优先级排序，逐个处理。每个 skill 走完完整的 改 → 独立评 → keep/revert 循环后，再处理下一个。原因：变量可控，改进可归因，回滚干净。

对当前优先级最高的 skill，生成具体的修改 diff（GEPA 的 Reflective Mutation 模式）：

```markdown
### Reflective Mutation: {skill-name}

**诊断摘要**: {基于 ASI 数据和轨迹分析的一句话诊断}

**修改 Diff**:
\`\`\`diff
--- a/{skill-name}/SKILL.md
+++ b/{skill-name}/SKILL.md
@@ -行号 @@
- {原始内容}
+ {修改后内容}
\`\`\`

**修改理由**: {为什么这样改，引用具体的失败轨迹或 ASI 数据}
**预期效果**: {改了之后应该能解决什么问题}
**风险评估**: {这个修改可能引入什么副作用}
```

修改原则（定点修补）：
- 只改出问题的部分，不全量重写
- 每个 diff 只针对一个问题
- 如果需要改多处，生成多个独立的 diff

### 4.5. 独立评分（来自 darwin-skill）

**改和评必须分离。** 生成 diff 的 agent 不能评估自己的 diff。

流程：
1. 主 agent 生成 diff 并应用修改（git commit）
2. 启动一个**独立子 agent**（通过 Agent tool），给它以下输入：
   - 修改前的 SKILL.md 原文
   - 修改后的 SKILL.md 全文
   - 本次修改要解决的问题描述
   - 不给它看主 agent 的诊断过程和修改理由（防止锚定）
3. 子 agent 独立评估，输出：

```markdown
### Independent Review: {skill-name}

**结构评分** (1-5):
- 职责明确性: {分} — {理由}
- 指令适配性: {分} — {理由}
- 内容一致性: {分} — {理由}

**变更评估**:
- 修改是否解决了声称的问题: Yes/No/Partial — {理由}
- 是否引入新问题: Yes/No — {具体}
- 总体判断: KEEP / REVERT

**置信度**: High / Medium / Low
```

4. 决策规则：
   - 子 agent 判断 KEEP + 置信度 High/Medium → 保留修改
   - 子 agent 判断 REVERT 或置信度 Low → git revert，记录原因
   - 用户始终有最终决定权，子 agent 结果展示给用户确认

**为什么这样做：** 自己改自己评会产生确认偏差（confirmation bias）——生成 diff 的 agent 倾向于认为自己的修改是好的。独立评分消除这个偏差。

### 5. 归纳合并 + 逐个优化循环

将多条成功/失败分析归纳为 skill 级别的改进建议，然后按优先级逐个处理：

```markdown
# Trace-Reflect 报告

## Session 概况
- 成功轨迹: {N} 条
- 失败轨迹: {M} 条
- 涉及 skill: {skill 列表}

## Skill 改进队列（按优先级排序）

### 1. {skill-name} — 优先级最高
**来源**: {N} 条成功 + {M} 条失败轨迹
**问题**: {一句话}
**状态**: 待处理

### 2. {skill-name}
...
```

**逐个处理流程（单一资产原则）：**
1. 从队列取优先级最高的 skill
2. 执行 Step 4（Reflective Mutation）生成 diff 并 commit
3. 执行 Step 4.5（独立评分）由子 agent 评估
4. KEEP → 标记完成，展示 diff + 评分给用户确认
5. REVERT → git revert，记录原因
6. 用户确认后，处理队列中下一个 skill
7. 每个 skill 之间暂停，不要连续自动处理

### 新 Skill 候选
**名称**: {建议名}
**理由**: {为什么现有 skill 覆盖不了}
**核心内容**: {skill 应该包含什么}

### Pareto 版本建议
如果修改可能影响 skill 在其他场景下的表现，建议保留多版本：
- **当前版本**：在 {场景A} 下表现更好
- **修改版本**：在 {场景B} 下表现更好
- **建议**：保留两个版本，通过 trigger 条件区分使用场景
```

### 6. 持久化

- 报告写入 `/tmp/trace-reflect-{date}.md`
- 如果有高置信度的 skill 改进建议，询问用户是否立即应用
- 如果发现新 skill 候选，询问用户是否创建

## 约束

- 只分析当前 session 的轨迹，不跨 session
- 失败分析必须经过至少两轮诊断，不要一轮就下结论
- 成功模式的"可泛化程度"要诚实评估——只在当前任务有效的标"低"
- 不要生成空洞的建议（"应该更仔细"），每条建议必须具体到可执行
- 改进建议不超过 5 条，聚焦最有价值的
- 不自动修改任何 skill 文件，所有修改需用户确认
