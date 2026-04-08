---
name: code-review
description: "Phase D: 预落地代码结构化评审，聚焦需求一致性与 confirm-first 机制"
trigger: "用户要求对分支代码做评审，或准备合并前的质量检查"
allowed-tools:
  - Bash
  - Read
  - Write
  - Edit
  - Grep
  - AskUserQuestion
---

# Phase D: 代码评审

对当前分支相对基线分支的改动做结构化评审，核心目标：预防需求遗漏。

## 技术栈基线

优先按当前项目 profile 选择评审基线：

- `java-ddd-tmf`：`references/java-ddd-tmf-baseline.md`（第 5 节）
- `go-service`：`references/go-service-baseline.md`（分层职责与服务边界）

若未提供 profile，回退到 Java 默认基线。

## 上下文加载原则（Token 优化）

1. 优先读取 `_upstream_context.md`，不要回读原始 PRD 文档或 `plain_text.txt`。
2. 图片语义已预解析到 `image_semantics.md`，直接引用文本结论，不要重新读取图片文件。
3. Phase A 结构化产物是唯一的需求基线，不要回溯飞书原文。

## 核心原则：调用链路级评审

对于 DDD+TMF 项目，禁止孤立地按文件做评审。必须按调用链路做评审：

1. **从 API 入口追踪完整链路**：Provider → CmdExe → DomainService → TMF.execute → decideSteps → Step → Ability → Extension → Gateway
2. **在链路上下文中评估问题**：某个能力（如幂等、并发控制、状态校验）可能不在当前类实现，而在链路的上层或下层。必须确认整条链路的保护是否完整后再下结论
3. **标注保护点位置**：每个发现必须说明"该能力在链路的哪一层实现/缺失"，而非仅指出某个类缺少某个功能
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

## 强制约束

先读取 `skills/modules/00_policy_constraints_zh.md`。若约束冲突，立即停止并输出 `STATUS: BLOCKED`。

## 执行顺序（固定）

1. `skills/modules/01_base_branch_context_zh.md` — 基线分支上下文
2. `skills/modules/02_intent_scope_check_zh.md` — 意图与范围确认
3. **调用链路梳理** — 对每个改动功能点追踪完整 TMF 链路，输出 `CALL_CHAIN` 章节
4. `skills/modules/03_java_review_checklist_zh.md` — 评审 checklist（在链路上下文中执行）
5. `skills/modules/04_diff_and_context_scan_zh.md` — Diff 扫描
6. `skills/modules/05_confirm_first_fix_flow_zh.md` — Confirm-first 修复流程
7. `skills/modules/06_evidence_validation_report_zh.md` — 证据验证报告

## 自检（提交前强制检查）

在生成最终报告前，必须逐项完成以下清单：

- [ ] 所有 BLOCKER 级问题有代码证据
- [ ] REQ/BR/SE → CODE/TEST 覆盖缺口已确认
- [ ] 每个发现标注了来源（文件名:行号）和置信度
- [ ] DDD+TMF 项目已追踪完整调用链路
- [ ] 如果是重跑：新版是旧版超集
- [ ] 推理日志 _reasoning_log.md 已同步输出

## Judge/Critique（提交前自我评审）

在自检通过后、finalize 前执行：

- **Judge**：对照代码验证每个评审发现的准确性，逐条确认证据链完整、结论无误
- **Critique**：假设有遗漏，重点检查安全漏洞、资源泄露、并发问题
- 记录在报告末尾「自我评审记录」章节

## 修正

根据 Judge/Critique 发现的问题修正评审报告：

1. 删除证据不足或结论错误的发现
2. 补充遗漏的安全漏洞、资源泄露、并发问题
3. 更新覆盖缺口摘要和严重级别
4. 确保修正后的报告通过自检清单全部项目

## 评审输出要求

1. 先调用链路图，再问题清单，再结论。
2. 每条问题：`严重级别 + 文件:行号 + 风险说明 + 修复建议 + 证据 + 链路位置`。
3. 链路位置格式：`[链路: Provider → CmdExe → Service → Step(xxx) → Ability(xxx)]`，标注问题在链路的哪个位置。
4. 禁止"可能、看起来、应该"等无证据表述。
5. 必须给出 `REQ/BR/SEM → CODE/TEST` 覆盖缺口摘要。
6. 图片语义未入链路时单列 `SEM_GAP`。
7. **禁止孤立评审**：不得仅因某个类缺少某功能就标记为问题，必须先确认该功能是否在链路的其他层实现。
8. 报告建议复用 `references/code-review-template.md`，并在报告头包含 `PROFILE_CONTEXT`（来自 `output/<project>/phaseD/_profile_context.md`）。

## 状态协议

| 状态 | 含义 |
|------|------|
| `DONE` | 评审完成，无未决风险 |
| `DONE_WITH_CONCERNS` | 评审完成，有未修复或未验证项 |
| `BLOCKED` | 被关键约束阻断 |
| `NEEDS_CONTEXT` | 缺少必要上下文 |

## 通过标准

评审报告标记为 `DONE` 前，必须满足：

1. 自检清单全部通过
2. Judge/Critique 已执行且问题已修正
3. 推理日志已输出

## 禁止事项

1. 禁止调用 gh、codex、open、Greptile API 等外部平台工具。
2. 禁止自动修改代码（未确认前不能改）。
3. 禁止自动 commit/push/建 PR。
4. 禁止跳过自检和 Judge/Critique 直接 finalize。
5. 禁止重跑时从零重写。
