# Q05 三步生成范式（T6）

与 `SKILL.md` 主流程对齐：**先分支与后果，再写 EUT 与代码**，避免「一 SE 一条 happy path」导致 no-exception-test 漏网。

## Step A — 分支清单（机器可读）

在写入测试代码前，输出到 **`Q05/_internal/_q05_branch_inventory.json`**（finalize 时由 `q05_branch_coverage` Guardrail 消费）。

```json
{
  "targets": [
    {
      "repo": "car-mrs",
      "class_name": "RightsDistributionProviderImpl",
      "method_name": "findRightsDistributionList",
      "branches": [
        {"id": "B-001", "kind": "happy", "description": "正常分页查询"},
        {"id": "B-002", "kind": "exception", "description": "下游 Service 抛 BizException"},
        {"id": "B-003", "kind": "boundary", "description": "pageNum 为 null 走默认页"}
      ]
    }
  ]
}
```

- `kind` 建议取值: `happy` | `boundary` | `exception` | `concurrency` | `defense`。
- 含 **`exception` / `throws` / `error` / `catch`** 的分支会触发 Guardrail：至少一条 `route_type=Exception` 的 EUT。

## Step B — 业务后果映射

输出 **`Q05/_internal/_q05_business_outcomes.json`**，每条分支对应可验证后果（供 `then` 引用）：

```json
{
  "outcomes": [
    {"outcome_id": "O-001", "branch_id": "B-001", "expected": "返回列表非空且元素 status=ACTIVE"},
    {"outcome_id": "O-002", "branch_id": "B-002", "expected": "抛出 BizException，code=ORDER_NOT_FOUND"}
  ]
}
```

## Step C — EUT 与断言

- `eut_items[].then` **必须**引用 `outcome_id`（例如在 `then` 首行写 `outcome_id: O-002`），并与 Step B 的 `expected` 语义一致。
- 异常分支优先使用 `route_type: "Exception"`。
