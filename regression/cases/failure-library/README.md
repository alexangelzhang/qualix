# Failure Library

失败样例库用于沉淀已经发生过的误报、漏报、边界输入和弱文档输入问题，并要求后续规则改动必须回归通过。

目录约定：

```text
regression/cases/failure-library/<case-id>/
├── case.json
└── expected/
    └── ...
```

`case.json` 最小字段：

- `case_id`
- `library`: 固定为 `failure-library`
- `error_type`: `误报` / `漏报` / `边界输入` / `弱文档输入`
- `case_kind`
- `trigger_condition`
- `fix_strategy`
- `regression_case`
- `actual_dir`
- `include`

建议：

- 每个 case 只覆盖一种失败模式
- `trigger_condition` 描述触发前提
- `fix_strategy` 描述当时采取的修复策略
- `regression_case` 记录后续回归名称，方便和规则改动关联
