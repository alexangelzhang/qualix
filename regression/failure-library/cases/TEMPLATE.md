# Bug 案例录入模板

每个案例一个目录，包含两个文件：

## case.json — 结构化元数据

```json
{
  "case_id": "FN-phaseA-001",
  "phase": "A",
  "error_type": "FN",
  "severity": "high",
  "title": "一句话描述 bug",
  "root_cause": "SKILL_RULE",
  "fix_target": "skills/requirement-structuring.md",
  "tags": ["并发", "幂等"],
  "created_at": "2026-04-02",
  "status": "open",
  "expected": {
    "item_type": "GAP",
    "item_id": "GAP-xxx",
    "content": "正确答案的关键内容"
  },
  "actual": {
    "item_type": null,
    "content": "skill 实际输出（或未输出）"
  },
  "lesson": "一句话可执行教训（与 Signs 二选一必填；批量补齐见 scripts/backfill_failure_case_lessons.py）",
  "case_category": "STRUCTURED_SCHEMA"
}
```

### case_category（五类，可选但推荐）

| 值 | 含义 |
|----|------|
| STRUCTURED_SCHEMA | 缺字段、矩阵不全、Pydantic/schema 校验失败 |
| ENUM_VOCABULARY | severity 等枚举自造词 |
| CROSS_PHASE_IDS | phantom EUT、上下游 ID 漂移 |
| ASSERTION_QUALITY | then 弱断言、断言未对准业务后果 |
| DOC_SKILL_DRIFT | skill 示例与 schema 冲突、prompt 未列必填 |

### 字段说明

| 字段 | 值域 | 说明 |
|------|------|------|
| error_type | FN / FP / WRONG | 漏报 / 误报 / 错判 |
| severity | critical / high / medium / low | 影响程度 |
| root_cause | SKILL_RULE / KNOWLEDGE / CONTEXT / SCHEMA | 归因类型 |
| fix_target | 具体文件路径 | 应该修哪个文件 |
| status | open / fixed / wontfix | 修复状态 |

### root_cause 归因说明

- **SKILL_RULE**: prompt 规则不够明确或缺失 → 修 skills/*.md
- **KNOWLEDGE**: 领域知识不足（异常类型、架构模式等）→ 补 references/*.md 或 profiles/
- **CONTEXT**: 输入信息不足（飞书解析丢内容、图片未识别）→ 修 ingest 或提示用户补充
- **SCHEMA**: 结构化输出丢失信息 → 修 schemas/

## input.md — 触发 bug 的原始输入片段

用 markdown 写，贴 PRD/技术方案/代码的关键片段。不需要完整文档，只需要能复现问题的最小上下文。
