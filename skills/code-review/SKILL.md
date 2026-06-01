---
name: code-review
description: "Phase Q07: 预落地代码结构化评审，聚焦需求一致性与 confirm-first 机制。用户要求对分支代码做评审，或准备合并前的质量检查时触发。"
license: MIT
compatibility:
  claude: ">=3"
metadata:
  phase: Q07
  depends_on: [Q01]
  outputs: [phase_d_structured.json, phase_d_report.md, _reasoning_log.md, _blast_radius.md]
allowed-tools:
  - Bash
  - Read
  - Write
  - Edit
  - Grep
  - AskUserQuestion
---

# Phase Q07: 代码评审

IRON LAW: 每条发现必须有代码证据（文件:行号 + 代码片段），无证据的发现必须删除，不报比误报好。

对当前分支相对基线分支的改动做结构化评审，核心目标：预防需求遗漏。

## 技术栈基线

优先按当前项目 profile 选择评审基线：
- `java-ddd-tmf`：`../../profiles/java-ddd-tmf/baseline.md`（第 5 节）
- `go-service`：`references/go-service-baseline.md`（分层职责与服务边界）

若未提供 profile，回退到 Java 默认基线。

## 上下文加载原则（Token 优化）

1. 优先读取 `_upstream_context.md`，不要回读原始 PRD 文档或 `plain_text.txt`。
2. 图片语义已预解析到 `image_semantics.md`，直接引用文本结论，不要重新读取图片文件。
3. Phase Q01 结构化产物是唯一的需求基线，不要回溯原始需求文档。

## 核心原则：调用链路级评审

对于 DDD+TMF 项目，禁止孤立地按文件做评审。必须按调用链路做评审：

1. **从 API 入口追踪完整链路**：Provider → CmdExe → DomainService → TMF.execute → decideSteps → Step → Ability → Extension → Gateway
2. **在链路上下文中评估问题**：某个能力（如幂等、并发控制、状态校验）可能不在当前类实现，而在链路的上层或下层。必须确认整条链路的保护是否完整后再下结论
3. **标注保护点位置**：每个发现必须说明"该能力在链路的哪一层实现/缺失"
4. **区分入口差异**：同一个 Ability 可能被多个入口调用（用户触发、定时任务、MQ 回调、BPM 回调），不同入口的保护链路可能不同，需逐一检查

### 链路追踪步骤

对每个改动的功能点：
```
Step 1: 找到 API Provider 入口
Step 2: 追踪 CmdExe 的编排逻辑
Step 3: 进入 DomainService，看 TMF.execute 的 decideSteps
Step 4: 逐个 Step 检查：调了哪个 Ability？Ability 调了哪个 Extension？
Step 5: Extension 的具体实现做了什么？Gateway 层的 SQL 是什么？
Step 6: 在完整链路上标注：分布式锁在哪层？幂等检查在哪层？状态校验在哪层？
Step 7: 检查是否所有入口都经过了这些保护点
```

## 变更大小门禁（Change Sizing）

| 变更行数 | 分级 | 评审策略 |
|---------|------|---------|
| ~100 行 | 好 | 正常评审，单次完成 |
| ~300 行 | 可接受 | 分模块评审，重点关注核心改动 |
| ~500 行 | 偏大 | 建议拆分，标记 `CHANGE_TOO_LARGE` |
| ~1000+ 行 | 必须拆分 | 输出拆分建议后暂停评审，等开发者拆分后重新提交 |

## 评论严重级别标签

每条评审发现必须带严重级别前缀：

| 前缀 | 含义 | 是否必须修复 |
|------|------|------------|
| `[BLOCKER]` | 会导致线上故障、数据损坏、资金损失 | 必须修复，阻断合并 |
| `[MAJOR]` | 功能缺陷、安全风险、性能问题 | 必须修复或显式 defer（附理由） |
| `[MINOR]` | 可改进但不影响正确性 | 可选，建议采纳 |
| `[INFO]` | 代码风格、命名、格式、知识分享 | 仅供参考，无需行动 |

## 参考资料加载规则（按需读取，不要一次性全部加载）

| 场景 | 读取文件 |
|------|---------|
| Java 代码质量（异常处理/性能/边界条件/N+1） | `references/code-quality-checklist.md` |
| 安全审查（XSS/注入/AuthN/AuthZ/Race Condition） | `references/security-checklist.md` |
| SOLID 原则与架构（SRP/OCP/LSP/ISP/DIP） | `references/solid-checklist.md` |
| 涉及金额/退款/积分/券/库存等资产操作 | `references/fund-safety-identification.md` |
| Java/Spring/MyBatis/Redis/MQ 资损风险模式 | `references/fund-safety-java-patterns.md` |
| 治理闭环（对账/告警/熔断/审计日志） | `references/fund-safety-governance.md` |
| 依赖新增/Feature Flag/通用 checklist | `references/review-checklist.md` |

