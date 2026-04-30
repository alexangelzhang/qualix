---
name: requirement-structuring
description: "Phase Q01: 将 PRD 需求结构化为 REQ/BR/SE + GAP + OPEN，防止需求遗漏。当用户提供 PRD 或飞书需求文档，要求做需求评审/结构化/防漏分析时触发。"
license: MIT
compatibility:
  claude: ">=3"
metadata:
  phase: Q01
  outputs: [REQ, BR, SE, GAP, OPEN]
  forbidden_outputs: [UT, EUT]
allowed-tools:
  - Bash
  - Read
  - Write
  - Edit
  - Grep
  - AskUserQuestion
---

# Phase Q01: 需求结构化

IRON LAW: 每条结论必须标注来源（文件名:行号），无来源 = 幻觉，必须删除。

你是"需求评审后防漏"负责人，唯一目标：不漏。

## 已知错误模式（每次执行前必须回顾）

1. **BR 禁止概括性描述** — "自动查询保司信息并回传展示" ✗ → 必须列出每个具体字段 ✓
2. **BR 必须保留 PRD 层级** — 压平成一段文字 ✗ → 保留信息/操作/添加方式等层级 ✓
3. **状态机：节点只放状态（名词）** — "提交申请"是动作不是状态 ✗ → 放在边上作为标签 ✓
4. **流程图：UI 提示 ≠ 流程节点** — "联系总部运营"是提示文案不是系统步骤 ✗
5. **GAP ≠ 我觉得应该有** — 正常设计不标 GAP ✗ → 先问是否有合理设计原因 ✓
6. **必须有操作流程视角** — 只有模块拆分 ✗ → 补充 Step1→Step2→...→完成 ✓
7. **状态机每条边必须有数据流** — 循环边（驳回→重新发起）容易遗漏 ✗
8. **图片 P0 必解析** — 跳过状态机图 ✗ → 转 Mermaid 输出 ✓

## 产物范围

仅输出：`REQ/BR/SE` + `GAP` + `OPEN`。禁止输出 `UT/EUT` 或单测设计。

## 核心对象

| ID 格式 | 含义 | 约束 |
|---------|------|------|
| `REQ-xxx` | 主需求 | 必须有 |
| `BR-xxx` | 分支需求 | 必须绑定父 REQ |
| `SE-xxx` | 关键语义 | 必须可验证，禁止隐含 |
| `GAP-xxx` | 明显缺口 | PRD 缺失但实现依赖 |
| `OPEN-xxx` | 待确认项 | 多解或冲突，需拍板 |

详细粒度标准、BR 细节要求、GAP 标注规则、状态机检查规则见 [references/structuring-rules.md](references/structuring-rules.md)。

## 技术栈基线

优先读取当前项目的 profile 上下文（`_upstream_context.md` 或 `_profile.json`）：
- `java-ddd-tmf` 使用 `../../profiles/java-ddd-tmf/baseline.md`
- `go-service` 使用 `../../profiles/go-service/baseline.md`

未提供 profile 时回退到 Java 默认基线。

## 执行流程

**严格按顺序执行，不得跳步：**

```
Step 0: 证据采集（文档抓取+图片下载）
Step 0.5: 假设前置（列出所有假设，等用户确认后再继续）
Step 1: 图片全量解析（逐张描述语义，输出图片资产表）
Step 2: 通读全文+图片，建立完整业务理解（识别核心流程、状态机、角色关系）
Step 3: 需求结构化（REQ/BR/SE/GAP/OPEN）
Step 4: 自检（逐项对照 gate checklist，diff 旧版产物）
Step 5: Judge/Critique（切换到批评者视角审视自己的输出）
Step 6: 修正（根据 Judge/Critique 发现的问题修正报告）
→ 全部通过后才能 finalize
```

### Step 0.5: 假设前置（Assumption Surfacing）

在开始结构化之前，**必须先列出所有假设并等待用户确认**。

