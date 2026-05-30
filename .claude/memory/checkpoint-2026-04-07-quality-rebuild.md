---
date: 2026-04-07
session_topic: DQG 质量体系重建 + 记忆层 + Multi-Agent + 代码重构
project: qualix
status: in-progress
---

## 架构发现
- SQLite 统一存储层现在有 35 张表，所有缓存/索引/遥测共用一个 DB，schema 只在首次连接时执行（`_initialized_dbs` 缓存）
- 统一记忆层 `MemoryLayer` 整合了 7 个子系统：事实/图片/文本/代码/知识网络/版本追踪/语义缓存
- Multi-Agent 三阶段架构：prompt 隔离（Phase 1）→ 独立 API + 6 家模型 fallback（Phase 2）→ 自适应循环 + 多 Judge 投票（Phase 3）
- 中文 FTS5 搜索用 n-gram 分词（单字+双字），FTS5 只索引标题+关键词，长文本走 LIKE fallback + 上下文截取

## 关键决策
- **Judge/Critique 移到 finalize 前**：之前是 finalize 后可选执行，形同虚设。现在是提交前强制步骤
- **推理日志 `_reasoning_log.md` 硬性校验**：finalize 时检查存在性和内容量，不存在则 BLOCKED
- **重跑防回退**：`_prev_counts.json` 快照对比，产物数量减少自动告警
- **模型无关 Agent Framework**：不绑定 Claude API，支持 DeepSeek/Qwen/Gemini/Kimi 自动 fallback，解决国内被墙问题
- **代码重构**：6 个模块的 `_ensure_tables` 统一到 `store.py`，`_tokenize_chinese` 移到 `text_utils.py`，`REPORT_MAP`/`STRUCTURED_JSON_MAP` 统一定义

## 问题与解法
- **Phase A 报告质量回退**：重跑时从零重写导致 BR 细节/SE 判定依据/GAP 风险等级全部丢失。解法：skill 规则禁止从零重写 + finalize 防回退检测
- **状态机画错**：把迁移动作当状态节点、驳回循环目标错误、正常/异常路径混淆。解法：skill 加入状态机建模规则 + 5 个 bug case 沉淀
- **研发反馈 6 条**：流程图错误/BR 层级压平/遗漏回调/GAP 过度推断/消息通知细节不足/缺操作流程视角。全部写入 skill 规则和 bug 案例库
- **text_cache FTS5 bug**：`content_tokenized` 列存了 heading 而非实际内容，导致搜索退化为 LIKE。已修复

## 未完成工作
- [ ] `_row_to_dict` 还有 3 处重复（image_cache/text_cache/fact_cache），应改为引用 `text_utils.row_to_dict`
- [ ] `knowledge_network.py` 的 O(n²) 跨项目链接 + N+1 DB 调用未优化（需要批量 insert）
- [ ] `memory_layer.py` 有两处重复的 inline import `PHASE_DEFS`
- [ ] Bug 案例库从 87 条增长到 265 条，但 `CLAUDE.md` 中还写着 87 条
- [ ] Headless pipeline runner (`scripts/run_pipeline.sh`) 未实际测试过完整流程
- [ ] damage-assessment 技术方案完成后需要继续 Phase A.5

## 下次会话建议
优先完成 damage-assessment 的技术方案后继续 Phase A.5。代码重构的剩余 3 项（_row_to_dict/N+1/inline import）可以在下次 /simplify 时一并处理。如果要跑完整 pipeline，先用 `./scripts/run_pipeline.sh damage-assessment --parallel` 测试 headless 模式。
