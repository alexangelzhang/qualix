# DQG 上下文层级模型（Context Hierarchy）

> 统一的上下文加载策略，所有 Phase 共用。
> 解决上下文规则散落各处、不同 Phase 策略不一致的问题。

## 五级金字塔

从高优先级到低优先级，上层覆盖下层：

```
Level 1: Phase Skill（执行规则）
  ↓
Level 2: Structured Artifacts（结构化产物）
  ↓
Level 3: Evidence Pack（证据包）
  ↓
Level 4: Knowledge Layer（知识层）
  ↓
Level 5: Raw Input（原始输入）
```

### Level 1: Phase Skill（最高优先级）

- 来源：`skills/*.md` + `skills/modules/*.md`
- 持久性：永久（代码仓库）
- 信任级别：Trusted
- 加载时机：execute 开始时
- 行数预算：~500 行（progressive disclosure 按需展开）

### Level 2: Structured Artifacts（结构化产物）

- 来源：上游 Phase 的 `phase_*_structured.json`
- 持久性：项目级（output 目录）
- 信任级别：Trusted（已通过 schema 校验）
- 加载时机：`_upstream_context.md` 构建时
- 行数预算：~1000 行

### Level 3: Evidence Pack（证据包）

- 来源：`_upstream_context.md`（概览 + 摘要 + 关键引用）
- 持久性：Phase 级
- 信任级别：Trusted
- 加载时机：execute 时自动生成
- 行数预算：~2000 行

### Level 4: Knowledge Layer（知识层）

- 来源：`_bug_cases.md` + `_cross_project_insights.md` + `_business_mutations.md`
- 持久性：项目级 / 跨项目
- 信任级别：Verify（案例可能过时，insights 可能不适用）
- 加载时机：execute 时按相关性匹配注入
- 行数预算：~500 行

### Level 5: Raw Input（最低优先级）

- 来源：PRD 原文、飞书文档、代码仓库
- 持久性：外部
- 信任级别：Verify（可能有歧义、可能过时）
- 加载时机：仅在 Level 2-3 不足时回退
- 行数预算：按需，但总量不超过 5000 行

## 信任级别

| 级别 | 含义 | 处理方式 |
|------|------|---------|
| Trusted | 项目源码、已校验的结构化产物、skill 文件 | 直接使用 |
| Verify | 外部文档、知识层注入、历史案例 | 使用前交叉验证 |
| Untrusted | 用户自由输入、第三方 API 返回、错误日志 | 不直接作为结论依据 |

## 行数阈值

| 场景 | 阈值 | 超出时的处理 |
|------|------|------------|
| 单个 Phase 的总上下文 | < 5000 行 | 触发 compact（压缩摘要） |
| 单个文件的注入量 | < 2000 行 | 截断 + 标记 `...(截断)` |
| Bug case 注入 | < 500 行（最多 8 条） | 按相关性排序取 top 8 |
| 跨项目 insights | < 300 行（最多 10 条） | 按 strength 排序取 top 10 |

## 加载顺序规则

1. **不回读原始输入**：有 `_upstream_context.md` 时不读 PRD 原文
2. **不重复注入**：`_upstream_context.md` 已内联 profile/bug_cases/diff 时不再单独注入
3. **图片已预解析**：有 `image_semantics.md` 时不重新读取图片文件
4. **Phase Q01 产物是需求基线**：下游 Phase 只读 `phase_a_structured.json`，不回溯飞书原文
5. **按需加载详细规则**：skill 文件用 `<!-- @include -->` 标记，只在需要时展开

## Anti-Rationalization

| 常见借口 | 为什么不能接受 | 正确做法 |
|---------|--------------|---------|
| "多加点上下文总没坏处" | 研究表明超过 5000 行上下文性能下降 | 按层级加载，聚焦相关内容 |
| "直接读原文更准确" | 原文未经结构化，噪音多 | 优先读结构化产物 |
| "把所有 bug case 都注入" | 不相关的 case 是噪音 | 按相关性匹配取 top 8 |
| "context window 很大，用满它" | window 大小 ≠ 注意力预算 | 聚焦的 2000 行优于散漫的 10000 行 |
