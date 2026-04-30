# 5 分钟快速上手

从 clone 到跑完 Phase Q01 的最短路径。

## 前置条件

- Python >= 3.11
- git
- AI IDE（Claude Code / Cursor / Windsurf）

## Step 1: 克隆 DQG（只需一次）

```bash
git clone <your-dqg-repo-url>
cd dev-quality-gate
```

## Step 2: 安装依赖

```bash
pip install -e .
pip install larkkit          # 飞书文档摄入
npm install -g agent-browser # 飞书画板截图（可选）
```

`larkkit` 用于从飞书抓取 PRD 文档。`agent-browser` 用于 API 下载失败时自动截图飞书画板/思维导图，不装不影响基础流程。

## Step 3: 环境检查

```bash
dqg-run any-project doctor
```

确认输出全部 ✓ 或只有 ⚠（警告不阻断）。

## Step 3.5: 图片解析增强（可选）

DQG 支持自动解析 PRD 中的图片（UI 截图、流程图、状态机）。需要安装 OCR 引擎：

```bash
dqg-run any-project setup-ocr
```

一键安装 tesseract + 中文语言包。安装后 `dqg-run doctor` 会显示 ✓。

不装也不影响基础流程——图片会标记为 `manual_review_required`，由人工补录语义。

**进阶（可选）**：
- 高精度 OCR 兜底：`pip install surya-ocr`（~500MB）
- VLM 深度解析：配置环境变量 `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` / `DASHSCOPE_API_KEY`

## Step 4: 初始化项目

```bash
dqg-run my-first-project init --profile java-ddd-tmf
```

执行效果：
```
  ✓ state.json 已创建
  ✓ version.json 已创建 (v0.2.0)

  项目 my-first-project 初始化完成:
    Profile: java-ddd-tmf
    输出目录: output/my-first-project
    Phase 目录: phaseA, phaseA3, phaseA6, phaseA5, phaseB, phaseC, phaseD

  下一步: dqg-run my-first-project startup
```

## Step 5: 在 AI IDE 中启动

```bash
@dqg_starter.md 执行
```

AI 会自动检测到 `my-first-project`，展示菜单：

```
==========================================
  研发质量门禁 — my-first-project
  进度: 0/7 (0%) | 总耗时: 0s
==========================================

  [1] ⬜ Phase Q01  需求结构化           ← 可执行
  [2] 🔒 Phase Q02  技术方案生成          (依赖 Q01)
  ...

  快捷键: [v] 详情模式  [g] 全局进度  [数字] 执行阶段

请选择:
```

输入 `1` 开始 Phase A。

## Step 6: 执行 Phase A

AI 会逐步引导你：

1. 提供 PRD 文档（飞书链接或本地路径）
2. AI 自动抓取文档 + 解析图片
3. 列出假设，等你确认
4. 执行需求结构化（REQ/BR/SE/GAP/OPEN）
5. 自检 + Judge/Critique
6. finalize → approve → 完成

## Step 7: 查看进度

输入 `g` 查看全局进度，或 `v` 查看每个 Phase 的详情。

## 下一步

- Phase Q01 完成后，可以并行执行 Phase Q02（技术方案生成）和 Phase Q05（单测生成）
- 输入对应数字即可开始
- 遇到问题？查看 [FAQ](faq.md)

## 常用命令速查

| 命令 | 用途 |
|------|------|
| `dqg-run <project> init` | 初始化项目 |
| `dqg-run <project> startup` | 输出 JSON 菜单（供 AI 解析） |
| `dqg-run <project> status` | 查看状态看板 |
| `dqg-run <project> doctor` | 环境健康检查 |
| `dqg-run <project> setup-ocr` | 一键安装 OCR 依赖 |
| `dqg-run <project> update` | 更新到最新版本 |
| `dqg-run <project> version` | 显示版本号 |
| `@dqg_starter.md 执行` | AI IDE 一站式入口 |
