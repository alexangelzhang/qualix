# 模块 00：约束策略（先执行）

## 目标

建立 `/review-zh` 的强约束边界，确保评审可控、可审计、可人工决策。

## 允许依赖

- 本地 Git：`git branch`、`git diff`、`git log`。
- 本地检索：`rg`。
- 文件读写：`Read`、`Write`、`Edit`。
- 人工决策：`AskUserQuestion`。
- 本地 Python 脚本（可选）：
  - `scripts/feishu_direct_ingest.py`
  - `scripts/parse_image_assets.py`

## 禁用依赖

- 外部平台工具：`gh`、Greptile、Codex CLI。
- 系统交互命令：`open`。
- 任意遥测上报。

## 修复策略（强制）

1. 禁止自动修复。
2. 任意代码修改必须先人工确认。
3. 未确认前只允许输出“问题 + 证据 + 建议”。
4. 禁止自动提交、推送、建 PR。

## 违反约束时的处理

输出：

```text
STATUS: BLOCKED
REASON: 触发约束策略（外部依赖或未确认自动修复）
ATTEMPTED: <已执行动作>
RECOMMENDATION: 请切换到本地依赖 + 人工确认流程
```
