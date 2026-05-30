### Step 1: 加载 Q01 产物

读取 q01/structured.json，共提取：
- REQ：8条（REQ-001~REQ-008）
- BR：11条（BR-001~BR-011）
- SE：10条（SE-001~SE-010）
- GAP：2条，OPEN：3条

### Step 2: 检查 Java 仓库

仓库路径：/Users/zhangyiqian/private-dev/asp-aftersale-service-wmx-logistic-exchange/asp-aftersale-service
base_ref: master，head_ref: HEAD

git diff --name-only 生产 Java 文件共 30 个，通过 build_code_index.py 提取 30 个类。

### Step 3: diff 文件分类决策

**included_diff_files（8个）：核心业务逻辑变更文件**
- LogisticExchangeIdentifyManager.java：全新核心类，248行，三段式识别逻辑，多个分支 — 必测
- LogisticExchangeIdentifyParam.java：新增 DTO，isValid()有校验逻辑 — 必测
- ExchangeOrderService.java：新增138行，assembleLogisticExchangeOrderParams等核心方法 — 必测
- GenericConfigDataManager.java：白黑名单查询，识别器核心依赖 — 测其mock行为
- Cn3cCreateTagExt.java：建单T2打标逻辑新增 — 必测
- Cn3cProcessExtendTagExt.java：检测处理T8重新识别+清标逻辑 — 必测
- Cn3cProcessMethodValidateExt.java：处理方法门控校验，多分支 — 必测
- OrderCenterConsumer.java：OC取消回传新分支，直接影响工单终态和结算 — 必测

**excluded_diff_files（22个）：** 枚举/接口/DTO/Dubbo API层，无独立业务分支，风险T3，通过上层集成覆盖。详见eut_matrix.json。

### Step 4: 变更 Java 实现类与 EUT 覆盖映射

| 类名 | EUT 覆盖 |
|------|---------|
| LogisticExchangeIdentifyManager | EUT-001~EUT-012 |
| ExchangeOrderService | EUT-013~EUT-016 |
| Cn3cCreateTagExt | EUT-017~EUT-018 |
| Cn3cProcessExtendTagExt | EUT-019~EUT-021 |
| Cn3cProcessMethodValidateExt | EUT-022~EUT-026 |
| OrderCenterConsumer | EUT-027~EUT-028 |

### Step 5: 需求覆盖自检

| REQ/BR/SE | 至少一条EUT？| 覆盖EUT |
|-----------|-------------|---------|
| REQ-001 | ✅ | EUT-001,004,005,007,017 |
| BR-001 | ✅ | EUT-002 |
| BR-002 | ✅ | EUT-003,011 |
| BR-003 | ✅ | EUT-017 |
| BR-005 | ✅ | EUT-022~026 |
| BR-007 | ✅ | EUT-013,014 |
| BR-008 | ✅ | EUT-015,016 |
| BR-011 | ✅ | EUT-008,009,010 |
| REQ-003 | ✅ | EUT-019~021,022 |
| REQ-004 | ✅ | EUT-013~016 |
| REQ-007 | ✅ | EUT-027,028 |
| SE-001 | ✅ | EUT-002 |
| SE-002 | ✅ | EUT-003 |
| SE-003 | ✅ | EUT-006 |
| SE-004 | ✅ | EUT-008 |
| SE-005 | ✅ | EUT-009 |
| SE-006 | ✅ | EUT-013 |
| SE-007 | ✅ | EUT-014 |
| SE-008 | ✅ | EUT-011,012 |
| SE-009 | ⚠️ | 工单流分支属于集成测试，单元测试不覆盖工作流路由 |
| SE-010 | ✅ | EUT-027 |

### Step 6: 不可测项说明

- REQ-002（工单流变更）、SE-009（强安装工单流分支）：涉及工作流引擎路由（ProcessContext），属于集成测试范畴，单元测试层无法隔离验证。
- REQ-005（XMS展示物流单关联信息）：纯展示层逻辑，属于前端/API集成测试范畴。
- REQ-006（换货完成工单闭环）：妥投消息全链路属于集成测试范畴；正向妥投触发的工单流转在OrderCenterConsumer正向路径中，通过EUT-027间接覆盖部分场景。
- REQ-008（拒收换）：OPEN-001未解决，无法设计确定性EUT。
