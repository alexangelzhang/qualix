# Dev-QA Loop 反面教材

## ❌ 批量实现后统一 review

```
Task 1: 实现用户认证 → 写完代码，不 review，继续
Task 2: 实现权限控制 → 写完代码，不 review，继续
Task 3: 实现审计日志 → 写完代码，不 review，继续
最后统一 review → 发现 Task 1 的认证设计有问题
→ Task 2、3 都基于错误的 Task 1 构建，全部返工
```

## ✅ 逐 task 验证

```
Task 1: 实现用户认证 → 写完 → 自验证 → QA review → PASS → 继续
Task 2: 实现权限控制 → 写完 → 自验证 → QA review → FAIL
  → feedback: "权限检查应该在 middleware 层，不是 handler 层"
  → 带 feedback 修复 → 重新 QA → PASS → 继续
Task 3: 实现审计日志 → 基于正确的 Task 1+2 构建
```

关键区别：错误在 Task 1 就被发现，不会污染后续 task。

## ❌ QA 失败后盲目重试

```
QA feedback: "这个函数没有处理空列表的情况"
attempt 1: 加了 if not list: return []  → QA FAIL（没看 feedback 的具体场景）
attempt 2: 加了 try-except → QA FAIL（还是没理解问题）
attempt 3: 终于读了 feedback，发现是业务逻辑问题不是空值问题 → 但已经浪费了 2 次机会
```

## ✅ 带 feedback 定向修复

```
QA feedback: "这个函数没有处理空列表的情况——当用户没有订单时，
dashboard 应该显示空状态而不是报错"
→ 读懂 feedback：问题是空状态的 UI 处理，不是防御性编程
→ 加空状态组件 + 测试 → QA PASS（一次通过）
```

关键区别：先理解 feedback 的具体场景，再动手修。

## ❌ 跳过集成验证

```
8/8 tasks 全部 PASS → 宣布完成
→ 上线后发现 Task 3 的数据库迁移和 Task 7 的缓存策略冲突
→ 单独测试都没问题，组合起来才出 bug
```

## ✅ 完整集成验证

```
8/8 tasks 全部 PASS → 跑完整测试套件 → 发现 Task 3+7 冲突
→ 修复冲突 → 重新验证 → 确认无回归 → 才宣布完成
```
