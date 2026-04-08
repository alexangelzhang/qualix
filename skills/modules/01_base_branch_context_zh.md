# 模块 01：基线分支与评审上下文

## 目标

在不依赖 `gh` 的前提下，确定基线分支并确认是否存在有效 diff。

## 步骤

1. 获取当前分支：
   - `git branch --show-current`
2. 获取本地默认基线（优先顺序）：
   - `git symbolic-ref refs/remotes/origin/HEAD` 解析出 `origin/<base>`
   - 若失败，尝试 `main`
   - 若 `main` 不存在，尝试 `master`
3. 判断是否需要评审：
   - 若当前分支等于基线分支，直接结束。
   - 执行 `git diff <base> --stat`，无差异则结束。

## 输出模板

```text
Review Context:
- current_branch: <branch>
- base_branch: <base>
- diff_files: <N>
- diff_lines: <added/deleted 概览>
```

## 无需评审时输出

```text
Nothing to review — 当前在基线分支或与基线无差异。
STATUS: DONE
```
