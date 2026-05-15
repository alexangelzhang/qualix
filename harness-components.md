# Harness 组件总览

> 共 26 个组件，按作用范围排序：全局 → Q01 → Q04 → Q05 → Q06 → Q07。
> 多 Phase 组件（如 blast_radius 覆盖 Q05/Q06）归入首个 Phase 分组。

---

## 全局组件（13 个）

| 组件名称 | 流程节点 | 能力说明 | 解决的问题 | 目标/收益 |
|---|---|---|---|---|
| phase_contract | Execute handler | 根据 Phase spec 生成执行合同，锁定字段约束、hard_checks 和依赖关系 | AI 凭记忆执行导致契约漂移；字段必填/取值约束被遗忘 | 每次执行前从代码实时导出契约事实，规则不被绕过 |
| review_chain | Finalize handler | 生成 Judge rubric 和 Critique prompt，构建完整 review 调用链 | 手动组装 Judge prompt 容易遗漏关键维度；不同 Phase rubric 缺乏一致性 | 标准化 Judge 评审入口，确保 rubric 与 Phase spec 同步 |
| verification_bundle | Finalize handler | 收集 Worker 输出、schema 校验结果、judge 评分，打包为统一验证包 | finalize 阶段各路校验结果分散，门禁难以统一判断 | 为 completion_gate 和人工审查提供单一可信数据源 |
| overcorrection_guard | Quality | 检测 Judge 是否存在过严误报（低分但产物实际合格） | Judge 模型在某些维度系统性打低分，误触无效循环修正 | 保护 Worker 不被无效 Critique 反复修改；减少误判 token 浪费 |
| skill_factory | Finalize handler | 分析 bug case 库，生成 Anti-Rationalization 借口 + Rebuttal 规则对 | AI 重复犯同类错误；历史失败案例无法自动转化为约束 | 将 2000+ 条失败经验结构化为下次执行的规则补充建议 |
| skill_evolution | Finalize handler | 对比新建议与现有 SKILL.md，生成去重 diff；置信度达阈值自动合并 | skill 文件靠人工维护更新滞后；新规则可能与已有规则重复 | 使 Skill 文件随失败案例积累自动进化，减少人工维护成本 |
| score_calibration | Finalize handler | 用 DeepEval 框架对 Judge 评分进行校准，校正系统性偏差 | 不同模型 Judge 分数量纲不一致；raw score 缺乏可比性 | 输出标准化评分，使跨项目、跨模型的质量基线具有可比性 |
| eval_baseline | Finalize handler | 量化本次执行的质量基线（各维度分数、通过率、迭代次数等） | 缺乏历史对比时难以判断当前质量是进步还是退步 | 积累项目级质量趋势数据，支撑模型升级/组件消融的 A/B 决策 |
| golden_sample | Finalize handler | 将当前产物与预设 Golden Sample 做结构和内容对比 | Judge 是主观评估，不同跑次结果飘移；缺乏客观锚点 | 提供基于参考答案的客观校验层，检测产出相对黄金标准的偏差 |
| rule_compliance | Finalize handler | 统计 SKILL.md 中规则的实际执行率（命中次数 / 应命中次数） | 无法知道哪些规则真正在约束 Worker，哪些形同虚设 | 识别低执行率规则（候选消融）和高失效规则（需强化或重写） |
| reasoning_log | Finalize gate | 检查推理日志（`_reasoning.json`）是否存在且非空 | Worker 可能输出结果但跳过推理步骤，无法追溯决策依据 | 硬性保证每次 finalize 都留有可审查的推理轨迹 |
| no_regression | Finalize gate | 对比本次与上次 approved 产物数量，检测回退 | 重跑或修复时意外删除产物；产物静默减少但门禁未拦截 | 防止在修复局部问题时无意丢失已通过的产物 |
| auto_checks | Finalize gate | 运行 AutoHarness 自动校验套件（schema 完整性、字段格式、跨 Phase 一致性） | 人工核对产物 schema 遗漏率高；跨 Phase 字段不一致难以手动发现 | 用代码级检查代替人眼核对，作为 completion_gate 最后一道机械屏障 |

---

## Q01 组件（2 个）