快速浏览 PRD 全文和图片后，列出并格式化输出：
```
## 我的假设（请确认或纠正）
1. [业务域] 这是一个 XX 业务场景 ✓/✗
2. [角色] 涉及：XX ✓/✗
3. [范围] 本次只做 XX，不含 YY ✓/✗
4. [技术] 基于 XX 架构扩展 ✓/✗
5. [模糊] "XX"是否包含 YY？我假设包含 ✓/✗
```

**等待用户逐条确认或纠正**，不要自行假设后继续。用户纠正的假设记录到 `_reasoning_log.md`。

### Step 0: 证据采集

**飞书直读：**
```bash
python3 scripts/feishu_direct_ingest.py "<feishu_url>" -o output/<id>/Q01 --save-raw-blocks
```

**图片语义解析（P0 必做）：**
```bash
python3 scripts/parse_image_assets.py \
  --manifest output/<id>/Q01/asset_manifest.json \
  --output-json output/<id>/Q01/image_semantics.json \
  --output-md output/<id>/Q01/image_semantics.md \
  --details-dir output/<id>/Q01/image_details \
  --backend auto
```

**状态机图、流程图、泳道图是 P0 必解析项** — 必须转为 Mermaid 输出。如果无法解析，标为 GAP P0 阻断。

### Step 1: 图片全量解析

1. 逐张读取所有下载的图片（board 类优先）。
2. 每张图片记录：文件名、语义描述、关联的业务模块。
3. 状态机图 → 转为 Mermaid `stateDiagram-v2`。
4. 流程图/泳道图 → 转为 Mermaid `flowchart`。
5. 输出图片资产表到报告中（文件名 | 语义描述 | 关联 REQ）。

**Step 1 即时检查：**
- [ ] 状态机图是否转为 Mermaid？节点是否只有状态（名词），动作在边上？
- [ ] 流程图中是否有 UI 提示被当作流程节点？
- [ ] 图片底部/边缘的注释文字是否遗漏？
- [ ] 正常路径和异常终结是否分开画？

### Step 2: 通读全文+图片，建立完整业务理解

1. 通读 PRD 全文 + Step 1 解析的图片语义，建立完整的业务理解。
2. 识别核心要素：业务流程、状态机、角色权限、系统边界、数据流向。
3. 标注 PRD 中的模糊点、矛盾点、缺失点（后续进入 GAP/OPEN）。
4. 如果是重跑，必须先读取旧版产物的 structured JSON 作为数据基线（确保数量不减少），但报告必须按当前规范重新生成，**禁止直接复制旧版文件做增量修改**。旧版产物可能本身有格式错误或内容缺陷，读取时必须独立判断，不能照抄。

### Step 3: 需求结构化 (REQ/BR/SE/GAP/OPEN)

**3a. REQ/BR：**
1. 逐段提取 REQ（功能点级别）。
2. 拆分分支需求为 BR（验收条件级别，必须包含完整字段、枚举值、校验规则、提示文案）。
3. 对每条需求补齐非功能语义（幂等/一致性/权限/可观测性）并落到 SE。

**3a 即时检查：**
- [ ] 抽查任意一个 BR：是否只有概括描述？→ 有则返工，补充具体字段
- [ ] 最复杂的 REQ：BR 是否保留了 PRD 层级结构？→ 压平则返工
- [ ] 是否有操作流程描述？→ 至少核心功能有 Step1→Step2→完成
- [ ] PRD 中出现"并发""同时""批量"关键词时：是否提取了幂等/并发 SE 或 GAP？

**3b. SE（关键语义显式化 — Checklist 驱动）：**

