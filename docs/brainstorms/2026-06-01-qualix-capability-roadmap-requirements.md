# Qualix 能力路线图需求文档

> 日期：2026-06-01
> 范围：P0–P2 五个方向的完整实施规格

---

## 背景与目标

Q05b 当前成功率极差（>5 轮或卡死），是整个 pipeline 最大的交付阻塞。TS/Go 支持缺失限制了非 Java 项目接入。Q01 缺乏迭代推理能力。multi-agent 还是文件交换模拟。

所有五项均做完整实现，不留技术债。

---

## P0-1：Q05b 幻觉控制（Java 方法名/import 幻觉）

### 问题根因

agent 在生成 `@Test` 时会凭空发明：
1. 被测类里不存在的方法名（如 `buildXxxDto()`）
2. 不存在的 import（如 `com.example.XxxHelper`）
3. 错误的构造函数签名

编译失败后 Ralph Loop 重试，但 prompt 里没有「已失败的幻觉方法名」的 negative example，agent 可能再次生成同样的错误。

### 解决方案

**三层防护：**

1. **pre-codegen 代码骨架注入**（skill 层）：在生成 @Test 前，先调用 `code_skeleton.py` 的 `SkeletonResult`，把被测类的所有 public 方法签名注入到 prompt 的 `given` 区域。agent 只能使用骨架里列出的方法名。

2. **post-compile 幻觉定位反馈**（skill 层）：`mvn test-compile` 失败时，解析 `error: cannot find symbol` 的具体行号和符号名，把「你生成了不存在的 `buildXxxDto()`，该类只有以下方法」追加到下一轮的 fixer prompt 里。

3. **import 白名单验证**（新增 gate）：每批生成后，解析 @Test 方法里的 import 语句，对照 `_q05_target_modules.json` 里的已知类路径做白名单验证。不在白名单里的 import 标为 WARNING，在 `phase_b_code_status.json` 里记录，fixer 优先处理。

### 验收标准

- 编译成功率 ≥ 90%（第一次 `mvn test-compile` 即通过，不需要 fixer 重跑）
- 相同幻觉错误在同一项目内不出现第二次（负面 example 被注入）
- import 幻觉警告覆盖率：>95% 的幻觉 import 能在编译前被 gate 捕获

### 范围

- 修改 `skills/unit-test-codegen/SKILL.md`（Step 2 注入骨架，Step 3 失败反馈）
- 修改 `references/test-generation-rules.md`（骨架使用规则）
- 新增 `src/qualix/quality/checks/import_whitelist_check.py`
- 接入 `src/qualix/quality/checks/finalize_checks.py` 的 Q05b gate 链

---

## P0-2：Q05b Mock 策略错误（runtime 测试失败）

### 问题根因

编译通过但 `mvn test` 失败，根因在于：
1. `@InjectMocks` vs `new Xxx(obj1, obj2)` 选错——DDD+TMF 分层里 `@InjectMocks` 对 inner class 不生效
2. `Mockito.when().thenReturn()` 固定返回和被测方法实际调用链不匹配（mock 了错误的层）
3. `verify()` 调用次数期望错误（exactly(1) vs atLeastOnce()）

### 解决方案

**两层增强：**

1. **Mock 模板库**（skill 层）：在 `references/test-generation-rules.md` 里建立 DDD+TMF 分层 Mock 模板——Domain Service、Application Service、Infrastructure Adapter 各自对应的 `@ExtendWith(MockitoExtension.class)` + `@InjectMocks` 组合模板。agent 对照层级选模板，不自由发挥。

2. **runtime 失败诊断反馈**（skill 层）：`mvn test` 失败后，解析 Surefire 报告里的 `AssertionError`/`NullPointerException` 堆栈，定位到具体的 `@Test` 方法名 + 失败原因，追加到下一轮 prompt："EUT-007 的 `verify()` 失败，原因是 mock 了 `Repository` 层而非 `DomainService` 层，请改为 mock `XxxDomainService`"。

3. **Mock 一致性静态检查**（新增 check）：在 C9 之后、`mvn test` 之前，静态检查 `@InjectMocks` 注解的类是否和 `when()` mock 的依赖层级一致。

### 验收标准

- `mvn test` 第一次通过率 ≥ 70%（当前估计 <30%）
- Mock 分层错误在 fixer 第一轮即修复率 ≥ 85%

### 范围

