# 模块 02：意图、范围与语义追踪检查

## 目标

确认“改动是否做对事、做全事、没多做事”，并检查需求语义是否进入可验证链路。

## 输入来源

1. `TODOS.md`（若存在）。
2. `git log <base>..HEAD --oneline` 提交信息。
3. `git diff <base> --stat` 变更文件清单。
4. 需求依据（至少一项）：PRD、评审纪要、验收条目、需求单。
5. （可选）飞书直读结果：
   - `ingest.json / plain_text.txt`
   - `image_semantics.json / image_semantics.md`

## 检查项

1. 提炼 Intent（本分支原始目标，1 行）。
2. 提炼 Delivered（当前改动实际交付，1 行）。
3. 判断范围状态：
   - `DRIFT DETECTED`：出现与目标无关的改动。
   - `REQUIREMENTS MISSING`：目标中的要求未实现。
4. 建立最小需求追踪（不要求完整表格，但必须可检索）：
   - `REQ`：主需求点
   - `BR`：分支需求
   - `SEM`：关键语义（排序/去重/状态迁移/窗口/默认/降级）
5. 语义缺口检查：
   - `SEM_MISSING`：需求或图片中明确语义未进入追踪链路。
   - `TRACE_BROKEN`：`REQ/BR/SEM` 无法定位到代码或测试证据。

## 输出模板

```text
Scope Check: [CLEAN / DRIFT DETECTED / REQUIREMENTS MISSING]
Requirement Trace: [OK / MISSING_CONTEXT / SEM_GAP / TRACE_BROKEN]
Intent: <1-line>
Delivered: <1-line>
REQ/BR/SEM Snapshot:
- REQ-001: ...
- BR-001: ...
- SEM-001: ...
Out-of-scope:
- <item>
Missing:
- <item>
```

## 判定说明

- 缺需求依据：标记 `MISSING_CONTEXT`，最终状态不得直接给 `DONE`。
- 存在 `SEM_GAP` 或 `TRACE_BROKEN`：至少 `DONE_WITH_CONCERNS`。