| 组件名称 | 流程节点 | 能力说明 | 解决的问题 | 目标/收益 |
|---|---|---|---|---|
| requirement_smell | Execute handler | 检测需求文档中的 smell（二义性、缺失验收条件、矛盾约束等） | Q01 提炼 SE 之前缺乏需求质量把关，垃圾进垃圾出 | 提前识别需求缺陷，避免将模糊需求传播到后续所有 Phase |
| requirement_graph | Finalize handler | 构建需求层级图并检测 GAP（孤立节点、断层、循环依赖） | SE 列表扁平化，无法反映需求层次结构和覆盖完整性 | Q01 产物附带层级完整性报告，使审查者快速定位遗漏域 |

---

## Q04 组件（1 个）

| 组件名称 | 流程节点 | 能力说明 | 解决的问题 | 目标/收益 |
|---|---|---|---|---|
| coverage_matrix | Execute handler | 自动生成 SE×Test 覆盖度矩阵 | 手动维护覆盖矩阵耗时且易漏；Q04 审计缺乏结构化输入 | 为 Q04 提供可机读的覆盖度起点，减少 LLM 自由发挥 |

---

## Q05 组件（4 个）

> blast_radius、data_patterns、se_code_mapping 同时作用于 Q05/Q06（或更多），归入首个 Phase。

| 组件名称 | 流程节点 | 能力说明 | 解决的问题 | 目标/收益 |
|---|---|---|---|---|
| blast_radius | Execute handler（Q05/Q06） | 分析代码改动影响范围，计算 risk_tier（LOW/MEDIUM/HIGH/CRITICAL） | 不同风险的改动用同等审计深度，高风险改动被轻放过 | 驱动 ACT depth 动态调整 max_iterations；高风险多跑 |
| data_patterns | Execute handler（Q05/Q06） | 从 2000+ 条历史 bug case 提取高频故障数据模式注入 Worker | Worker 不知道哪些数据边界是真实线上踩过的坑 | 把历史故障经验转化为当次执行的先验约束，提升 FN 召回率 |
| se_code_mapping | Execute handler（Q05/Q06/Q07） | 自动建立 SE（语义期望）→ 代码实现的映射关系 | SE 是需求语言，代码是实现语言，LLM 需显式映射才能精准审计 | 消除 SE 粒度和代码粒度的语义鸿沟，使覆盖判定有据可查 |
| compile_check | Finalize gate | 对 Q05 生成的 Java 测试代码执行实际编译验证 | 生成语法正确但无法编译的代码是 Q05 的高频失败模式 | 编译通过作为 finalize 硬门禁，不可人工绕过 |

---

## Q06 组件（5 个）

> diff_context 同时作用于 Q06/Q07，归入首个 Phase。

| 组件名称 | 流程节点 | 能力说明 | 解决的问题 | 目标/收益 |
|---|---|---|---|---|
| diff_context | Execute handler（Q06/Q07） | 提取 Git diff，构造增量上下文注入 Worker | Worker 不知道本次改动范围，审计全量代码而非变更集 | 聚焦改动边界，减少无关噪音，提升 Q06/Q07 审计精准度 |
| weak_assert | Execute handler | 用 tree-sitter 静态分析检测弱断言（assertTrue(true)、非常量布尔断言等） | LLM 无法可靠识别编译合法但语义空洞的测试断言 | 将弱断言检测从软约束变硬证据，提前暴露骨架测试 |
| business_mutations | Execute handler | 注入业务域变异规则（金额边界、状态非法跳转、幂等场景等） | 通用测试充分性评估缺失业务语义；只测"有没有"不测"对不对" | 让 Q06 审计知晓业务特有的等价类和边界，识别遗漏变异 |
| coverage_gate | Finalize gate | 计算实际测试覆盖率，与项目配置的最低阈值比较 | 覆盖率门禁靠人工审查不可靠；Q06 可能通过 Judge 但未达覆盖线 | 覆盖率不达标则 finalize 阻断，强制补充覆盖后才能 approve |
| blast_radius（兼） | ← 见 Q05 分组 | — | — | — |

---

## Q07 组件（2 个）

| 组件名称 | 流程节点 | 能力说明 | 解决的问题 | 目标/收益 |
|---|---|---|---|---|
| code_skeleton | Execute handler | 用 TREEFRAG 算法压缩代码骨架（保留签名/分支，省略实现细节） | Q07 代码量大导致 context 溢出；全量代码 token 成本过高 | 不丢结构信息的前提下大幅降低 Q07 token 消耗 |
| demand_trace | Execute handler | 从需求描述反向追踪代码执行路径 | Q07 单测生成缺乏需求驱动视角，产出技术细节测试而非业务验证 | 以需求为锚点生成测试，确保覆盖真实业务路径 |
