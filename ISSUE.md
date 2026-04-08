# ISSUE.md — 变更记录

## 2026-04-02

### 新增能力

- **LLM-as-Judge 自动评审** — `finalize` 后自动生成 `_judge_prompt.md`，支持 Phase A/A.5/A.6/C 四个阶段的独立评审，输出 precision/recall 估计和问题列表。CLI: `dqg-run <project> judge <phase>`
- **Self-Critique + RLAIF 融合闭环** — Phase 执行后自我批评生成 v2，偏好比较判定哪个更好，有效 critique 自动沉淀为 bug case。CLI: `dqg-run <project> critique <phase>` / `dqg-run <project> preference <phase>`
- **Bug 案例库** — 按 Phase 分类的结构化案例库（case.json + input.md），支持归因（SKILL_RULE/KNOWLEDGE/CONTEXT/SCHEMA）和修复路径建议。CLI: `python -m dqg.bug_cases`
- **案例自动注入** — skill 执行时基于上游产物内容做相关性匹配，只注入相关案例为反例，token 节省 77%
- **案例批量导入** — 从飞书 Bitable 批量导入 bug 案例。CLI: `python -m dqg.import_bug_cases <ingest.json>`
- **飞书多维表格（Bitable）解析** — Wiki 节点 obj_type=bitable 时自动走 bitable 路径，遍历所有 sheet 读取全量记录
- **多平台支持** — 新增 `AGENTS.md`（Codex/opencode/IntelliJ）、`GEMINI.md`（Gemini CLI）、`.cursor/rules/dqg.mdc`（Cursor）
- **规则级质量追踪** — `finalize` 时比对结构化输出与 bug 案例库，输出健康度分数和命中的已知问题模式
- **自动修复闭环** — `finalize` 发现 validation errors 时自动生成 bug case 并建议 prompt 修改

### 优化

- **目录结构重构** — 输出路径从 `output/{id}_phaseA/` 改为 `output/{id}/phaseA/`，state.json 移入项目子目录。涉及 12 个源文件 + 5 个测试文件 + 3 个 skill 文档
- **飞书图片并发下载** — ThreadPoolExecutor 8 workers，预计提速 5-8x
- **飞书引用文档并发抓取** — 同层级文档 4 workers 并发，根文档串行
- **飞书单文档 API 并发** — get_meta + get_content + fetch_raw_content 三个请求并发
- **异常矩阵扩展** — `references/risk-and-exception-catalog.md` 从 38 行扩展到 364 行，每个风险/异常类型补充了 Java DDD+TMF 场景的触发条件、代码信号、判定规则
- **测试覆盖** — 从 85 个用例增加到 129 个

### 修复

- **飞书权限错误诊断** — Wiki 节点解析失败时给出具体排查步骤（区分 403/401/空响应），`call_with_token_fallback` 增加 user_access_token_not_supported 快速跳过
- **state.json 写入失败** — `save_state` 改为 `path.parent.mkdir(parents=True)` 确保项目子目录存在
- **regression case 路径** — `rights-platform` 的 case.json include 路径未更新为新目录结构（待更新）

## 2026-04-01

### 新增

- 87 条真实 bug 案例从飞书 Bitable 导入（Phase C: 56, Phase A: 22, Phase A.6: 6, Phase A.5: 1）
- 4 条手动创建的示例案例（并发幂等、覆盖度错判、RPC 无补偿、弱断言）
