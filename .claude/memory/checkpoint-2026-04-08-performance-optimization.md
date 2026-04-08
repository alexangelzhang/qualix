---
date: 2026-04-08
session_topic: DQG 性能与证据链优化收口
project: dev-quality-gate
status: completed
---

## 架构发现
- Phase 执行链上的主要 token 浪费点已经从“全文拼 prompt”转到“证据包构建、相关性匹配和重复 LLM 调用”三类热点。
- `Agent.query_cache` 已具备可复用能力，接入 `adaptive_loop` 后能直接覆盖 Worker/Judge/Fixer/Critique 的重复调用场景。
- FTS5 中文检索质量会直接影响 evidence pack 和 bug case relevance 的上下文质量，因此需要统一中文分词、identifier subtoken 和 MATCH query builder。
- Phase C 的 weak assert 问题仅靠 LLM 后置审计容易漏判，前置 sidecar 比在 prompt 中临时解释更稳定。

## 关键决策
- retrieval-first evidence pack 作为默认上下文装配方式，固定输出 Pack 概览 + 证据摘要 + 关键引用，不再把 PRD/报告全文直接塞给 LLM。
- 应用层 LLM result cache 统一收口到 `Agent.query_cache`，命中键由模型、角色、上下文版本共同决定，避免重复 Judge/Critique/Fixer 调用。
- FTS5 检索统一走 `text_utils` 中的中文分词、query builder 和 signal 检查，减少中文单字误命中与各缓存层行为漂移。
- weak assert 检测作为 Phase C `execute` 的 sidecar 前置产物，交给 skill 优先读取，而不是等审计 prompt 自由发挥。
- `CLAUDE.md` / `AGENTS.md` 的 `Claude-Reflect Learnings` 视为生成产物，后续补充 learnings 应先更新 `.claude/memory/`，不能直接手改 auto-generated 区块。

## 已完成
- `adaptive_loop` 已复用 `Agent.query_cache`，重复 Worker/Judge/Fixer/Critique 路径可直接命中缓存。
- retrieval-first evidence pack 已在 `load_context()` 收口，`_upstream_context.md` 输出固定 schema。
- FTS5 中文检索已升级为边界感知分词 + identifier subtoken，统一覆盖 fact/text/image/code。
- Phase C `execute` 已产出 `_internal/_weak_assert_context.{json,md}`，供单测审计优先读取。
- `CLAUDE.md` / `AGENTS.md` 的手工维护内容已移回手工区或 `.claude/memory/` 源文件，避免继续污染 auto-generated 区块。

## 后续关注
- 如需刷新 `CLAUDE.md` / `AGENTS.md` 的 `Claude-Reflect Learnings` 展示，需要走 claude-reflect 的生成流程，而不是继续手改目标文件。
- README 中 bug case 数量、测试用例数量等静态数字可能已经过时，后续若要继续收口文档，可单独做一轮事实校对。
