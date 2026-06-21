# Qualix

AI 驱动的研发质量门禁——从需求到代码，每个环节都有迹可查。

[English](README.md) | 简体中文

[![Tests](https://github.com/alexangelzhang/qualix/actions/workflows/qualix-self-check.yml/badge.svg)](https://github.com/alexangelzhang/qualix/actions/workflows/qualix-self-check.yml)
[![PyPI](https://img.shields.io/pypi/v/qualix)](https://pypi.org/project/qualix/)
[![License](https://img.shields.io/badge/license-Apache%202.0-blue)](LICENSE)

---

## 测试全绿、覆盖率 100%，但需求真的被验证了吗？

PRD 写着：*500 元及以上的报销需要主管**和**财务双重审批。*

你的测试：

```
120 元 → 只需主管审批 ✓
600 元 → 需要财务审批 ✓
```

行覆盖率绿了。但**恰好 500 元**的边界测试缺失了——实现用的是 `> 500` 而不是 `>= 500`，边界条件悄悄走错了路径。

Qualix 把这类问题叫做**语义覆盖缺口**。Q06 阶段会在覆盖率工具看不到的地方把它找出来：

```
[HIGH] 缺少恰好 500 元的边界测试。
       实现使用 > 500，但需求规则是 ≥ 500。
       建议补充：approve(Request(amount=Decimal("500.00"))) → 需要财务审批
```

---

## 它解决什么问题

| 常见问题 | 通常的结果 | Qualix 的做法 |
|---|---|---|
| 需求在传递中失真 | PRD 的细节到了代码层已面目全非 | Q01 从 PRD 提取结构化需求条目，每条有可追踪 ID |
| 技术设计覆盖不全 | 设计评审靠经验，容易漏 | Q03/Q04 检查设计质量和需求覆盖情况 |
| 测试只覆盖代码行 | 覆盖率绿了，但业务行为没有被验证 | Q05a/Q05b 围绕业务行为设计并生成测试 |
| 断言太弱 | 只断言了调用或存在，没有验证语义 | Q06 审计测试意图、弱断言和覆盖证据 |
| Code review 靠记忆 | 不同 reviewer 标准不一 | Q07 产出有证据支撑的结构化 review 报告 |

---

## 真实项目数据

三个生产 Java 服务跑完 Q01→Q06 完整流程：

| 项目 | PRD 规模 | Q01 提取语义期望数 | Q06 审计测试目标数 | 弱/缺失 |
|---|---|---|---|---|
| 审批工作流 | 67 条需求 | 22 个语义期望 | 22 | 1 个部分覆盖 |
| 续费服务 | 31 条需求 | 11 个语义期望 | 90 | 0 |
| 平台服务 | 50 条需求 | 18 个语义期望 | 103 | 16 个部分覆盖，2 个缺失 |

平台服务中，103 个被审计的测试目标里有 18 个存在断言缺口——而行覆盖率没有发现它们。

---

## 快速上手

**第一步：不需要 API Key，先看效果**

```bash
pip install qualix
qualix-run demo          # 内置静态演示，无需任何 Key
```

**第二步：跑完整示例（需要模型 API Key）**

```bash
export ANTHROPIC_API_KEY="..."   # 或 OPENAI_API_KEY / GEMINI_API_KEY / DASHSCOPE_API_KEY

qualix-run --profile python-service expense-demo init
qualix-run ingest examples/expense-approval/prd.md --project expense-demo
qualix-run expense-demo startup --json
qualix-run expense-demo execute Q01 --json
```

支持 Anthropic Claude、OpenAI、Google Gemini、阿里云百炼（DashScope）。

**第三步：在线体验（无需安装）**

[→ Qualix SE 提取器](https://alexangelzhang.github.io/qualix/sandbox/)——粘贴一段 PRD，直接在浏览器里看结构化语义期望输出。带上自己的 API Key 即可。

### 定位 EUT 证据候选

`locate` 是只读的上下文收敛工具，用于把 Q05/Q06 需要看的代码或测试缩小到 file-line evidence candidate。它不判定 EUT 是否 `COVERED` / `PARTIAL` / `MISSING`，语义结论仍由 Q06 负责。

```bash
qualix-run my-service locate \
  --phase Q06 \
  --eut-id EUT-003 \
  --se-id SE-003 \
  --query "approval threshold 500 finance required" \
  --code-repo src/ \
  --json
```

返回的 `citations[]` 包含 `path`、`line_start`、`line_end`、`kind`、`eut_id`、`se_id`、`locator` 和 `reason`。所有 citation 必须绑定单个 EUT，不能按 SE 聚合。

---

## Demo 视频

[![Qualix demo](docs/assets/demo.gif)](https://youtu.be/wtI07KJYXRI)

▶ [在 YouTube 观看](https://youtu.be/wtI07KJYXRI)——测试全通过、覆盖率 100%，但 500 元边界缺失。

---

## 阶段模型

```
Q01 需求结构化
├── Q02 技术设计生成（可选）
│   └── Q03 技术设计质量 review
│       └── Q04 技术设计需求覆盖审计
│           └── Q07 代码 review
└── Q05a 可执行单测目标矩阵设计
    └── Q05b 单测代码生成
        └── Q06 单测覆盖质量审计
```

| 阶段 | 目标 | 主要输出 |
|---|---|---|
| Q01 | 结构化需求 | REQ/BR/SE/GAP/OPEN 报告和 JSON |
| Q02 | 生成技术设计 | 可实施的设计草稿 |
| Q03 | review 设计质量 | 架构/API/数据/错误/性能 findings |
| Q04 | 审计设计覆盖 | 需求到设计的覆盖矩阵 |
| Q05a | 设计单测目标 | EUT 矩阵 |
| Q05b | 生成单测代码 | 测试代码和执行说明 |
| Q06 | 审计单测质量 | 覆盖和断言质量报告 |
| Q07 | review 代码变更 | 有证据支撑的 review 报告 |

---

## CI 和 pre-commit 集成

**GitHub Actions**

```yaml
- uses: alexangelzhang/qualix@v0.2.0a1
  with:
    project-id: my-project
    phase: Q06
    fail-on: hard
```

**pre-commit**

```yaml
repos:
  - repo: https://github.com/alexangelzhang/qualix
    rev: v0.2.0a1
    hooks:
      - id: qualix-gate
        args: [my-project, ci-gate, --fail-on, hard]
```

两种集成都读取已有的 verdict 文件——门禁时不触发 LLM 调用，不产生额外费用。

---

## 与 AI Coding Agent 配合使用

Qualix 为三种主流 AI 编程环境内置了指令文件：

| 文件 | 环境 |
|---|---|
| `CLAUDE.md` | Claude Code（Anthropic） |
| `AGENTS.md` | Codex、opencode 及其他兼容 OpenAI 的 agent |
| `GEMINI.md` | Gemini CLI |

在任意 agent 里加载项目 starter 即可开始：

```
$qualix-starter
```

---

## 当前状态

Qualix 目前处于早期阶段，适合：

- 实验性使用
- 内部质量门禁工作流
- 评估阶段模型是否适合你的团队

API、文件格式和阶段报告在 `1.0.0` 稳定版前仍可能调整。欢迎提 issue 反馈使用中遇到的问题。

---

## 许可证

Apache License 2.0。Q01–Q07 核心阶段、CLI、所有语言 profile、所有 skill 文件和 benchmark 均为 Apache 2.0，将长期保持开源。未来的商业方向是托管服务和团队协作功能，不会限制开源核心。

---

- 贡献指南：[CONTRIBUTING.md](CONTRIBUTING.md)
- 更新日志：[CHANGELOG.md](CHANGELOG.md)
- 路线图：[ROADMAP.md](ROADMAP.md)
- 概念说明：[docs/concepts.md](docs/concepts.md)
- 真实项目结果：[docs/real-world-results.md](docs/real-world-results.md)
- 与同类工具对比：[docs/comparison.md](docs/comparison.md)