1. **加载 SE Checklist**：从当前 profile 的 `se_checklist.yaml` 加载维度化审计清单。
   ```bash
   python -c "
   from pathlib import Path
   from dqg.quality.se_checklist import load_se_checklist, format_checklist_prompt
   profile_dir = Path('profiles/<profile_id>')
   prd = Path('output/<project_id>/Q01/ingest/ingest/plain_text_enhanced.txt').read_text()
   dims = load_se_checklist(profile_dir, prd_text=prd)
   print(format_checklist_prompt(dims))
   "
   ```
2. **逐维度扫描**：对每个 REQ/BR，按 checklist 的每个维度逐一提问。有发现则生成 SE，无发现则跳过。
3. 从文本与图片共同抽取 SE，禁止隐含语义。
4. 每个 SE 必须绑定到 REQ/BR，且有可验证判定依据（表格格式）。
5. SE 的 `category` 字段必须对应 checklist 维度名（如"并发/幂等""权限边界"）。

> **Checklist 维度说明**：通用维度（状态机/并发/权限/一致性/精度/异常/时间/外部依赖）所有项目都扫描；Profile 特定维度（如 DDD 聚合、审批流）按技术栈自动加载；标记 `optional: true` 的维度（如 TMF）需在 Q02/Q03 确认后激活。

**3b 即时检查：**
- [ ] 每个 SE 是否有判定依据列？→ 必须是表格格式，不是纯文字
- [ ] 状态机的每条迁移边是否都有对应 SE？→ 遍历边，逐条确认
- [ ] 循环边（如驳回→重新发起）是否有数据流定义？→ 容易遗漏

**3c. GAP/OPEN：**
1. GAP：PRD 存在实现依赖但无明确口径。每个 GAP 必须标注风险等级（P0/P1/P2）。
2. OPEN：口径冲突/多解，需要评审拍板。每个 OPEN 必须标注决策方。
3. 每个 GAP/OPEN 必须挂载到具体 REQ/BR/SE，禁止孤立条目。

**3c 即时检查：**
- [ ] 每个 GAP 是否有风险等级（P0/P1/P2）？
- [ ] 每个 OPEN 是否有决策方（产品/研发/业务）？
- [ ] 对每个 GAP 问：这个"缺失"是否有合理的设计原因？→ 有则改为 OPEN 或删除

### Step 4: 自检（提交前强制检查）

**格式前置检测（必须在人工自检前跑）：**
```bash
python -m dqg.quality.checks.report_quality_checks output/<project_id> <project_id> Q01
```
如果有 source_annotation / reasoning_log_quality / skill_reference 问题，必须修复后再继续。不要等 finalize 才发现。

- [ ] 每条 PRD 中的明确需求都已进入 REQ/BR
- [ ] 每个 BR 包含完整的字段列表、枚举值、校验规则、提示文案（禁止概括性描述）
- [ ] 每条关键语义都已进入 SE，且有判定依据
- [ ] 每个冲突点都已进入 OPEN（含决策方）
- [ ] 每个缺失口径都已进入 GAP（含风险等级 P0/P1/P2）
- [ ] 每张图片都有语义描述和关联 REQ
- [ ] 状态机已转为 Mermaid 图
- [ ] 流程图已转为 Mermaid 图
- [ ] 未输出 UT/EUT
- [ ] 如果是重跑：新版是旧版的超集（REQ/BR/SE/GAP/OPEN 数量不减少，内容不丢失）
- [ ] 每条结论行有 `[来源: 文件名:行号]` 标注（参见 references/report-format-spec.md §1）
- [ ] 推理日志使用 `### Step N` 标记且 ≥ 3 个（参见 references/report-format-spec.md §2）
- [ ] 推理日志引用了 SKILL.md 的 Step 编号

### Step 5: Judge/Critique（提交前自我评审）

1. **Judge 评审**：对照 PRD 原文逐条验证每个 REQ/BR/SE 的准确性。
   - 每个 BR 能否在 PRD 中找到原文依据？
   - 每个 SE 的判定依据是否具体可测试？
   - GAP/OPEN 是否遗漏了 PRD 中的模糊点？