## 评审维度（完整清单）

### 基础维度（每次必查）

1. **需求一致性**：逐条对照 Phase Q01 的 REQ/BR/SE，检查代码是否正确实现
2. **调用链路完整性**：从 API 入口追踪到 Gateway 层，确认保护点位置
3. **异常处理**：catch 是否吞异常、错误码是否正确、是否有降级
4. **DDD 分层职责**：业务逻辑是否在正确的层

### 代码质量维度（读取 code-quality-checklist.md）

5. **性能**：N+1 查询、循环内 RPC、缺少批量操作、缺少缓存
6. **边界条件**：null/空集合/0值/负数/超大值/off-by-one
7. **错误处理**：空 catch、过宽 catch、错误信息泄露

### 安全维度（读取 security-checklist.md）

8. **输入安全**：SQL 注入、XSS、SSRF、路径遍历
9. **认证授权**：缺少 auth guard、IDOR、租户隔离
10. **并发安全**：Race Condition、TOCTOU、check-then-act、读改写无锁
11. **密钥管理**：硬编码密钥、日志泄露 PII

### 资金安全维度（涉及金额/资产时读取 fund-safety-*.md）

12. **资产识别**：操作的资产是什么、从哪流向哪
13. **幂等与防重**：是否有幂等键、唯一索引、去重记录
14. **金额精度**：BigDecimal 构造方式、舍入模式、元分转换、溢出检查
15. **状态机完整性**：状态流转是否覆盖所有合法/非法路径、是否可绕过
16. **事务边界**：@Transactional 是否生效、事务内外副作用顺序
17. **治理闭环**：对账、告警、熔断、审计日志、修复工具

### SOLID 与架构维度（读取 solid-checklist.md）

18. **单一职责**：一个类/方法是否只做一件事
19. **开闭原则**：扩展新功能是否需要修改已有代码
20. **依赖倒置**：是否依赖抽象而非具体实现

### Surgical Changes 维度（变更范围合理性）

21. **变更追溯性**：每一行变更是否能追溯到 REQ/BR/SE？无法追溯的变更标记为 `SCOPE_CREEP`
22. **顺手改进检查**：是否有"顺手"改了相邻代码、注释、格式、命名？与需求无关的改动标记为 `DRIVE_BY_REFACTOR`
23. **风格一致性**：新代码是否匹配已有代码风格（缩进/命名/引号/注释风格）？不匹配标记为 `STYLE_DRIFT`
24. **死代码处理**：是否删除了不该删的已有代码？自己的变更产生的孤儿代码是否清理了？
25. **变更大小**：单个方法/类的变更是否过大？超过 300 行的单文件变更建议拆分

**检验标准：** 把 diff 中每一行变更列出来，问"这行是为了解决什么需求？"。回答不了的行就是多余的。

## 依赖新增审查（Dependency Discipline）

当 diff 中出现新的 `import`、`pom.xml` 依赖、`go.mod` require 时，必须回答 5 个问题：现有技术栈能否解决、依赖体积/复杂度是否合理、是否活跃维护、是否有已知安全漏洞、License 是否兼容。

详见 [references/review-checklist.md](references/review-checklist.md)。

## Feature Flag 检查

当 PR 是大功能的部分实现时，检查：
- 未完成的功能是否有 feature flag 保护？
- 用户是否能触达未完成的功能路径？

## 强制约束

先读取 `../modules/00_policy_constraints_zh.md`。若约束冲突，立即停止并输出 `STATUS: BLOCKED`。

## 执行顺序（固定）

1. `../modules/01_base_branch_context_zh.md` — 基线分支上下文
2. `../modules/02_intent_scope_check_zh.md` — 意图与范围确认
3. **调用链路梳理** — 对每个改动功能点追踪完整 TMF 链路，输出 `CALL_CHAIN` 章节
4. `../modules/03_java_review_checklist_zh.md` — 评审 checklist（在链路上下文中执行）
5. `../modules/04_diff_and_context_scan_zh.md` — Diff 扫描
6. `../modules/05_confirm_first_fix_flow_zh.md` — Confirm-first 修复流程
7. `../modules/06_evidence_validation_report_zh.md` — 证据验证报告

## 自检（提交前强制检查）

