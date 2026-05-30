---
name: "record-session"
description: "记录当前 session 摘要到 Codex journal 文件，供下次 session 启动时注入 context。用于 /record-session、记录会话、session journal。"
---

# Record Session — 会话摘要记录

在 session 结束前调用，将本次工作摘要写入 journal 文件，下次启动时自动注入。

## 执行步骤

### 1. 回顾本次 session

从对话历史中提取：

- **完成了什么**：列出已完成的任务/变更（2-5 条，每条一句话）
- **遇到的问题**：卡点、workaround、未解决的 bug（如果有）
- **下次要做什么**：明确的 next step（1-3 条）
- **关键决策**：本次做出的重要技术决策及原因（如果有）

### 2. 写入 journal 文件

文件路径：`.codex/journals/journal-{YYYY-MM-DD}-{HH}.md`

如果同一小时已有 journal 文件，追加序号：`journal-{YYYY-MM-DD}-{HH}-2.md`

格式：

```markdown
# Session Journal — {YYYY-MM-DD HH:MM}

## 完成
- 具体完成的事项

## 问题
- 遇到的问题（无则写"无"）

## 下一步
- 明确的 next step

## 决策
- 关键决策及原因（无则省略此节）
```

### 3. 确认输出

写入后告知用户：
- 文件路径
- 下次启动时会自动注入此 journal

## 约束

- 摘要控制在 30 行以内，追求简洁
- 只记录对下次 session 有价值的信息，不要流水账
- 不要记录代码细节，记录决策和方向
- journal 文件是短期接力用的，不替代 memory 系统
- 超过 7 天的 journal 不会被注入（hook 自动跳过）