- 修改 `references/test-generation-rules.md`（新增 Mock 模板库，按 DDD+TMF 层列出）
- 修改 `skills/unit-test-codegen/SKILL.md`（Step 3.3 增加 runtime 失败解析和反馈）
- 新增 `src/qualix/quality/checks/mock_consistency_check.py`

---

## P1-1：TS 和 Go Q05b 支持

### 现状 gap

- `src/qualix/languages/typescript/provider.py`（436 行）和 `src/qualix/languages/go/provider.py` 均已实现 `compile_check` 和 `run_tests`
- `src/qualix/quality/checks/compile_check.py` 已支持 `language_provider` 参数（306 行）
- **gap**：`src/qualix/quality/checks/test_execution_gate.py`（360 行）完全没有 `language_provider` 接入，硬编码 Java/JaCoCo 路径
- **gap**：`skills/unit-test-codegen/SKILL.md` 的 Step 2 模板和 Step 3 验证命令都硬编码 Java

### 解决方案

**TS 和 Go 同步接入，分三层打通：**

**层 1 — test_execution_gate 多语言化**

重构 `test_execution_gate.py`，接受 `language_provider` 参数：
- Java：保持现有 `mvn test` + JaCoCo 路径
- TS：调用 `TypeScriptProvider.run_tests()`，解析 Jest/Vitest JSON reporter 输出
- Go：调用 `GoProvider.compile_check()` + `go test -json`，解析 JSON 输出
- 覆盖率：TS 用 `--coverage` + lcov 解析；Go 用 `go test -cover`

**层 2 — skill 多语言模板**

`skills/unit-test-codegen/SKILL.md` 的 Step 2 增加语言分支：
- 检测 `_upstream_context.md` 里的 `language` 字段
- Java：现有模板
- TypeScript：Jest `describe/it/expect` 模板 + `jest.mock()` 模式
- Go：`TestXxx(t *testing.T)` 模板 + `testify` mock 模式

**层 3 — C9 追溯注释多语言化**

当前 C9 检查依赖 `// EUT-xxx` 注释（Java 单行注释）：
- TS：`// EUT-xxx` 相同，无需改
- Go：`// EUT-xxx` 相同，无需改

### 验收标准

- 给定一个 TS 项目（有 `package.json` + Jest/Vitest），`qualix-run project execute Q05b --json` 能跑通并产出 `phase_b_code_status.json`
- 给定一个 Go 项目（有 `go.mod`），同上能跑通
- 现有 Java 测试全绿（不回归）

### 范围

- 重构 `src/qualix/quality/checks/test_execution_gate.py`
- 修改 `src/qualix/runtime/handlers/handlers_execute.py`（传入 language_provider）
- 修改 `skills/unit-test-codegen/SKILL.md`（多语言 Step 2 模板 + Step 3 命令）
- 新增 `src/qualix/quality/checks/ts_coverage_parser.py`（lcov 解析）

---

## P1-2：Q01 ReAct 推理（工具驱动迭代式需求发现）

### 问题根因

Q01 当前是单次 LLM 调用。面对复杂 PRD（多状态机、跨系统、图片为主），一次输出的 SE 质量依赖 prompt 里的规则完备性，但 agent 无法：
1. 发现一个状态机节点后，主动去搜索其他文档里的触发条件
2. 发现 GAP 后，主动查询代码仓库确认是否有隐含实现
3. 发现 OPEN 后，主动追问用户最关键的那一个

### 解决方案

**ReAct 循环（Reason + Act）嵌入 Q01 执行流**

不改 `adaptive_loop` 架构，在 Q01 skill 的 Step 2（通读）和 Step 3（结构化）之间增加一个 **ReAct 工具调用阶段**：

```
Step 2: 通读 → 建立初步业务理解（现有）
Step 2.5: ReAct 工具调用阶段（新增）
  - 允许工具：Read（读文档片段）、Grep（搜索关键词）、AskUserQuestion（追问一个关键 OPEN）
  - 触发条件：发现跨文档引用、状态机节点不完整、异常路径缺依据
  - 退出条件：连续 2 轮无新发现，或达到 5 轮上限
Step 3: 结构化（现有，但输入更完整）
```

ReAct 阶段的工具调用结果追加到 `_reasoning_log.md`，作为 SE 的 `source` 证据链。

