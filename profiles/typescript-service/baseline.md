# TypeScript Service Baseline

## 测试规范

### 测试文件组织
- 测试文件与源文件同目录，命名 `*.test.ts` 或 `*.spec.ts`
- 集成测试放在 `__tests__/` 目录
- 测试使用 `describe/it` 组织，每个 `it` 只测一个行为

### 断言规范
- 优先使用 `toBe`/`toEqual`/`toStrictEqual` 验证具体值
- 避免仅用 `toBeDefined()`/`toBeTruthy()` 作为唯一断言
- `toHaveBeenCalledWith()` 优于 `toHaveBeenCalled()`（验证入参）
- 异常测试用 `toThrow()` 后补充状态断言

### Mock 规范
- 优先使用依赖注入，减少 `jest.mock()` 使用
- Mock 外部服务（HTTP、DB），不 mock 内部模块
- `jest.spyOn()` 优于全局 `jest.mock()`
- 每个测试后清理 mock：`jest.restoreAllMocks()`

### 覆盖率要求
- 行覆盖率 ≥ 80%
- 分支覆盖率 ≥ 75%
- 语句覆盖率 ≥ 80%

## 代码规范

### TypeScript 严格模式
- `tsconfig.json` 必须启用 `strict: true`
- 禁止 `any` 类型（除非有充分理由并加注释）
- 函数返回值必须显式标注类型

### 错误处理
- 异步函数必须有 try-catch 或 `.catch()` 处理
- 自定义错误类继承 `Error`，携带错误码
- 禁止吞掉异常（空 catch 块）