- [ ] 所有 BLOCKER 级问题有代码证据
- [ ] REQ/BR/SE → CODE/TEST 覆盖缺口已确认
- [ ] 每个发现标注了来源（文件名:行号）和置信度
- [ ] DDD+TMF 项目已追踪完整调用链路
- [ ] 如果是重跑：新版是旧版超集
- [ ] 推理日志 `_reasoning_log.md` 已同步输出
- [ ] 每条结论行有 `[来源: 文件名:行号]` 标注（参见 references/report-format-spec.md §1）
- [ ] 推理日志使用 `### Step N` 标记且 ≥ 3 个（参见 references/report-format-spec.md §2）
- [ ] 推理日志引用了 SKILL.md 的 Step 编号

## Judge/Critique（提交前自我评审）

- **Judge**：对照代码验证每个评审发现的准确性，逐条确认证据链完整、结论无误
- **Critique**：假设有遗漏，重点检查安全漏洞、资源泄露、并发问题
- 记录在报告末尾「自我评审记录」章节

## 修正

根据 Judge/Critique 发现的问题修正评审报告：删除证据不足的发现、补充遗漏的安全漏洞/资源泄露/并发问题、更新覆盖缺口摘要和严重级别。

## 评审输出要求

1. 先调用链路图，再问题清单，再结论。
2. 每条问题：`严重级别 + 文件:行号 + 风险说明 + 修复建议 + 证据 + 链路位置`。
3. 链路位置格式：`[链路: Provider → CmdExe → Service → Step(xxx) → Ability(xxx)]`。
4. 禁止"可能、看起来、应该"等无证据表述。
5. 必须给出 `REQ/BR/SEM → CODE/TEST` 覆盖缺口摘要。
6. 图片语义未入链路时单列 `SEM_GAP`。
7. **禁止孤立评审**：不得仅因某个类缺少某功能就标记为问题，必须先确认该功能是否在链路的其他层实现。
8. 报告建议复用 `../../references/code-review-template.md`，并在报告头包含 `PROFILE_CONTEXT`。

## 状态协议

| 状态 | 含义 |
|------|------|
| `DONE` | 评审完成，无未决风险 |
| `DONE_WITH_CONCERNS` | 评审完成，有未修复或未验证项 |
| `BLOCKED` | 被关键约束阻断 |
| `NEEDS_CONTEXT` | 缺少必要上下文 |

## 输出模板

报告必须包含以下标准章节（缺一不可）：

1. **PROFILE_CONTEXT** — 技术栈基线
2. **评审范围** — 分支名/变更文件数/变更行数
3. **评审发现** — 按 BLOCKER/MAJOR/MINOR/INFO 分级，每条有 issue_id + 文件:行号 + 置信度
4. **调用链分析** — 变更影响范围（caller/callee）
5. **安全审查** — OWASP Top 10 相关检查
6. **评审结论** — PASS / PASS_WITH_RISKS / FAIL + 问题数量汇总
7. **自我评审记录** — Judge + Critique

## 通过标准

评审报告标记为 `DONE` 前，必须满足：
1. 自检清单全部通过
2. Judge/Critique 已执行且问题已修正
3. 推理日志已输出

## Anti-Rationalization（禁止偷懒）

| 常见借口 | 为什么不能接受 | 正确做法 |
|---------|--------------|---------|
| "这个改动很小，不需要追踪调用链" | 小改动也可能影响下游 callers | 用 blast_radius 分析影响范围 |
| "并发场景不太可能发生" | 只要是写操作就有并发可能 | 检查锁/幂等/版本号 |
| "金额用 double 是历史代码" | 历史代码不是借口，金额必须 BigDecimal | 标 BLOCKER，不管是不是历史代码 |
| "这个 finding 我不太确定" | 不确定就不要写，每条 finding 必须有代码证据 | 引用具体 文件:行号 和代码片段 |
| "整体代码质量还行" | 禁止整体评价，必须逐条检查 REQ/SE 对齐 | 逐条对照 Phase Q01 产物 |
| "Service 层看完就够了" | DDD+TMF 必须追踪到 Gateway 层 | Controller→Service→Domain→Gateway 完整链路 |
| "这个方法没改过不用看" | 调用链上的方法都可能受影响 | 追踪 caller/callee 确认影响范围 |
| "回调接口内部调用不需要验签" | 内部 RPC 也可能被伪造 | 检查所有外部入口的信任边界 |
| "只给修复建议不给代码" | 研发需要具体的修复方案才能行动 | 每条发现必须有代码证据+修复方案+修复原因 |
| "顺手改了一下格式/命名" | 与需求无关的改动增加 review 负担和回归风险 | 标 DRIVE_BY_REFACTOR，建议单独 PR |

