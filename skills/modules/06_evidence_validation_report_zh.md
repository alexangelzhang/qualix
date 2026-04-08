# 模块 06：证据校验与最终报告

## 目标

保证所有结论可追溯，最终输出可用于发布门禁。

## 校验清单

1. 每条问题都要有证据（文件:行号）。
2. 每条“已修复”都要说明修复前后行为。
3. 每条“测试覆盖”都要指出测试文件与用例名。
4. 无法验证的内容必须标注“未验证”。
5. `REQ/BR/SEM` 至少有最小追踪证据（代码与测试至少其一）。
6. 若有图片语义输入，必须说明是否入链路。

## 最终报告格式

```text
Pre-Landing Review Summary
- total_issues: <N>
- critical: <X>
- informational: <Y>
- fixed: <A>
- skipped: <B>
- unverified: <C>
- req_count: <R>
- sem_count: <S>
- trace_broken: <T>
- sem_gap: <G>

Findings:
1) [SEVERITY] <file:line> ...

Requirement Trace Snapshot:
- REQ-001 -> <code/test evidence>
- BR-001 -> <code/test evidence>
- SEM-001 -> <code/test evidence>

Known Risks:
- <risk item>

STATUS: DONE | DONE_WITH_CONCERNS | BLOCKED | NEEDS_CONTEXT
```

## 状态判定建议

- `DONE`：无未修复 Critical，且无关键未验证项，且无 `sem_gap/trace_broken`。
- `DONE_WITH_CONCERNS`：仍有未修复项、未验证项、`sem_gap` 或 `trace_broken`。
- `BLOCKED`：流程被约束阻断。
- `NEEDS_CONTEXT`：缺失必要上下文（尤其是需求依据）。
