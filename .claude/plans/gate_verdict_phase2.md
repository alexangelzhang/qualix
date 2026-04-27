# Phase 2: GateVerdict 统一卡控层

## 目标

将 flow_integrity、schema validation、phase_constraints、handler errors、guardrail 五层检查结果汇入一个 `GateVerdict`，消除三个断裂点，让 approve 只读 `_gate_verdict.json` 做决策。

## 核心设计

### GateVerdict 数据结构

```python
@dataclass
class CheckItem:
    source: str          # "flow_integrity" | "schema" | "phase_constraints" | "handler" | "guardrail" | "language"
    name: str            # 检查项名称
    passed: bool
    level: str           # "HARD" | "SOFT"  — HARD 不可绕过，SOFT 可 --force
    message: str = ""
    details: dict = field(default_factory=dict)

@dataclass
class GateVerdict:
    phase_id: str
    timestamp: str
    checks: list[CheckItem]
    
    @property
    def hard_blocked(self) -> bool:
        return any(not c.passed and c.level == "HARD" for c in self.checks)
    
    @property  
    def soft_blocked(self) -> bool:
        return any(not c.passed and c.level == "SOFT" for c in self.checks)
    
    @property
    def passed(self) -> bool:
        return not self.hard_blocked and not self.soft_blocked
```

### HARD vs SOFT 分类

| 检查源 | 级别 | 说明 |
|--------|------|------|
| flow_integrity CRITICAL | HARD | 产物缺失/critique 断裂 |
| schema 校验失败 | HARD | 结构化产物不合规 |
| phase_constraints blocking | HARD | Phase Contract 硬约束 |
| required handler 失败 | HARD | 必要 handler 崩溃 |
| guardrail BLOCKED | HARD | 门控阻断 |
| language compile_check 失败 | HARD | 编译不通过 |
| flow_integrity HIGH/MEDIUM | SOFT | 非关键问题 |
| guardrail WARNING | SOFT | 门控警告 |
| optional handler 失败 | SOFT | 非必要 handler |
| judge score < 3.0 | SOFT | 评分偏低 |

### `--force` 行为

- `--force` 只能绕过 SOFT 约束
- HARD 约束不可绕过，必须修复后重新 finalize
- 输出明确区分 HARD/SOFT 阻断原因

## 实施步骤

### Step 1: 新建 `src/dqg/runtime/gate_verdict.py`（~120 行）

- `CheckItem` + `GateVerdict` 数据类
- `build_verdict(result: PhaseResult, ...) -> GateVerdict` — 从各检查源收集
- `save_verdict(output_dir, project_id, phase_id, verdict)` — 写 `_gate_verdict.json`
- `load_verdict(output_dir, project_id, phase_id) -> GateVerdict | None` — 读取

### Step 2: 改造 `runtime_finalize()`（phase_runtime.py）

在 handler 执行和 guardrail 执行之后，新增：
1. 调用 `enforce_phase_constraints()` — 修复断裂点 2
2. 收集 LanguageProvider compile_check 结果 — 修复断裂点 3
3. 调用 `build_verdict()` 汇总所有检查
4. 调用 `save_verdict()` 写入 `_gate_verdict.json`
5. 根据 `verdict.hard_blocked` 设置 `result.success`

### Step 3: 改造 `cmd_approve()`（phase.py）

- 读取 `_gate_verdict.json` 做决策，不再分散读多个来源
- HARD blocked → 无条件阻断
- SOFT blocked + `--force` → 放行并记录
- SOFT blocked 无 `--force` → 阻断并提示
- 保留现有 Phase Contract 检查作为 fallback（verdict 文件不存在时）

### Step 4: Guardrail 结果接入（修复断裂点 1）

- `build_verdict()` 读取 `_guardrail_results.json`
- BLOCKED 级 guardrail → HARD CheckItem
- WARNING 级 guardrail → SOFT CheckItem

### Step 5: 多语言感知

- `build_verdict()` 检查 LanguageProvider 是否有 compile_check 结果
- 从 `_internal/_compile_result.json` 读取（如果存在）
- compile_check failed → HARD CheckItem
- 不依赖具体语言，通过 Provider 抽象

### Step 6: 测试

- `test_gate_verdict.py` — 单元测试 CheckItem/GateVerdict 逻辑
- 更新 `test_finalize_prompt_dedup.py` — 验证 verdict 文件生成
- 更新 `test_schemas.py` — 验证 schema 错误进入 verdict

## 文件变更清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `src/dqg/runtime/gate_verdict.py` | 新建 | GateVerdict 核心 |
| `src/dqg/runtime/phase_runtime.py` | 修改 | finalize 末尾汇总 verdict |
| `src/dqg/commands/phase.py` | 修改 | approve 读 verdict |
| `tests/test_gate_verdict.py` | 新建 | 单元测试 |
| `AGENTS.md` | 修改 | 文档同步 |
| `ROADMAP.md` | 修改 | 文档同步 |

## 多语言考量

- GateVerdict 不绑定任何具体语言，通过 `source` 字段区分检查来源
- LanguageProvider 的 compile_check/lint_check 结果统一转为 CheckItem
- 未来新增语言只需实现 Provider，GateVerdict 自动收集
- Phase Constraints 的指标解析已支持多语言（通过 structured JSON 字段）

## 风险

- `runtime_finalize()` 已经较长（342 行），新增 verdict 构建需控制行数
- 现有 `cmd_approve()` 的 Phase Contract 检查需要保留 fallback 路径
- Guardrail 当前在 `except: pass` 中执行，需确保 verdict 构建不受影响
