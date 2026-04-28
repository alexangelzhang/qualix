---
name: tech-quality-review
description: "Phase Q03: 评审技术方案自身设计质量（架构/接口/数据/异常/性能）。用户明确要求评审技术方案质量，或 Phase Q04 完成后进入时触发。"
license: MIT
compatibility:
  claude: ">=3"
metadata:
  phase: Q03
  depends_on: [Q01, Q04]
  outputs: [phase_a6_structured.json, tech_design_quality_review.md, _reasoning_log.md]
  forbidden_outputs: [UT, EUT]
allowed-tools:
  - Bash
  - Read
  - Write
  - Edit
  - Grep
  - AskUserQuestion
---

# Phase Q03: 技术方案质量评审

独立于覆盖度审计，专注技术方案自身设计质量。禁止输出 UT/EUT。

## 核心原则

1. 逐维度交互式评审，每个维度确认后才进入下一个。
2. 先按 profile 选择基线：`java-ddd-tmf` 用 `../../profiles/java-ddd-tmf/baseline.md`，`go-service` 用 `references/go-service-baseline.md`。
3. Failure Mode 驱动：每个关键业务路径至少一个故障场景。
4. 证据优先：每条结论附技术方案中的具体证据。

## 上下文加载原则（Token 优化）

1. 优先读取 `_upstream_context.md`，不要回读原始 PRD 文档或 `plain_text.txt`。
2. 图片语义已预解析到 `image_semantics.md`，直接引用文本结论，不要重新读取图片文件。
3. Phase Q01 结构化产物是唯一的需求基线，不要回溯飞书原文。

## 执行流程

### Step 0: 范围确认与链路梳理

1. 读取技术方案文档（飞书直读优先）。
2. 识别架构类型：DDD / TMF / DDD+TMF / 其他。
3. **技术方案输入质量检查**：
   - 检查是否有 HLD（整体架构+数据模型+状态机+非功能性设计）
   - 检查是否有 LLD（每个接口的实现逻辑，不只是签名；DDD 各层职责分配；事务边界；外部调用细节）
   - **LLD 不存在或严重不完整 → 阻断执行**，提示补充后重新提交
   - LLD 部分缺失 → 继续执行，但标注缺失范围，相关接口评审置信度降为 Medium/Low
4. **feature 分支全链路梳理**（当提供代码仓库时）：
   - 从 API Provider 入口追踪每个改动功能点的完整调用链路
   - DDD+TMF 链路：Provider → CmdExe → DomainService → TMF.execute → decideSteps → Step → Ability → Extension → Gateway
   - 输出 `CALL_CHAIN` 章节，列出每个功能点的完整调用链路图
   - **必须覆盖所有 REQ**：逐条对照 Phase Q01 的 REQ 列表，确认每个 REQ 在代码仓库中都有对应的改动分析。如果某个 REQ 在 commit 范围内无对应代码改动，必须显式标注 `REQ-xxx: 未发现代码改动`，不得静默跳过

### Step 1: 架构设计评审

检查分层职责一致性（Client/Application/Domain/Infrastructure/TMF 链路）、系统依赖与边界、灰度发布策略。问题记录为 `ARCH-xxx`。

**STOP** — 展示发现，确认后继续。

### Step 2: 接口设计评审

逐个检查：入参完备性、出参完备性、幂等设计、版本兼容、批量限制、分页设计。问题记录为 `API-xxx`。

**STOP** — 展示发现，确认后继续。

### Step 3: 数据模型评审

检查：主键策略、索引设计、字段完备性、扩展性、数据一致性（跨表事务/双写补偿/枚举一致/时间精度）。问题记录为 `DATA-xxx`。

**STOP** — 展示发现，确认后继续。

### Step 4: 异常与容错评审

强制检查 12 类标准异常场景（详见 [references/exception-catalog.md](references/exception-catalog.md)）：参数校验失败、外部 RPC 超时、外部 RPC 返回错误、MQ 消费失败、数据库唯一键冲突、乐观锁冲突、分布式锁获取失败、定时任务执行失败、部分成功（事务半提交）、并发重复请求、配置缺失/错误、下游数据脏/格式异常。

同时检查重试与补偿机制。问题记录为 `EXC-xxx`。

**STOP** — 展示发现，确认后继续。

### Step 5: 性能与可观测性评审

性能风险点（列表查询/导出/定时任务/热点数据）、缓存设计、可观测性（日志/监控/链路追踪）。问题记录为 `PERF-xxx`。

**STOP** — 展示发现，确认后继续。

### Step 6: Failure Mode 分析

对每个关键业务路径列出故障场景，评估：
- `SAFE`：有处理 + 明确报错
- `RISK`：有处理但可能静默
- `CRITICAL_GAP`：无处理 + 静默失败或数据不一致（必须上线前修复）

### Step 7: 完整性 Gate

- [ ] 架构分层已逐项检查
- [ ] 所有接口已检查入参/出参/幂等/兼容性
- [ ] 所有新建表已检查主键/索引/字段/扩展性
- [ ] 异常场景矩阵已填写（12 类）
- [ ] 关键业务路径已做 Failure Mode 分析
- [ ] 性能风险点已识别
- [ ] 可观测性已检查
- [ ] 未输出 UT/EUT

### Step 8: 自检（提交前强制检查）

