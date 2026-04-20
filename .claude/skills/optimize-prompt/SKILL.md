---
name: optimize-prompt
description: 基于失败案例自动分析并优化 prompt，支持 GEPA 式迭代优化循环（seed + evaluator + objective）。适用于 RAG、Skill、任何 LLM 任务。
triggers:
  - /optimize-prompt
  - 优化 prompt
  - prompt 调优
  - 知识库准确率低
---

# Prompt 优化器

IRON LAW: 优化前后必须有可量化的对比数据。NEVER 凭感觉声称"优化了"，没有 baseline 数据不开始改 prompt。

给定当前 prompt 和失败案例，分析失败原因，提出改进版本，用 DeepEval（RAG 场景）或 Claude 自评（通用场景）打分，输出最优结果。

## 优化模式

### 模式 A：单轮优化（默认）
适用于快速改进，生成 3 个变体对比选最优。

### 模式 B：GEPA 式迭代优化
适用于需要持续改进的场景。基于 GEPA (arXiv:2507.19457) 的 Reflective Mutation 循环：

```
seed_candidate（当前 prompt）
  → evaluate（在测试集上跑分）
  → reflect（LLM 读执行轨迹，诊断 WHY 失败）
  → mutate（基于诊断生成定向修改）
  → evaluate（验证修改是否有效）
  → 重复直到满意或预算耗尽
```

**何时用模式 B：**
- 有 10+ 个测试样本
- 单轮优化后仍有明显失败模式
- 用户明确要求"持续优化"或"迭代优化"

**模式 B 执行流程：**

1. **定义三元组**：
   - `seed`：当前 prompt 文本
   - `evaluator`：评估方法（DeepEval / Claude 自评 / 自定义脚本）
   - `objective`：优化目标（如"提高准确率同时保持回答简洁"）

2. **迭代循环**（最多 3 轮）：
   - 每轮在测试集上评估当前最优 prompt
   - 收集 ASI（Actionable Side Information）：不只是分数，还有每个失败 case 的具体错误信息、推理过程、偏差类型
   - LLM 读 ASI 后生成 1-2 个定向修改版本（不是随机变异，是基于诊断的修复）
   - 评估修改版本，如果改进则接受，否则回退

3. **Pareto 保留**：
   - 如果不同版本在不同类型的测试样本上各有优势，保留多个版本
   - 输出时标注每个版本的适用场景

4. **终止条件**：
   - 达到目标分数
   - 连续 2 轮无改进
   - 预算耗尽（3 轮）

## 判断模式

**RAG 知识库场景**（满足以下任一条件）：
- 优化目标涉及检索 + 生成（有 retrieval_context）
- 用户提到"知识库准确率"、"RAG"、"检索"

→ 使用 **DeepEval 模式**，安装并运行 deepeval 评测脚本

**通用场景**（Skill prompt、任务 prompt 等）：
→ 使用 **Claude 自评模式**，无需额外依赖

---

## DeepEval 模式（RAG 场景）

### 前置准备

```bash
pip install -U deepeval
export OPENAI_API_KEY=<your-key>  # deepeval 默认用 gpt-4.1 作为 judge
# 如果用 Claude 作为 judge：
export ANTHROPIC_API_KEY=<your-key>
```

### 输入要求

1. **测试样本**：每条包含 `input`（用户问题）、`actual_output`（RAG 回答）、`retrieval_context`（检索到的文档列表）、`expected_output`（期望答案，可选）
2. **失败案例**：至少 5 条答错的样本
3. **当前 prompt**：待优化的 answer prompt 或 query rewrite prompt

### Step 1：生成 DeepEval 评测脚本

根据用户提供的样本，生成如下评测脚本 `eval_baseline.py`：

