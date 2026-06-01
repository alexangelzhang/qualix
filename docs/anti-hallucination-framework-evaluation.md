# 三层防幻觉框架多维度评估

> 评估日期：2026-05-19  
> 适用范围：Qualix 全 Phase，重点覆盖 Q01 / Q05a / Q06 的防幻觉链路。

## 1. 结论摘要

三层防幻觉框架的架构方向是正确的：它没有把 LLM 输出当作事实，而是把 LLM 输出定义为可验证声明，并要求声明回到外部真相、结构化一致性和可执行产物上接受验证。

总体评价：

| 评估对象 | 评分 | 结论 |
| --- | ---: | --- |
| 原则框架 | 9.0 / 10 | 方向非常正确，抓住了“声明不等于事实”的核心问题 |
| Qualix 当前落地骨架 | 8.4 / 10 | Q01/Q05a/Q06 已形成对称防幻觉链路，Q05a 最硬，Q06 已补齐骨架 |
| 不可绕过审计系统成熟度 | 7.8 / 10 | 还需要统一 HARD/SOFT 语义、Evidence Graph 和 fail-closed 策略 |

一句话结论：三层框架已经能系统性降低幻觉，但下一阶段不应只是继续增加散点规则，而应收束为统一的 `claim / evidence / verifier / gate` 架构。

## 2. 框架定义

```text
Layer 0: 外部真相
  PRD 原文、代码库、schema、编译器、测试执行、coverage report、git diff、人工决策记录

Layer 1: LLM 声明
  结构化 JSON、ID、source、summary、coverage status、cross-phase references

Layer 2: LLM 产物
  测试代码、方案文档、审计报告、代码评审报告、补丁文件
```

三层本身只是骨架，真正的防幻觉能力来自三条交叉验证边：

| 验证边 | 目标 | 典型例子 |
| --- | --- | --- |
| L0 ↔ L1 | 验证结构化声明是否来自事实 | `SE.source ↔ PRD 行号`、`coverage_gate ↔ JaCoCo` |
| L1 ↔ L2 | 验证声明和产物是否一致 | `EUT.then ↔ 测试断言`、`impl_class ↔ @InjectMocks/import` |
| L2 ↔ L0 | 验证产物是否能被外部系统承认 | 编译、单测执行、coverage、类/方法/文件存在性 |

核心原则：LLM 可以提出声明，但不能自证声明。事实必须来自独立数据源或可执行验证。

## 3. 多维度评分

| 维度 | 评分 | 评价 |
| --- | ---: | --- |
| 认知正确性 | 9.5 | 把“声明 ≠ 事实”作为第一原则，避免了依赖 prompt 自律的伪解法 |
| 架构分层 | 8.8 | L0/L1/L2 分界清楚，能覆盖需求、结构化数据和代码产物 |
| 工程可落地性 | 8.3 | 能直接转化为 schema validator、cross-phase check、compile gate、coverage gate |
| 抗幻觉强度 | 8.5 | 对 source 虚报、覆盖率虚高、测试伪覆盖有明确治理路径 |
| 可扩展性 | 8.0 | 所有 Phase 都可套用，但需要统一 claim/evidence 抽象避免规则碎片化 |
| 可维护性 | 7.5 | 检查项增长后会分散在多个模块，需中心化注册和失败语义治理 |
| 成本控制 | 8.0 | 多数检查可确定性执行，LLM 只做语义确认或二级判断 |
| 审计可信度 | 7.8 | 仍受 L0 缺失、WARNING 滥用、语义等价难判等问题影响 |

## 4. 对 Qualix 的适配性

Qualix 天然适合三层框架，因为它本身就是 Phase pipeline：

| Phase | 主要职责 | 防幻觉重点 |
| --- | --- | --- |
| Q01 | 需求结构化 | `SE.source`、`verification`、`bound_reqs`、代码反推检测 |
| Q05a | EUT矩阵设计 | `bound_se`、`then_must_be_concrete`、`impl_class ↔ @InjectMocks/import` |
| Q05b | 单测代码生成 | `impl_class` 反查、编译 gate、执行 gate |
| Q06 | 单测覆盖审计 | `COVERED ↔ 断言强度`、`evidence ↔ 行号`、`audit_items` 反向完整、coverage 一致性 |
| Q07 | 代码评审 | 需求链路、调用链、代码证据、严重级别 |

其中 Q01 是真相源，Q05a→Q05b 是设计+可执行产物层，Q06 是对 Q05a/Q05b 的反向审计层。三者形成了当前 Qualix 最关键的防幻觉闭环。

## 5. 当前落地成熟度

### Q01：需求层

已覆盖能力：

- `SE.source ↔ PRD` 行号和上下文交叉验证。
- `verification` 必须具备可执行断言线索。
- `bound_reqs` 防止 SE 游离。
- 代码标识符反推检测，防止从代码倒推出伪需求。
- BR 密度检查，防止过度拆分或压缩需求。

成熟度判断：覆盖面较完整，但 `SE.source` 虚报、代码反推、BR 密度当前更适合作为风险提示，若按源头真相标准，应把 `SE.source` 虚报升级为硬阻断。

### Q05a：EUT 矩阵设计层

已覆盖能力：

- `then_must_be_concrete` 在 schema 层拒绝模糊 then（must 含具体断言方法和预期值）。
- `bound_se` 与 Q01 真实 SE 对齐。
- Step 0.5 三层防御：目标模块文件存在、覆盖全部 SE、记录 git diff、`impl_class` 反查。
- EUT `when/then` 交叉验证场景完整性。
- 并发/幂等/锁相关 SE 要求非占位 EUT。

