---
name: tech-coverage-audit
description: "Phase Q04: 审计技术方案对 Phase Q01 结构化需求的覆盖度，确保不漏不偏。用户提供技术方案文档，且已有 Phase Q01 产出，要求做覆盖度审计时触发。"
license: MIT
compatibility:
  claude: ">=3"
metadata:
  phase: Q04
  depends_on: [Q01]
  outputs: [phase_a5_structured.json, tech_design_coverage_review.md, _reasoning_log.md]
  forbidden_outputs: [UT, EUT]
allowed-tools:
  - Bash
  - Read
  - Write
  - Edit
  - Grep
  - AskUserQuestion
---

# Phase Q04: 技术方案覆盖度审计

承接 Phase Q01 产物，逐条比对技术方案覆盖度。禁止输出 UT/EUT。

## 核心原则

1. 逐条比对，不漏不猜。
2. 双向审计：需求→技术方案 + 技术方案→需求。
3. 区分前后端覆盖状态。
4. 未显式提及不得标 COVERED，可标 IMPLICIT 但须附推导依据。

## 覆盖状态枚举

| 状态 | 含义 |
|------|------|
| `COVERED` | 技术方案有明确对应设计 |
| `PARTIAL` | 部分覆盖，存在缺失维度 |
| `MISSING` | 无对应设计 |
| `IMPLICIT` | 未显式提及但可推导（须附依据） |

## 上下文加载原则（Token 优化）

1. 优先读取 `_upstream_context.md`，不要回读原始 PRD 文档或 `plain_text.txt`。
2. 图片语义已预解析到 `image_semantics.md`，直接引用文本结论，不要重新读取图片文件。
3. Phase Q01 结构化产物（`phase_a_structured.json` / `phase_a_report.md`）是唯一的需求基线，不要回溯飞书原文。

## 执行流程

**严格按顺序执行，不得跳步：**

```
Step 0: 输入准备与范围确认（如果是重跑，必须先读取旧版产物）
Step 0.5: [可选] 技术方案生成（当无现成技术方案时，基于 Phase Q01 产物 + 知识库自动生成）
Step 1: REQ 级覆盖扫描
Step 2: BR 级覆盖详查
Step 3: SE 覆盖审计
Step 4: GAP/OPEN 闭环检查
Step 5: 反向审计
Step 6: 自检（逐项对照 gate checklist，全部通过才能进入 Step 7）
Step 7: Judge/Critique（切换到批评者视角审视自己的输出）
Step 8: 修正（根据 Step 7 发现的问题修正报告，重新执行 Step 6）
→ 全部通过后才能 finalize
```

### Step 0: 输入准备与范围确认

1. 确认 Phase Q01 报告路径。
2. 收集技术方案文档清单（飞书直读优先）。
3. 无权限文档标记 `NEEDS_ACCESS` 列入风险项。
4. **技术方案输入质量检查**：
   - 检查是否有 HLD（整体架构+数据模型+状态机）
   - 检查是否有 LLD（核心接口实现逻辑，不只是签名）
   - 仅有 HLD 缺 LLD：可继续执行，但在报告开头标注"技术方案缺少详细设计，覆盖度判定可信度受限"
   - HLD 也不完整：阻断执行，提示用户补充
5. Scope Challenge：技术方案覆盖 PRD 哪个子集？是否有多份需拼合？是否显式排除了某些需求？
6. **如果是重跑**，必须先读取旧版产物（`tech_design_coverage_review.md`），新版必须是旧版的超集。
7. **已有实现扫描**（当提供代码仓库时）：扫描 master/main 分支的已有接口、表结构、TMF 链路，输出 `EXISTING_IMPL` 章节。

### Step 0.5: [可选] 技术方案生成

**触发条件**: 用户无现成技术方案文档，由用户显式触发（`--generate-design`）。

三阶段生成流程（Brainstorming → Writing Design → Multi-Agent 互审）详见 [references/design-generation.md](references/design-generation.md)。

### Step 1: REQ 级覆盖扫描

逐条检查 Phase Q01 的每个 REQ，标注覆盖状态和来源文档。

### Step 2: BR 级覆盖详查

按模块分组，逐条检查每个 BR 的前端/后端覆盖。

### Step 3: SE 覆盖审计

逐条检查每个 SE。对 MISSING/PARTIAL 项做 Failure Impact 分析：
`SE-xxx | MISSING | 最坏后果: <描述> | 影响范围: <用户/资金/数据>`

### Step 4: GAP/OPEN 闭环检查

- GAP：标记 `已闭环` / `部分闭环` / `未闭环`。
- OPEN：标记 `已闭环` / `未闭环`。
- 未闭环的高风险项（资金/安全/数据一致性）升级为 P0。

### Step 5: 反向审计

1. 技术方案新增设计（NEW_DESIGN）：Phase Q01 未识别的非功能需求，评估是否回补。
2. 技术方案显式排除（NOT_IN_SCOPE）：与 Step 0 交叉验证。
3. 新接口/新表/新流程无对应 REQ/BR：判断是技术细节还是遗漏。

### Step 6: 自检（提交前强制检查）

