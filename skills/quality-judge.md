---
name: quality-judge
description: "LLM-as-Judge: 独立评审 Phase 输出质量，输出 precision/recall 和问题列表"
trigger: "用户要求评审某个 Phase 的输出质量，或 finalize 后自动触发"
allowed-tools:
  - Read
  - Write
  - Grep
---

# Quality Judge

独立评审 Phase 输出的准确性和完备性。

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