成熟度判断：Q05a 的防幻觉硬性在设计层（EUT JSON），编译/执行 gate 已移至 Q05b。

### Q05b：单测代码生成层

已覆盖能力：

- `impl_class ↔ @InjectMocks/import` 反查，防止测试代码与被测类对不上。
- 编译 gate（真实 maven/gradle/go 编译）防止测试代码只停留在文档层。
- 测试执行 gate，防止测试通过率伪高。
- 弱断言 gate：high-risk 方法数 ≥ 1 BLOCKED。

成熟度判断：Q05b 是当前三层框架中最硬的一环，把 L1 的 EUT JSON、L2 的测试代码和 L0 的编译器/测试框架连起来，是最接近不可造假的部分。

### Q06：测试审计层

已覆盖能力：

- `COVERED` 判定反查测试方法断言强度。
- `evidence` 行号反查测试代码附近是否有 assert/verify。
- `audit_items` 必须覆盖 Q05a 大多数 EUT，防止漏审导致覆盖率虚高。
- weak assert sidecar 存在时检查是否被 Q06 消费。
- `WRONG_TARGET` 判定反查测试代码，防止随意制造问题。
- coverage gate 自报与 JaCoCo/Istanbul 结果做一致性校验。

成熟度判断：Q06 已从报告审计升级为代码证据审计，但当前不少规则仍是 WARNING。对高风险命中项，应逐步升级为 HARD 或至少进入不可 `--force` 的 gate。

## 6. 架构优点

1. 把幻觉治理从 prompt 问题转成工程验证问题。
2. 将 LLM 输出降级为 claim，天然要求 evidence 支撑。
3. 支持跨 Phase 追溯，能发现下游引用不存在的上游 ID。
4. 能用编译、测试、coverage 等外部系统压实代码类产物。
5. 规则大多可离线、确定性、低成本执行。
6. 易于演进为 Evidence Graph，支撑查询和审计。

## 7. 主要风险

### 7.1 L0 缺失时 fail-open

当 PRD 原文、code_repo、coverage report 或 git diff 缺失时，部分检查会跳过。跳过本身不一定错误，但必须明确区分：

- `NOT_APPLICABLE`：确实不适用。
- `MISSING_EVIDENCE`：应有证据但缺失。
- `INFRA_FAILURE`：基础设施失败。
- `BLOCKED`：证据链断裂，必须修复。

### 7.2 WARNING 吞掉 P0 问题

`SE.source` 虚报、COVERED 无真实断言、coverage 自报偏差，本质上都是证据链断裂。若仅作为 WARNING，容易被流程推进掩盖。

### 7.3 语义等价难以纯规则判断

行号附近包含关键词，不等于语义完全一致。后续需要 semantic entailment 校验，或在规则命中后使用 LLM 做二级确认，但二级确认结果也必须有 evidence。

### 7.4 规则碎片化

当前规则分散在 schema、auto_checks、q05_structure_checks、q06_structure_checks、cross_phase_check、guardrail 等位置。随着规则增长，需要统一注册和统一失败语义，否则维护成本会快速上升。

### 7.5 编译不是业务真相

编译只能证明语法、类名、方法和包路径真实；测试运行只能证明测试通过。它不能证明断言是否测对了业务结果，因此 Q06 的断言强度和期望值来源审计仍然必要。

## 8. 架构升级建议

建议将三层框架沉淀为统一的 `claim / evidence / verifier / gate` 架构：

| 概念 | 说明 |
| --- | --- |
| Claim | LLM 或工具产出的可验证声明，如 SE、EUT、COVERED、coverage rate |
| Evidence | 支撑声明的外部证据，如 PRD 行号、代码位置、测试方法、coverage report hash |
| Verifier | 对 claim 和 evidence 做确定性或半确定性验证的组件 |
| Gate | 将 verifier 结果收敛为 HARD/SOFT/INFO/NOT_APPLICABLE/INFRA_FAILURE 的决策层 |

最小实现目标：

```text
Claim(SE-001)
  source: plain_text.txt:79
  evidence_hash: ...
  verification: assert HTTP 409 + errorCode=DUPLICATE_SUBMIT
  downstream:
    EUT-003
    TestClass#testDuplicateSubmit
    AUDIT-003
```

这样 Qualix 就能从“很多防幻觉检查”升级为“系统性事实验证引擎”。

## 9. 推荐优先级

| 优先级 | 事项 | 目标 |
| --- | --- | --- |
| P0 | 统一失败语义 | 消除 `FAIL:` / `WARNING:` / `BLOCKED:` 字符串前缀散落表达严重性的歧义 |
| P0 | Q01 `SE.source` 虚报硬阻断 | 源头真相断裂不可进入下游 |
| P0 | coverage report 缺失 fail-closed | 有 code_repo/Q05a 测试时，Q06 缺 coverage evidence 不应静默通过 |
| P1 | Claim Registry | 所有核心声明统一登记，可查询、可追溯 |
| P1 | Evidence Contract | 每类 claim 明确必须的 evidence 类型和最低强度 |
| P1 | Verifier Registry | 规则插件化，避免散落在各 Phase 函数中 |
| P1 | Evidence Graph | 支持从 SE 查到 EUT、测试代码、审计项、代码评审发现 |

## 10. 最终判断

三层防幻觉框架架构合理、方向正确、可落地性强。它比单纯增加 Judge 更高级，因为它把幻觉治理变成了 claim verification problem。

当前 Qualix 已经完成从原则到工程骨架的关键跨越，尤其 Q05a 已接近不可造假。下一阶段的重点是统一抽象和统一 gate 语义，让所有检查从散点规则变成一张可审计、可演进、可查询的事实验证网络。
