# 错误恢复协议（Error Recovery Protocol）

> 当任何 Phase 执行出现意外结果时，必须遵循此协议。
> 适用于：Phase 产出异常、finalize 被 BLOCKED、Judge 评分过低、编译失败、覆盖率不达标。

## Stop-the-Line 规则

当出现以下任一情况时，**立即停止当前工作**：

1. finalize 返回 BLOCKED 错误
2. Judge 评分 < 2.0（严重不合格）
3. 编译检查失败（compile_check BLOCKED）
4. 覆盖率门禁失败（coverage_gate BLOCKED）
5. 产物数量回退（REGRESSION 警告）
6. 结构化 JSON 无法通过 schema 校验

**停止后的行为**：
- 不要继续执行下一个 Step
- 不要尝试"快速修一下"然后继续
- 不要删除或重置产物
- 保留当前所有文件作为证据

## Triage 五步法

### Step 1: Reproduce（复现）

确认问题是否可稳定复现：

1. 重新运行 `dqg-run <project> finalize <phase>` 确认错误仍然存在
2. 记录完整的错误信息到 `_reasoning_log.md`
3. 如果不可复现，进入**不可复现决策树**：

**不可复现 Bug 四分支决策树：**

| 类型 | 识别信号 | 诊断方法 |
|------|---------|---------|
| 时序依赖 | 偶发、与执行速度相关 | 添加时间戳日志，人工插入延迟复现 |
| 环境依赖 | 换机器/换 context 后消失 | 对比环境变量、模型版本、上下文大小 |
| 状态依赖 | 首次执行正常，重跑失败 | 检查 SQLite 残留数据、缓存污染、`_prev_counts.json` |
| 随机性 | 无规律 | 添加防御性日志，设置告警，连续跑 3 次取多数结果 |

### Step 2: Localize（定位）

缩小问题范围：

| 错误类型 | 定位方向 |
|---------|---------|
| BLOCKED: _reasoning_log.md 不存在 | 检查是否跳过了推理日志输出 |
| BLOCKED: 编译失败 | 读取 compile_check 的 error_summary，定位具体文件和行号 |
| BLOCKED: 覆盖率不达标 | 读取 coverage_gate 的 line/branch 数据，找到未覆盖的模块 |
| REGRESSION: 产物数量减少 | 对比 `_prev_counts.json`，找到减少的字段 |
| Judge 评分低 | 读取 `_judge_result.json` 的 issues 列表，按 severity 排序 |
| Schema 校验失败 | 读取 validation_errors，逐条修复 |
| 回归问题（之前通过现在失败） | 使用 `git bisect` 定位引入提交（见下方） |

**Bisection 定位法（回归问题专用）：**

当问题是"之前通过，现在失败"时：
1. 确认最后一次通过的 commit（`git log` 找到上次 approve 的时间点）
2. 使用 `git bisect start HEAD <last_good_commit>` 开始二分
3. 每次 bisect 步骤运行 `dqg-run <project> finalize <phase>` 判断 good/bad
4. 定位到引入问题的具体 commit 后，分析该 commit 的改动

### Step 3: Reduce（简化）

找到最小复现条件：

1. 如果是多个错误，先修最严重的（BLOCKED > REGRESSION > WARNING）
2. 如果是 Judge 评分低，找到扣分最多的维度，只修那个维度
3. 如果是编译失败，先修第一个编译错误（后续错误可能是级联的）

### Step 4: Fix Root Cause（修根因）

修复时的纪律：

- **只修问题本身**，不顺手改其他东西
- **在旧版基线上增量修改**，不从零重写
- **每次修复后重新运行 finalize**，确认问题已解决
- **记录修复过程到 `_reasoning_log.md`**

### Step 5: Guard（防护）

修复后防止复发：

1. 如果是 skill 规则不够明确导致的问题 → 更新 skill 的 Anti-Rationalization 表
2. 如果是 schema 不够严格导致的问题 → 更新 schemas/ 下的校验规则
3. 如果是反复出现的模式 → 生成 bug case 存入 `regression/failure-library/cases/`
4. 如果是 finalize gate 没有拦住的问题 → 考虑新增 finalize_checks gate

## Anti-Rationalization

| 常见借口 | 为什么不能接受 | 正确做法 |
|---------|--------------|---------|
| "我知道问题在哪，直接改就行" | 70% 的时候你是对的，30% 会浪费更多时间 | 先复现，再定位 |
| "这个测试可能是错的" | 先验证这个假设，不要直接跳过 | 读测试代码确认 |
| "重新跑一次可能就好了" | 不可复现的问题更危险，不是更安全 | 记录环境信息，分析原因 |
| "先跳过这个错误继续" | 错误会累积，后面的 Phase 基于错误的产物工作 | Stop-the-Line，先修再继续 |
| "从零重写比修复快" | 重写会丢失旧版的正确部分，且 REGRESSION gate 会拦截 | 在旧版基线上增量修改 |