## Question-Style 评审指令（用问题代替模糊指令）

评审每个变更文件时，逐条回答以下问题：

### 需求一致性
- 问自己：这个方法实现的逻辑和 PRD/BR 描述的一致吗？有没有多做或少做？
- 问自己：Phase Q01 的 11 个 SE，哪些在这个文件中有实现？实现正确吗？

### 并发安全
- 问自己：如果两个请求同时打进来会怎样？共享了什么状态？
- 问自己：这个操作是原子的吗？check 和 act 之间状态会变吗？
- 问自己：锁的粒度对吗？锁的范围覆盖了整个关键区间吗？

### 金额安全
- 问自己：这个金额字段用的是 BigDecimal 还是 double/float？
- 问自己：元和分有没有混淆？舍入方向一致吗？
- 问自己：如果金额为 0/负数/超大值，代码会怎样？

### 状态机
- 问自己：从状态 A 到状态 B 的转移，代码有白名单校验吗？
- 问自己：有没有可能绕过中间状态直接跳到终态？

### 异常处理
- 问自己：这个 catch 块吞了异常吗？调用方知道出错了吗？
- 问自己：异常后数据状态一致吗？事务回滚了吗？

### Surgical Changes
- 问自己：这行变更是为了解决什么需求？回答不了就是多余的。
- 问自己：新代码匹配已有代码风格吗？

## Pre-Delivery Checklist（具体可验证）

### 正确性
- [ ] 每条发现有 finding_id + 文件:行号 + 代码证据 + 修复方案 + 修复原因
- [ ] 无 "可能""看起来""应该" 等无证据表述
- [ ] BLOCKER 级发现的修复方案可直接执行（不是"建议加强"）

### 完整性
- [ ] REQ/BR/SE → CODE 覆盖缺口摘要已输出
- [ ] 所有变更文件都已评审（不能只看核心文件跳过 DTO/Convert）
- [ ] 资金安全五步法已执行（涉及金额/资产时）

### 格式统一
- [ ] 28 条发现格式统一（问题+路径+证据+方案+原因）
- [ ] 按 BLOCKER/MAJOR/MINOR/INFO 分级，数量汇总正确
- [ ] 评审结论为 DONE/DONE_WITH_CONCERNS/BLOCKED 之一

## 验证标准（Verification）

| 验证项 | 检查方式 | 阻断级别 |
|--------|---------|---------|
| 推理日志存在 | finalize_checks: `_reasoning_log.md` 存在且 > 100 字符 | BLOCKED |
| 产物数量不回退 | finalize_checks: 对比 `_prev_counts.json` | REGRESSION |
| Schema 校验 | schemas/phase_d.py 验证 `phase_d_structured.json` | BLOCKED |
| 无 BLOCKER 未修复 | 结构化 JSON 中无 severity=BLOCKER 的 open finding | 人工确认 |
| 影响范围已分析 | `_blast_radius.md` 存在（有 code_repo 时） | 人工确认 |

### `phase_d_structured.json` 格式（必须严格遵守）

```json
{
  "project_id": "项目ID",
  "findings": [
    {
      "finding_id": "FIND-001",
      "file_path": "your-module/src/main/java/com/example/service/OrderService.java",
      "description": "applyEarlyDeliveryAuthStore 无分布式锁，幂等检查与 BPM 创建之间存在竞态窗口",
      "severity": "BLOCKER",
      "related_req": "SE-002",
      "suggestion": "在 applyEarlyDeliveryAuthStore 入口加分布式锁（以 mrNo 为 key），锁范围覆盖幂等检查到 BPM 创建"
    }
  ],
  "conclusion": "PASS|PASS_WITH_RISKS|FAIL"
}
```

**字段约束（严格遵守，否则 Schema 校验 BLOCKED）：**
- `finding_id`：必填，非空字符串（如 `FIND-001`）
- `severity`：必填，枚举 `BLOCKER` / `MAJOR` / `MINOR` / `INFO`
- `description`：必填，非空字符串
- `file_path`：可选，指向具体文件路径
- `related_req`：可选，关联的 REQ/BR/SE ID
- `suggestion`：可选，修复建议
- `conclusion`：可选，整体结论

## 禁止事项

1. 禁止调用 gh、codex、open、Greptile API 等外部平台工具。
2. 禁止自动修改代码（未确认前不能改）。
3. 禁止自动 commit/push/建 PR。
4. 禁止跳过自检和 Judge/Critique 直接 finalize。
5. 禁止重跑时从零重写。