- [ ] 架构/接口/数据/异常/性能五个维度已逐项检查
- [ ] Phase Q01 的每个 REQ 都有对应的代码分析或显式标注「未发现代码改动」
- [ ] 每个 issue 有具体代码/设计证据支撑
- [ ] Failure Mode 分析覆盖所有写操作/RPC调用/状态迁移
- [ ] 无 CRITICAL_GAP
- [ ] 每个发现标注了来源和置信度
- [ ] 如果是重跑：新版是旧版超集
- [ ] 推理日志 `_reasoning_log.md` 已同步输出
- [ ] 每条结论行有 `[来源: 文件名:行号]` 标注（参见 references/report-format-spec.md §1）
- [ ] 推理日志使用 `### Step N` 标记且 ≥ 3 个（参见 references/report-format-spec.md §2）
- [ ] 推理日志引用了 SKILL.md 的 Step 编号

### Step 9: Judge/Critique（提交前自我评审）

1. **Judge**：对照技术方案原文验证每个 issue 的准确性，排除误读和过度推断。
2. **Critique**：假设输出有遗漏，重点检查并发/幂等/事务/超时/降级五个高风险领域。
3. 将结果记录在报告末尾「自我评审记录」章节。

### Step 10: 修正

根据 Step 9 发现的问题进行修正，修正完成后重新执行 Step 8 自检清单，确保全部通过。

## 输出模板

复用 `../../references/tech-design-quality-template.md`。

### `phase_a6_structured.json` 格式（必须严格遵守）

```json
{
  "project_id": "项目ID",
  "issues": [
    {
      "issue_id": "ARCH-001",
      "description": "问题描述",
      "severity": "CRITICAL|HIGH|MEDIUM|LOW",
      "suggestion": "修复建议",
      "dimension": "architecture|api|data|exception|performance",
      "evidence": "DOC-007 第3章"
    }
  ],
  "failure_modes": [
    {
      "business_path": "业务路径（如：提交审批）",
      "failure_scenario": "故障场景（如：BPM 创建超时）",
      "has_exception_handling": true,
      "user_impact": "用户影响",
      "status": "SAFE|RISK|CRITICAL_GAP"
    }
  ],
  "conclusion": "PASS|PASS_WITH_RISKS|FAIL"
}
```

**字段约束：**
- `issue_id`: 必填，格式 `(ARCH|API|DATA|EXC|PERF)-\d+`
- `severity`: 必填，枚举 CRITICAL/HIGH/MEDIUM/LOW
- `business_path`: 必填，不能用缩写 `path`
- `failure_scenario`: 必填，不能用缩写 `scenario`
- `status`: 必填，枚举 SAFE/RISK/CRITICAL_GAP，不能用 `assessment`

报告必须包含以下标准章节（缺一不可）：

1. **PROFILE_CONTEXT** — 技术栈基线
2. **评审范围** — 技术方案来源 + Phase Q01 产物
3. **五维度评审** — 架构/接口/数据/异常/性能，每个维度有 ✅/⚠️/❌ 标记
4. **评审发现** — 按 CRITICAL/HIGH/MEDIUM/LOW 分级，每条有 issue_id + 来源 + 置信度
5. **Failure Mode 分析** — 故障场景表格
6. **评审结论** — PASS / PASS_WITH_RISKS / FAIL + 问题数量汇总
7. **自我评审记录** — Judge + Critique
8. **统计** — CRITICAL/HIGH/MEDIUM/LOW/FM 数量

## 通过标准

1. 无 CRITICAL_GAP
2. 架构分层无 FAIL 项
3. 所有写操作接口有幂等设计
4. 涉及资金的操作有完整异常处理和补偿
5. P0 问题已有修复方案或明确排期
6. 自检清单全部通过
7. Judge/Critique 已执行且问题已修正
8. 推理日志已输出

## Anti-Rationalization（禁止偷懒）

| 常见借口 | 为什么不能接受 | 正确做法 |
|---------|--------------|---------|
| "这个接口没有并发场景" | 只要是写操作就有并发可能，必须分析 | 对每个写操作检查并发安全 |
| "异常处理代码里有 try-catch 了" | try-catch 存在不等于异常被正确处理 | 检查 catch 块是否有回滚/补偿/通知 |
| "Failure Mode 分析太重了" | 关键路径不做 FM 分析，线上出事才重 | 所有写操作/RPC/状态迁移必须有 FM |
| "这个问题影响不大，标 MINOR" | 涉及资金/数据一致性的问题一律 BLOCKER | 按业务影响定级，不按代码改动量 |
| "技术方案整体还行" | 禁止整体评价，必须逐维度检查 | 架构/接口/数据/异常/性能五维度逐项 |
| "12 类异常不是每个都适用" | 不适用的要显式标注"不适用+原因"，不能跳过 | 逐类检查，不适用的写明理由 |

## 验证标准（Verification）

| 验证项 | 检查方式 | 阻断级别 |
|--------|---------|---------|
| 推理日志存在 | finalize_checks: `_reasoning_log.md` 存在且 > 100 字符 | BLOCKED |
| 产物数量不回退 | finalize_checks: 对比 `_prev_counts.json`（issues/failure_modes） | REGRESSION |
| Schema 校验 | schemas/phase_a6.py 验证 `phase_a6_structured.json` | BLOCKED |
| 无 CRITICAL_GAP | 结构化 JSON 中无 severity=CRITICAL 的未解决 issue | BLOCKED |
| 异常矩阵覆盖 | 12 类异常每类有检查结论（覆盖/不适用+原因） | 人工确认 |

## 禁止事项

1. 禁止无证据评审。
2. 禁止跳过异常场景矩阵。
3. 禁止跳过 Failure Mode 分析。
4. 禁止存在 CRITICAL_GAP 时给"通过"结论。
5. 禁止跳过自检和 Judge/Critique 直接 finalize。
6. 禁止重跑时从零重写。
7. 禁止 issue 没有证据支撑。
