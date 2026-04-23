# DQG TypeScript 单测生成与审计支持

> 状态：**计划中** | 分支：`car-service-quality-gate` | 首个接入项目：service-cli

## 1. 背景

DQG 的 Q05（单测生成）、Q06（单测审计）、Q07（Code Review）三个 Phase 是语言敏感的。当前 Java 逻辑硬编码在以下模块中：

| 模块 | 语言耦合点 |
|------|-----------|
| `context/java_ast_analyzer.py` | tree-sitter Java AST 解析，JUnit 断言识别 |
| `context/weak_assert_analysis.py` | Java 断言正则匹配，`@Test` 注解识别 |
| `context/weak_assert_context.py` | 硬编码 `"tree-sitter-java"` 分析模式 |
| `quality/compile_check.py` | Maven/Gradle/Go 构建工具检测 |
| `runtime/handlers_execute.py` | `handle_code_skeleton` 硬编码 `java` 代码块 |

要支持 TypeScript（service-cli 为首个接入项目），且未来扩展 Go/Python/Rust 只需新增 Provider，需要先建立语言抽象层。

## 2. 架构设计

### 2.1 LanguageProvider 抽象层

```
src/dqg/languages/
├── __init__.py          # 包入口，注册所有内置 Provider
├── base.py              # LanguageProvider ABC + 数据类型
├── registry.py          # LanguageRegistry（注册、detect、获取）
├── java/
│   ├── __init__.py
│   ├── provider.py      # JavaProvider(LanguageProvider)
│   ├── ast_analyzer.py  # 从 context/java_ast_analyzer.py 迁入
│   └── assertions.py    # JUnit 断言强度映射
└── typescript/
    ├── __init__.py
    ├── provider.py      # TypeScriptProvider(LanguageProvider)
    ├── ast_analyzer.py  # tree-sitter-typescript 解析
    └── assertions.py    # Jest/Vitest 断言强度映射
```

### 2.2 LanguageProvider 接口

```python
class LanguageProvider(ABC):
    """语言 Provider — 覆盖 DQG 质量门控的全部语言特定能力"""

    # ── 检测 ──
    def detect(self, repo_root: Path) -> float:
        """返回置信度 0~1（支持 monorepo 多语言共存）"""

    def detect_test_framework(self, repo_root: Path) -> TestFrameworkInfo | None:
        """识别测试框架。Go/Rust 内置测试返回固定值"""

    def resolve_test_dependencies(self, repo_root: Path) -> list[str]:
        """解析测试相关依赖（testify, mockall, pytest 等）"""

    # ── 质量门控 ──
    def compile_check(self, repo_root: Path) -> CompileResult:
        """编译/类型检查。动态语言可返回 CompileResult(skipped=True)"""

    def lint_check(self, repo_root: Path) -> LintResult:
        """Lint 检查（clippy / eslint / ruff / golangci-lint）"""

    # ── AST 分析 ──
    def parse_source(self, source_file: Path) -> SourceInfo:
        """解析源文件：函数签名、类/struct、export、依赖"""

    def parse_assertions(self, test_file: Path) -> list[AssertionInfo]:
        """解析测试文件中的断言"""

    def classify_assertion_strength(self, assertion: AssertionInfo) -> Strength:
        """断言强度：strong / weak / trivial"""

    def detect_mock_patterns(self, test_file: Path) -> list[MockInfo]:
        """检测 mock 使用模式"""

    # ── 测试文件定位 ──
    def test_file_pattern(self) -> str:
        """glob 模式：'*_test.go', '*.test.ts', 'test_*.py'"""

    def locate_test_file(self, source_file: Path) -> Path:
        """给定源文件，返回对应测试文件的期望路径"""

    # ── 生成上下文 ──
    def get_test_gen_context(self, source_file: Path) -> TestGenContext:
        """为 LLM 提供语言特定的生成上下文"""

    def get_skill_overrides(self) -> dict:
        """对 skill prompt 的语言特定覆盖"""

    # ── 覆盖率 ──
    def run_coverage(self, repo_root: Path) -> CoverageResult | None:
        """执行覆盖率收集。不支持则返回 None"""
```

### 2.3 接口设计决策

| 决策 | 选择 | 理由 |
|------|------|------|
| `detect()` 返回类型 | `float`（0~1 置信度） | 支持 monorepo 多语言共存，按置信度选主语言或多语言并行 |
| `compile_check` 返回 | `CompileResult(passed, skipped, ...)` | Python 等动态语言不强制类型检查，`skipped=True` 优雅跳过 |
| Provider 发现机制 | 显式注册 | 项目规模不大，不需要插件化自动扫描 |
| AST 解析库 | tree-sitter 系列 | Java/TS 保持一致，性能好，社区成熟 |

## 3. TypeScript Provider 详细设计

### 3.1 能力矩阵

| 能力 | 实现方式 |
|------|----------|
| 语言检测 | `tsconfig.json` 存在 → 0.9；`package.json` 含 `typescript` → 0.7 |
| 测试框架识别 | 从 `package.json` devDependencies 检测 jest/vitest/mocha |
| 编译检查 | `tsc --noEmit`，解析 `file.ts(line,col): error TS...` 格式 |
| AST 解析 | tree-sitter-typescript 解析 `expect().toXxx()` 链式调用 |
| Mock 检测 | `jest.mock()`, `vi.mock()`, `jest.spyOn()`, `jest.fn()` |
| 测试文件定位 | `*.{test,spec}.{ts,tsx}` 或 `__tests__/` 目录 |
| 依赖解析 | 从 `package.json` 提取 jest/vitest/ts-jest 等 |
| Lint | `npx eslint --format json` |
| 覆盖率 | jest `--coverage` 或 vitest `--coverage`，解析 Istanbul JSON |