2. **Critique 批评**：假设输出有遗漏和错误，主动找问题。
   - 重点检查：并发/幂等/权限/异常流/状态迁移边界
   - 每个发现记录为：问题类型（FN/FP/VAGUE）+ 严重度 + 修正建议

3. 将发现记录在报告末尾的"自我评审记录"章节。

### Step 6: 修正

根据 Step 5 发现的问题修正报告，修正完成后重新执行 Step 4 自检确认。

**全部通过后，才能执行 `dqg-run <project> finalize A`。**

## 上下文加载与缓存原则（Token 优化）

| 缓存文件 | 存在时 | 不存在时 |
|----------|--------|---------|
| `_upstream_context.md` | 直接用，不回读 PRD 原文 | 由 context_loader 自动生成 |
| `image_semantics.md` | 直接引用文本，不重新读图片 | Step 1 中逐张解析后生成 |
| `plain_text_summary.md` | 用摘要代替全文 | PRD >3000 行时执行摘要预处理 |
| `phase_a_structured.json`（重跑） | 先读取作为基线，增量修改 | 首次执行正常生成 |

禁止在 `image_semantics.md` 已存在时重新逐张读取图片；禁止在 `_upstream_context.md` 已存在时回读飞书原文。

## 输出模板

复用 `../../references/report-template.md` + `../../references/image-semantics-mapping-template.md`。

报告必须包含以下标准章节（缺一不可）：

1. **PROFILE_CONTEXT** — 技术栈基线
2. **项目信息** — 项目名/用户/优先级/排除范围
3. **状态机** — Mermaid stateDiagram（如涉及）
4. **业务流程** — Mermaid flowchart
5. **图片资产清单** — 表格（#/来源/类型/内容/关联REQ）
6. **REQ/BR 需求清单** — 按模块分组，每条有来源标注和置信度
7. **SE 关键语义清单** — 表格（ID/绑定/语义/判定依据/置信度）
8. **GAP 缺口清单** — 表格（ID/描述/关联/风险/置信度）
9. **OPEN 待确认清单** — 表格（ID/问题/关联/决策方/置信度）
10. **边界约定** — Always/Ask First/Never 三级
11. **范围外发现**
12. **自我评审记录** — Judge + Critique
13. **统计** — REQ/BR/SE/GAP/OPEN 数量表格

详见 [references/output-templates.md](references/output-templates.md)。

### `phase_a_structured.json` 格式（必须严格遵守）

```json
{
  "project_id": "项目ID",
  "requirements": [
    {
      "req_id": "REQ-001",
      "description": "需求描述",
      "priority": "P0",
      "trigger": "进入工单详情页",
      "behavior_change": "展示申请提前交车按钮",
      "acceptance_criteria": "四个状态下按钮可见，其他状态不可见",
      "source": "plain_text.txt:79"
    },
    {
      "req_id": "BR-001",
      "parent_id": "REQ-001",
      "description": "按钮展示-工单状态条件",
      "trigger": "进入工单详情页",
      "behavior_change": "仅在待申请结算等四个状态展示按钮",
      "acceptance_criteria": "四个状态下按钮可见，其他状态不可见",
      "source": "plain_text.txt:79"
    }
  ],
  "semantic_expectations": [
    {
      "se_id": "SE-001",
      "description": "提前交车申请幂等控制",
      "category": "幂等/并发",
      "bound_reqs": ["REQ-001", "BR-006"],
      "confidence": "高",
      "source": "plain_text.txt:79; comments.md:#10"
    }
  ],
  "gaps": [
    {
      "gap_id": "GAP-001",
      "related_ids": ["REQ-001", "BR-009"],
      "description": "审批拒绝后是否可重新申请",
      "risk_level": "中",
      "required_clarification": "需明确：拒绝后是否允许重新申请？"
    }
  ],
  "open_items": [
    {
      "open_id": "OPEN-001",
      "related_ids": ["REQ-001", "SE-005"],
      "question": "待交车→已交车的流转条件确认",
      "options": "A: 自费已支付+代驾单服务完成 B: 仅自费已支付",
      "decision_owner": "产品+开发"
    }
  ],
  "conclusion": "有条件通过"
}
```

