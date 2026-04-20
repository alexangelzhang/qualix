# 实施切片指导（Implementation Slicing Guide）

技术方案产出后，必须附带实施切片建议，指导开发者如何安全地分步实现。

## 切片原则

1. **垂直切片优先**：每个切片是一条完整的功能路径（API→Service→Domain→Gateway），不是水平切（先做所有 DB → 再做所有 API）
2. **风险优先**：最不确定的部分先做，快速验证可行性
3. **Contract-first**：先定义接口契约（DTO + Provider interface），再并行实现
4. **每个切片可独立验证**：切片完成后可以跑测试确认，不依赖后续切片

## 任务分级

| 分级 | 改动量 | 文件数 | 示例 |
|------|--------|--------|------|
| XS | < 30 行 | 1-2 | 加一个枚举值、改一个校验规则 |
| S | 30-100 行 | 2-3 | 一个接口的完整实现（含测试） |
| M | 100-300 行 | 3-5 | 一个完整功能路径（API→Domain→Gateway） |
| L | 300-500 行 | 5-8 | 一个业务模块（含多个接口） |
| XL | 500+ 行 | 8+ | 必须拆分，不允许单个任务超过 XL |

## 拆分启发式

- 任务标题里有"和"字 = 两个任务
- 涉及超过 5 个文件 = 考虑拆分
- 预估超过 1 天 = 必须拆分

## 输出格式（附在技术方案末尾）

```markdown
## 实施切片建议

### Slice 1 [S] — 数据模型 + 接口契约（风险：低）
- 新增 DTO: XxxRequest, XxxResponse
- 新增 Provider interface: XxxService
- 新增 Gateway interface: XxxGateway
- 验证方式: 编译通过

### Slice 2 [M] — 核心业务逻辑（风险：高，先做）
- 实现 DomainService + DomainStep
- 实现状态机流转
- 验证方式: 单测覆盖 Happy + Exception

### Slice 3 [S] — Gateway 实现（风险：中）
- 实现 XxxGatewayImpl
- 实现 Mapper + DO
- 验证方式: 集成测试

### Slice 4 [XS] — 配置 + 上线（风险：低）
- 数据库 migration
- 配置项
- Feature flag
```