### 3.2 断言强度映射

```
Strong:
  expect(x).toBe(42)
  expect(x).toEqual({key: 'value'})
  expect(x).toStrictEqual(...)
  expect(x).toMatchObject(...)
  expect(fn).toThrow(Error)
  expect(fn).toHaveBeenCalledWith(arg1, arg2)

Weak:
  expect(x).toBeDefined()
  expect(x).toBeTruthy()
  expect(x).toBeFalsy()
  expect(x).toBeNull()
  expect(x).toBeUndefined()

Trivial:
  expect(true).toBe(true)
  expect(fn).toHaveBeenCalled()  // 无参数，只验证调用不验证入参
```

### 3.3 弱断言信号（对标 Java 的 WeakAssertSignal）

| Signal Code | 含义 | 对应 Java Signal |
|-------------|------|-----------------|
| `EXPECT_DEFINED_ONLY` | 仅 `toBeDefined()`，未验证具体值 | `ASSERT_NOT_NULL_ONLY` |
| `CONSTANT_EXPECT` | `expect(true).toBe(true)` 等常量断言 | `CONSTANT_BOOLEAN_ASSERT` |
| `MOCK_VERIFY_ONLY` | 仅 `toHaveBeenCalled()` 无业务断言 | `VERIFY_ONLY_NO_BUSINESS_ASSERT` |
| `THROW_NO_EFFECT` | 仅 `toThrow()` 无后续状态断言 | `ASSERT_THROWS_NO_EFFECT_ASSERT` |
| `INSUFFICIENT_ASSERTIONS` | 方法体长但断言少 | `INSUFFICIENT_ASSERTIONS` |

## 4. Profile 扩展

### 4.1 DqgProfile 新增字段

`DqgProfile` dataclass 新增 `language: str` 字段（默认 `"java"`），Profile 加载时自动绑定对应 Provider。

### 4.2 typescript-service Profile

```json
{
  "profile_id": "typescript-service",
  "name": "TypeScript Service",
  "description": "Profile for TypeScript/Node.js services with Jest/Vitest testing.",
  "language": "typescript",
  "baseline_path": "profiles/typescript-service/baseline.md",
  "risk_catalog_path": "references/risk-catalog-risks.md",
  "quality_thresholds": {
    "line_coverage": 0.8,
    "branch_coverage": 0.75,
    "statement_coverage": 0.8
  }
}
```

## 5. Pipeline 改造点

### 5.1 compile_check.py

```
Before: detect_build_tool() → 硬编码 maven/gradle/go
After:  registry.detect(repo) → provider.compile_check()
```

### 5.2 weak_assert_context.py

```
Before: is_ast_available() → analyze_with_ast() → 硬编码 Java tree-sitter
After:  provider.parse_assertions() → provider.classify_assertion_strength()
```

### 5.3 handlers_execute.py

```
Before: handle_weak_assert 无语言参数
After:  从 ExecutionContext 获取 Provider，传入弱断言分析
```

### 5.4 向后兼容

- `context/java_ast_analyzer.py` 改为 facade re-export（`from dqg.languages.java.ast_analyzer import *`）
- 所有现有 `from dqg.context.java_ast_analyzer import ...` 的调用方无需改动
- 未知语言仍返回 `CompileResult(passed=True, skipped=True)`

## 6. 实施计划

### 依赖图

```
Phase 1 (抽象层定义)
  ├──→ Phase 2 (Java 迁移) ──→ Phase 3 (Pipeline 集成) ──┐
  ├──→ Phase 4 (TS Provider)  ─────────────────────────────┼──→ Phase 6 (端到端验证)
  └──→ Phase 5 (Profile 扩展) ─────────────────────────────┘
```

### Phase 概览

| Phase | 内容 | 依赖 | 风险 |
|-------|------|------|------|
| 1 | LanguageProvider ABC + Registry | 无 | 低 |
| 2 | Java Provider 迁移 + facade 兼容 | Phase 1 | 中（回归） |
| 3 | Pipeline 集成（compile_check, weak_assert 等） | Phase 2 | **高**（改动面广） |
| 4 | TypeScript Provider 实现 | Phase 1 | 中（AST 解析） |
| 5 | Profile 扩展 + typescript-service | Phase 1 | 低 |
| 6 | 端到端验证（service-cli 接入） | Phase 3, 4, 5 | 中 |

### 并行策略

- Phase 1 完成后，Phase 2/4/5 可并行启动
- Phase 3 必须等 Phase 2 完成（依赖 Java 迁移后的接口）
- Phase 6 等所有前置完成

### 验证标准

- Phase 2 完成后：现有 Java 项目行为与迁移前完全一致
- Phase 3 完成后：对未知语言优雅降级，不 crash
- Phase 4 完成后：对 service-cli 的 `runner.test.ts` 能正确解析断言
- Phase 6 完成后：Q05 + Q06 对 service-cli 产出完整报告

## 7. 未来扩展路径

新增语言只需：

1. 新建 `src/dqg/languages/<lang>/` 包，实现 `LanguageProvider`
2. 在 `languages/__init__.py` 注册
3. 新建 `profiles/<lang>-service/` Profile

预估各语言实现复杂度：

| 语言 | 复杂度 | 原因 |
|------|--------|------|
| Go | 低 | 测试内置，工具链统一，几乎没有选择题 |
| Python | 中 | pytest vs unittest 两套，动态类型导致 AST 信息少 |
| Rust | 中 | `#[test]` 同文件 vs `tests/` 目录两种模式，macro 解析有难度 |

建议扩展顺序：Go → Python → Rust
