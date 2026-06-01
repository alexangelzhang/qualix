# 变异测试规则

> 本规则为 Phase Q06 Step 7.5 的详细设计背景。
> 工具配置与变异算子（Java 项目）详见：`references/java-ddd-tmf-baseline.md` 第 8 节。

## 双引擎架构

### C.1 — 静态极速扫描（已由 Step 1-7 覆盖）

- 分层注入合规性、弱断言检测、JaCoCo 覆盖率门禁
- 秒级反馈，拦截"空气单测"
- 若存在 `_weak_assert_context.md`，必须把其中命中的测试方法并入静态极速扫描结果，作为 `WRONG_TARGET` 候选证据来源之一

### C.2 — 动态变异猎杀（Step 7.5）

**执行流程：**

1. **增量变异生成**：仅针对本次 git diff 修改的目标类生成变异体（如 PITest 的 `scmMutationCoverage`），将执行时间控制在秒到分钟级
2. **定向运行**：只运行与改动范围相关的、带 EUT 标签的 `@Test` 用例
3. **存活变异体分析**：
   - 变异体存活（Mutation Survived）= 代码被篡改后单测仍通过 = 单测伪覆盖
   - 对每个存活变异体，比对 Phase Q01 的 `REQ/BR/SE` 契约：
     - 若被篡改代码行承载关键业务语义（SE 关联）→ 标记 `MUTATION_SURVIVED_CRITICAL`，必须补强断言
     - 若被篡改代码行不承载契约语义（日志、无关返回值）→ 标记 `MUTATION_SURVIVED_EXEMPT`，允许豁免

## 门禁规则

- 变异杀伤率（Mutation Score）门槛：T1 核心路径 >= 80%，T2 重要路径 >= 60%
- 存在 `MUTATION_SURVIVED_CRITICAL` 且未补强断言 → 判 `FAIL`

## 反馈闭环

存活变异体报告传导回 Phase Q05a，AI 拿着"罪证"指出具体的 EUT 漏测点和需要补强的断言方向。

## 变异测试结果输出格式

```
### 变异测试结果

- 工具：PITest / 其他
- 运行状态：PASS / FAIL
- 变异杀伤率：<x>%
- 存活变异体总数：<n>

| 变异体 ID  | 目标类:行号 | 变异类型                | 关联 SE  | 存活分类            | 补强方向 |
| ------- | ------ | ------------------- | ------ | --------------- | ---- |
| MUT-001 |        | 条件翻转/返回值篡改/方法删除/... | SE-xxx | CRITICAL/EXEMPT |      |
```
