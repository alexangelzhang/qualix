# Go Service 技术栈基线

> 适用于 Go 微服务、HTTP/RPC 接口、仓储层与领域服务解耦的项目。

## 1. 分层职责

| 层 | 职责 | 禁止 |
|----|------|------|
| transport | HTTP/gRPC handler、请求解析、响应组装 | 业务规则、直接持久化 |
| application | 用例编排、事务边界、DTO 转换 | 存储实现细节、协议适配 |
| domain | 领域规则、状态迁移、幂等、聚合不变式 | 直接依赖数据库/网络客户端 |
| infrastructure | repository/client/queue/cache 技术实现 | 业务规则判断 |

## 2. 关键规则

1. handler 只做协议适配，不承载业务语义分支。
2. repository 接口定义在领域或应用边界，具体实现留在 infrastructure。
3. 并发写路径必须显式处理幂等、锁、版本号或去重键。
4. 外部依赖失败必须有超时、重试或降级语义。

## 3. 测试最小集合

| 层 | 必测场景 |
|----|---------|
| transport | 参数校验、错误码、响应结构 |
| application | 编排顺序、事务/回滚、异常包装 |
| domain | 状态机、幂等、边界条件、重复请求 |
| infrastructure | 持久化正确性、下游失败/超时处理 |

## 4. Go 特定检查点

1. 核心路径必须运行 `go test ./...`
2. 并发关键路径必须评估 `go test -race`
3. context 传递不能丢失超时和取消语义
4. error wrapping 应保留根因，避免吞错

## 5. 默认质量阈值

- 行覆盖率 >= 75%
- 分支覆盖率 >= 70%
- 并发关键路径 race check 必须通过
- 关键接口至少有 1 条集成级回归用例