```python
from deepeval import evaluate
from deepeval.test_case import LLMTestCase
from deepeval.metrics import (
    AnswerRelevancyMetric,
    FaithfulnessMetric,
    ContextualRecallMetric,
    ContextualPrecisionMetric,
)

# 测试样本（从用户提供的失败案例填充）
test_cases = [
    LLMTestCase(
        input="<用户问题>",
        actual_output="<RAG 实际回答>",
        retrieval_context=["<检索到的文档1>", "<检索到的文档2>"],
        expected_output="<期望答案>",  # 有则填，没有可省略
    ),
    # ... 更多 case
]

metrics = [
    AnswerRelevancyMetric(threshold=0.7, include_reason=True),   # 回答是否切题
    FaithfulnessMetric(threshold=0.7, include_reason=True),      # 回答是否忠实于检索内容
    ContextualRecallMetric(threshold=0.7, include_reason=True),  # 检索内容是否覆盖期望答案
    ContextualPrecisionMetric(threshold=0.7, include_reason=True), # 检索内容是否精准
]

results = evaluate(test_cases=test_cases, metrics=metrics)
```

运行：`deepeval test run eval_baseline.py`

### Step 2：解读评测结果，定位失败根因

根据四个指标的得分，判断失败类型：

| 失败模式 | 低分指标 | 根因 | 优化目标 |
|---|---|---|---|
| 检索到了但没用上 | Faithfulness 低 | answer prompt 没有引导模型用检索内容 | 优化 answer prompt |
| 检索内容不够全 | ContextualRecall 低 | query rewrite 不够准确 | 优化 query rewrite prompt |
| 检索内容不精准 | ContextualPrecision 低 | 检索策略问题，或 query 太宽泛 | 优化 query rewrite prompt |
| 回答跑题 | AnswerRelevancy 低 | answer prompt 约束不足 | 优化 answer prompt |

### Step 3：生成 3 个改进版本并评测

针对 Step 2 定位的根因，生成 3 个改进版 prompt，分别生成对应的 `eval_vA.py` / `eval_vB.py` / `eval_vC.py`，替换 `actual_output`（用新 prompt 重新跑 RAG 得到的输出）后运行评测。

对比结果：

```
| 版本   | AnswerRelevancy | Faithfulness | ContextualRecall | ContextualPrecision |
|--------|----------------|--------------|-----------------|---------------------|
| 原始   | xx%            | xx%          | xx%             | xx%                 |
| A      | xx%            | xx%          | xx%             | xx%                 |
| B      | xx%            | xx%          | xx%             | xx%                 |
| C      | xx%            | xx%          | xx%             | xx%                 |
```

### Step 4：输出最优版本 + 飞轮建议

1. **推荐版本**及完整 prompt 文本
2. **改进理由**：哪个指标提升了、为什么
3. **新增 eval case 建议**：本轮仍答错的 case 加入 eval suite，下轮继续优化
4. **飞轮操作**：将本轮失败 case 追加到 `eval_suite.py`，作为持续回归基线

---

## Claude 自评模式（通用场景）

### 输入要求

1. **当前 prompt**：待优化的 prompt 文本
2. **测试样本**：10-20 个 `(输入, 期望输出)` 对
3. **失败案例**：至少 5 个答错的样本
4. **评估标准**：什么算"答对"

### Step 1：失败模式分析

逐一分析失败案例，归纳共同模式：
- 为什么失败？（缺少上下文 / 指令歧义 / 格式问题 / 知识缺失）

输出：失败原因分类统计

### Step 2：生成 3 个改进版本

- **版本 A**：针对最主要失败原因做最小改动
- **版本 B**：增加上下文约束和输出格式要求
- **版本 C**：重构 prompt 结构（改变指令顺序、增加 few-shot）

### Step 3：对比评测

```
| 版本 | 正确数/总数 | 准确率 | 主要改进点 |
|------|-----------|--------|-----------|
| 原始 | x/20      | xx%    | baseline  |
| A    | x/20      | xx%    | ...       |
| B    | x/20      | xx%    | ...       |
| C    | x/20      | xx%    | ...       |
```

### Step 4：输出最优版本

1. 推荐版本及完整 prompt
2. 改进理由
3. 已知局限
4. 下一步建议

---

## 约束

- 不要在没有测试数据的情况下凭感觉改 prompt
- 每个改进版本必须有明确的改进假设
- 不要一次改太多变量，每个版本只针对一个主要问题
- 测试样本少于 5 个时，明确告知结论可信度有限
- RAG 场景优先用 DeepEval，不要用 Claude 自评替代（自评结果不可重复）
- 每轮优化后，将失败 case 追加到 eval suite，不要丢弃