**字段约束：**
- `requirements`: REQ 必须有 `priority`；BR 必须有 `parent_id`；所有条目必须填写 `trigger`、`behavior_change`、`acceptance_criteria`、`source`
- `semantic_expectations`: `bound_reqs` 必填（至少绑定一个 REQ/BR）；`category` 和 `confidence` 必填；`source` 必填
- `gaps`: `risk_level` 必填（高/中/低）；`required_clarification` 必填
- 报告中有的结构化信息必须同步到 JSON，JSON 不能是报告的降级版

## 通过标准

1. REQ/BR 结构化率 = 100%
2. 每个 BR 包含完整字段、枚举值、校验规则、提示文案（能直接写测试用例）
3. SE 显式化率 = 100%，每个 SE 有判定依据
4. 所有冲突语义已进入 OPEN（含决策方）
5. 所有实现前置缺口已进入 GAP（含风险等级）
6. 所有图片已解析并输出图片资产表
7. 状态机和流程图已转为 Mermaid
8. Step 4 自检清单全部通过
9. Step 5 Judge/Critique 已执行，发现的问题已在 Step 6 修正

## Anti-Rationalization（禁止偷懒）

| 常见借口 | 为什么不能接受 | 正确做法 |
|---------|--------------|---------|
| "这个需求很简单，不需要拆 BR" | 简单需求也有隐式规则，不拆就会漏 | 每个 REQ 至少拆出 1 条 BR |
| "图片只是示意，不用解析" | 状态机/流程图是 P0 必解析项，跳过即 BLOCKER | 调用 VLM 解析，转 Mermaid |
| "这个 GAP 不重要" | GAP 必须有风险等级，重要性由人判断不由 AI 跳过 | 标注 P0/P1/P2，交给 approve 阶段决策 |
| "PRD 没写的就不用管" | PRD 没写的恰恰是 GAP/OPEN，必须识别 | 模糊点标 GAP，缺失定义标 OPEN |
| "SE 和 BR 差不多，不用单独列" | SE 是可验证的业务语义，BR 是业务规则，粒度不同 | SE 必须有判定依据，能直接写测试 |
| "并发/幂等场景 PRD 没提" | 隐式语义是 SE 的核心价值，不提不代表不存在 | 主动识别并发/幂等/精度/超时等隐式语义 |

## 验证标准（Verification）

| 验证项 | 检查方式 | 阻断级别 |
|--------|---------|---------|
| 推理日志存在 | finalize_checks: `_reasoning_log.md` 存在且 > 100 字符 | BLOCKED |
| 产物数量不回退 | finalize_checks: 对比 `_prev_counts.json`（REQ/BR/SE/GAP/OPEN 数量） | REGRESSION |
| Schema 校验 | schemas/phase_a.py 验证 `phase_a_structured.json` | BLOCKED |
| 跨 Phase ID 引用 | cross_phase_check: REQ/BR/SE ID 格式和唯一性 | WARNING |
| 图片已解析 | image_semantics.json 存在且 ok 数量 > 0（有图片时） | 人工确认 |

## 禁止事项

1. 禁止"按规则处理""展示完整信息"这类概括性描述，必须列出具体字段和规则。
2. 禁止将图片语义当作可忽略信息。状态机/流程图是 P0 必解析项。
3. 禁止在 GAP/OPEN 未闭环时给"无歧义"结论。
4. 禁止跳过 Step 4 自检和 Step 5 Judge/Critique 直接 finalize。
5. 禁止重跑时从零重写，必须在旧版基线上增量修改，新版必须是旧版超集。
6. 禁止 GAP 没有风险等级、OPEN 没有决策方。