- [ ] 每条 REQ 已标注覆盖状态
- [ ] 每条 BR 已检查前端/后端覆盖状态
- [ ] 每条 SE 已检查覆盖状态，MISSING/PARTIAL 项有 Failure Impact 分析
- [ ] 每条 GAP/OPEN 已检查闭环状态
- [ ] 反向审计已完成（NEW_DESIGN / NOT_IN_SCOPE / 无对应 REQ 的新设计）
- [ ] 每个覆盖判定有技术方案原文证据引用
- [ ] 未输出 UT/EUT
- [ ] 如果是重跑：新版是旧版的超集（覆盖判定数量不减少，已有结论不丢失）

### Step 7: Judge/Critique（提交前自我评审）

1. **Judge 评审**：对照技术方案原文逐条验证每个覆盖判定的准确性。
2. **Critique 批评**：假设输出有遗漏和错误，重点检查前后端覆盖不一致、GAP/OPEN 闭环遗漏、反向审计盲区。
3. 将发现记录在报告末尾的"自我评审记录"章节。

### Step 8: 修正

根据 Step 7 发现的问题修正报告，修正完成后重新执行 Step 6 自检确认。

**全部通过后，才能执行 `dqg-run <project> finalize A.5`。**

## 输出模板

复用 `../../references/tech-design-coverage-template.md`。

报告必须包含以下标准章节（缺一不可）：

1. **PROFILE_CONTEXT** — 技术栈基线
2. **审计范围** — 需求基线（REQ/BR/SE/GAP/OPEN 数量）+ 技术方案来源
3. **REQ 覆盖度** — 表格（ID/描述/状态/映射证据/置信度）
4. **SE 覆盖度** — 表格（ID/描述/状态/映射证据/置信度）
5. **GAP 闭环** — 表格（ID/描述/状态/置信度）
6. **OPEN 闭环** — 表格（ID/描述/状态/置信度）
7. **反向审计** — NEW_DESIGN / NOT_IN_SCOPE 表格
8. **覆盖度统计** — 表格（维度/总数/COVERED/PARTIAL/MISSING/覆盖率）
9. **评审结论** — PASS / PASS_WITH_RISKS / FAIL
10. **自我评审记录** — Judge + Critique

## 通过标准

1. REQ 覆盖率 = 100%（允许 IMPLICIT 须附依据）
2. SE 覆盖率 >= 90%（MISSING 须有 GAP/OPEN 兜底）
3. P0 风险项已闭环或有明确排期
4. GAP 闭环率 >= 60%（高风险必须闭环）
5. OPEN 闭环率 >= 50%（资金/安全相关必须闭环）
6. Step 6 自检清单全部通过
7. Step 7 Judge/Critique 已执行且问题已修正
8. 每个覆盖判定有技术方案原文证据引用
9. 如果是重跑：新版是旧版超集

## Anti-Rationalization（禁止偷懒）

| 常见借口 | 为什么不能接受 | 正确做法 |
|---------|--------------|---------|
| "技术方案提到了这个接口名，算 COVERED" | 提到接口名不等于有完整设计，必须有异常处理 | COVERED 要求正向+异常都有设计，否则标 PARTIAL |
| "这个 REQ 太细了，技术方案不会写这么细" | 覆盖度审计就是要逐条对照，粒度不够是 MISSING | 逐条检查，缺失的标 MISSING |
| "反向审计没发现新增设计" | 技术方案中超出 PRD 的设计很常见，不可能为零 | 仔细检查每个接口/表/配置是否在 PRD 中有对应需求 |
| "GAP 已经在 A.6 处理过了" | A.5 审的是覆盖度不是质量，GAP 闭环状态要独立判断 | 检查 GAP 在技术方案中是否有对应设计 |
| "覆盖率数字达标就行" | 覆盖率可以虚高（PARTIAL 算半个），必须看具体判定 | 逐条检查 COVERED 的判定依据 |

## 验证标准（Verification）

| 验证项 | 检查方式 | 阻断级别 |
|--------|---------|---------|
| 推理日志存在 | finalize_checks: `_reasoning_log.md` 存在且 > 100 字符 | BLOCKED |
| 产物数量不回退 | finalize_checks: 对比 `_prev_counts.json` | REGRESSION |
| Schema 校验 | schemas/phase_a5.py 验证 `phase_a5_structured.json` | BLOCKED |
| 覆盖度矩阵已生成 | `_coverage_matrix.json` 存在 | 人工确认 |
| REQ 覆盖率 100% | phase_a5_structured.json 中 req_coverage 无 MISSING | 人工确认 |
| SE 覆盖率 >= 90% | phase_a5_structured.json 中 se_coverage COVERED+PARTIAL >= 90% | 人工确认 |

## 禁止事项

1. 禁止未显式提及时标 COVERED。
2. 禁止跳过 GAP/OPEN 闭环检查。
3. 禁止忽略前后端覆盖不一致。
4. 禁止存在 P0 未闭环时给"通过"结论。
5. 禁止跳过 Step 6 自检和 Step 7 Judge/Critique 直接 finalize。
6. 禁止重跑时从零重写，必须在旧版基线上增量修改，新版必须是旧版超集。
7. 禁止概括性描述覆盖状态，必须引用技术方案原文作为证据。
