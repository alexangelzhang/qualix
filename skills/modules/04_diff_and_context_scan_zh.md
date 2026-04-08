# 模块 04：Diff 扫描与上下文补全

## 目标

读取完整变更并补齐跨文件上下文，避免只看 diff hunk 的误判；同时给出需求追踪证据。

## 步骤

1. 读取完整差异：
   - `git diff <base>`
2. 聚焦 Java 相关改动类型：
   - `*.java`
   - `pom.xml`
   - `application*.yml`
   - `mapper/*.xml`
   - `*.sql`
3. 枚举/状态扩散检查：
   - 发现新增枚举值后，用 `rg` 搜同类 case 分支。
   - 检查 `switch`、`if/else`、映射表是否补齐。
4. DDD/TMF 结构检查：
   - 检查 Step 是否存在直接注入 Ability。
   - 检查 Domain 规则是否上浮到 Application。
   - 检查 `decideSteps/TMF.execute` 失败路径处理是否可见。
5. 测试关联检查：
   - 观察 `src/test` 是否有对应新增/变更。
   - 没有则标记测试风险。
6. 最小追踪映射（必须输出证据）：
   - `REQ/BR/SEM -> 代码文件:行号`
   - `REQ/BR/SEM -> 测试文件:用例名`

## 证据规则

- 所有判断必须落到“文件 + 行号 + 代码片段语义”。
- 无法定位证据时，标注“未验证”，不得下肯定结论。
- 无法建立 `REQ/BR/SEM` 到代码/测试映射时，标记 `TRACE_BROKEN`。