这不需要改 `adaptive_loop` 架构——Q01 skill 本身就在 allowed-tools 里有 `Read`、`Grep`、`AskUserQuestion`，只需在 skill 的 Step 2 和 Step 3 之间明确规定"必须先走 ReAct 阶段"。

### 验收标准

- Q01 对同一份有跨文档引用的 PRD，SE 数量提升 ≥ 20%（对比无 ReAct 基线）
- ReAct 轮数不超过 5 轮（有硬性退出条件防止 loop）
- `_reasoning_log.md` 里每条 SE 都能追溯到具体的工具调用证据

### 范围

- 修改 `skills/requirement-structuring/SKILL.md`（在 Step 2 和 Step 3 之间插入 Step 2.5）
- 新增 `references/react-tooling-guide.md`（ReAct 工具调用规则和退出条件）
- 修改 `src/qualix/quality/checks/finalize_checks.py`（Q01 reasoning_log 里的工具调用记录列为可选 bonus 证据）

---

## P2：真 multi-agent context 隔离

### 现状

`src/qualix/agents/multi_agent.py` 注释明写"Phase 1：用文件交换数据，context 隔离"。实际执行走的是 `adaptive_loop`——Worker/Judge/Critique 在同一 LLM session 里串行切换，Judge 能看到 Worker 的推理过程（不独立）。

### 解决方案

**真正的 Agent tool 派发**

利用 Claude Code 的 `Agent` tool（已有 `src/qualix/agents/agent.py` 封装），把 Worker、Judge、Critique 分别派发为独立 Agent 子任务：

1. **Worker Agent**：独立 context，只看 skill + evidence pack，输出 report 文件
2. **Judge Agent**：独立 context，只看 report + rubric，不看 Worker 的推理过程
3. **Critique Agent**：独立 context，只看 report + Judge result

**通信协议**：完全通过文件交换（`phase_dir` 下的 `phase_a_report.md`、`_judge_result.json`、`_critique.json`），无 in-process 状态传递。

**并发**：Judge 和 Critique 可以并发（Judge 完成后 Critique 立刻启动；如果有多个 Judge model，同时派发）。Worker 必须串行（依赖 handoff）。

**与 adaptive_loop 的关系**：adaptive_loop 保留（用于 Worker 的多轮 fixer 迭代），但 Judge 调用改为 true subagent dispatch，而不是 in-process `multi_judge_vote`。

### 验收标准

- Judge 的 `_judge_result.json` 不包含任何 Worker 推理过程中的 `<thinking>` 内容（验证 context 隔离）
- 并发 Judge 在支持并发的环境下，耗时 ≤ 单 Judge 的 1.3× （非 2×）
- 现有 adaptive_loop 测试全绿

### 范围

- 重构 `src/qualix/agents/multi_agent.py`（从 prompt 生成器升级为真实 Agent 派发器）
- 修改 `src/qualix/agents/adaptive_loop.py`（`_run_judge` 改为 subagent 调用）
- 修改 `src/qualix/agents/agent_orchestrator.py`（并发 Judge 调度）
- 测试：`tests/test_multi_agent_isolation.py`（验证 context 不泄露）

---

## 实施顺序与依赖

```
P0-1 (幻觉控制)  ──┐
                   ├── 可并行，都是 Q05b 提升，无互相依赖
P0-2 (Mock策略)  ──┘

P1-1 (TS/Go支持) ── 依赖 P0-1/P0-2 完成后再接入（否则 TS/Go 也会卡死在 loop）

P1-2 (Q01 ReAct) ── 独立，不依赖其他项，可与 P0 并行

P2 (multi-agent) ── 最后，依赖 P1 完成后做（改动量最大，放在其他稳定后）
```

**建议分期：**

| 期 | 内容 | 预估工作量 |
|----|------|-----------|
| Sprint 1 | P0-1 + P0-2（并行）+ P1-2 | 1~2 周 |
| Sprint 2 | P1-1（TS/Go，基于 Sprint 1 稳定的 Q05b） | 1 周 |
| Sprint 3 | P2（multi-agent 隔离） | 2 周 |

---

## 非目标

- Q03/Q04/Q07 的 skill 改动（本次只动 Q01/Q05b）
- Python Q05b 支持（Python 测试生成模式与 Java/TS/Go 差异太大，单独立项）
- Q05b 的 JaCoCo 覆盖率目标从 80% 提升到 100%（现有指标保持）
- P2 的跨机器分布式 Agent（只做进程内 context 隔离）
