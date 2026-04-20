---
name: quality-judge
description: "LLM-as-Judge: 独立评审 Phase 输出质量，输出 4 维评分、FN/FP 列表和 verdict"
trigger: "用户要求评审某个 Phase 的输出质量，或 finalize 后自动触发"
allowed-tools:
  - Read
  - Write
  - Grep
---

# Quality Judge

独立评审 Phase 输出的准确性和完备性。

## Precision / Recall 定义

- **Precision**（准确率）= 输出中正确的条目数 / 输出总条目数。衡量"说了的是否都对"。FP（误报）降低 precision。
- **Recall**（召回率）= 输出中正确覆盖的条目数 / ground truth 总条目数。衡量"该说的是否都说了"。FN（漏报）降低 recall。

计算方式：
1. 将 Phase 输出的 REQ/BR/SE/GAP/OPEN 逐条与 ground truth（PRD/技术方案/代码）对照
2. 标记每条为 TP（正确）/ FP（多报或错报）/ FN（漏报）
3. `precision = TP / (TP + FP)`，`recall = TP / (TP + FN)`
4. 结果写入 `_judge_result.json` 的 `precision` 和 `recall` 字段

## 使用方式

1. `finalize` 后会自动生成 `_judge_prompt.md` 到 phase 目录
2. 执行评审: 读取 `_judge_prompt.md` 并按其指示完成评审
3. 结果写入 `_judge_result.json`

## 手动触发

```bash
dqg-run <project_id> judge <phase>
```

## 评审原则

1. 你是独立评审员，不是执行者
2. 每个判断必须引用原文证据
3. 漏报（FN）比误报（FP）更严重
4. 对照原始输入逐条验证，不能只看输出自洽性

## 评审流程

1. 读取 `_judge_prompt.md` 获取评审维度和评分标准
2. 读取 Phase 输出文件（report + structured JSON）
3. 读取上游产物（PRD/技术方案/代码）作为 ground truth
4. 逐维度评分，列出具体扣分项
5. 输出结构化 JSON 到 `_judge_result.json`

## 通用评审维度（当 _judge_prompt.md 不存在时使用）

| 维度 | 权重 | 评分标准 |
|------|------|---------|
| 完整性 | 30% | 上游产物的每条 REQ/BR/SE 是否在输出中有对应处理 |
| 准确性 | 30% | 每条结论是否有原文证据支撑，是否存在幻觉 |
| 结构规范 | 20% | 是否包含 skill 定义的所有必须章节，格式是否一致 |
| 自检质量 | 20% | Judge/Critique 是否执行，发现的问题是否已修正 |

## 输出 Schema

```json
{
  "phase": "A/A.5/A.6/B/C/D",
  "score": {
    "completeness": "0-5",
    "accuracy": "0-5",
    "structure": "0-5",
    "self_check": "0-5"
  },
  "total": "0-20",
  "verdict": "PASS / PASS_WITH_RISKS / FAIL",
  "deductions": [
    { "dimension": "...", "issue": "...", "evidence": "...", "points": "-N" }
  ],
  "false_negatives": ["漏掉的 REQ/BR/SE ID 列表"],
  "false_positives": ["错误标记的 ID 列表"]
}
```
