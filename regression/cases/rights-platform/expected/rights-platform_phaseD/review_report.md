# Phase D: Call-Chain-Level Code Review Report

> 项目: 权益中心二期（退款 + 查询）
> 评审日期: 2026-03-30
> 代码版本: car-equity-center (feature_main_20260309_refund), car-equity-admin (feature_main_20260309_refund), query modules (feature_main_20260203_equity_move)

---

## 1. 退款模块 — Call Chain Trace

### Chain 1: refund() 主链路

```
Admin: ServicePackageRefundProviderImpl.servicePackageRefund()
  → PackageRefundDomainService.refund()
    → PackageRefundCenterGatewayImpl.refund() [Dubbo RPC]
      → Center: PackageRefundProviderImpl.refund()
        → PackageRefundCmdExe.execute()
          → PackageRefundService.refund()
            ├─ SerializableIsolationAbility.acquireLock()  [分布式锁 ✓]
            ├─ DecideStepsAbility.decideSteps()  → "CnCar_packageRefund"
            └─ TMF.execute(chainId, creator, main)
               Step 1:  RefundParamParseStep        — 参数校验
               Step 2:  DuplicateRefundCheckStep     — 幂等校验 (RefundDuplicateCheckExt)
               Step 3:  EquityInfoQueryStep          — 查询权益信息 (EquityInfoQueryAbility)
               Step 4:  RefundRuleQueryStep          — 退款规则查询
               Step 5:  RefundLimitCheckStep         — 限制规则校验 (含使用检查/购买时间/下单人)
               Step 6:  RefundAmountCalculateStep    — 退款金额计算
               Step 7:  BpmApprovalStartStep         — BPM 审批发起
               Step 8:  RefundRecordSaveStep         — 退款记录保存 (@Transactional)
               Step 9:  RefundingStatusUpdateStep    — 权益状态→退款中 (@Transactional)
               Step 10: VoucherRecallStep            — 凭证回收
               Step 11: PostRecallActionStep         — 后置动作（积分补偿等）
               Step 12: OrderRefundStep              — 订单退款
```

**保护机制评估**:
- 分布式锁: PackageRefundService 层 acquireLock + tryLock + finally unlock — **完备**
- 幂等: DuplicateRefundCheckStep → RefundDuplicateCheckExt 按 orderId 查 equity_refund_record，状态为 REFUNDING/REFUND_SUCCESS 时拦截 — **完备**
- 事务: RefundRecordSaveAbility.saveRecords() 有 @Transactional — **完备**

### Chain 2: cancelRefund() 链路

```
Admin: ServicePackageRefundProviderImpl.servicePackageCancelRefund()
  → PackageRefundCenterGatewayImpl.cancelRefund() [Dubbo RPC]
    → Center: PackageRefundProviderImpl.cancelRefund()
      → CancelRefundCmdExe.execute()
        → PackageRefundCancelService.cancel()
          → CancelRefundAbility.cancel()  [直接调用，绕过 TMF 步骤链]
            ├─ resolveOrderId()
            ├─ packageCancelRecordGateway.findByOrderId()
            ├─ 校验 status == REFUNDING && idempotentId 非空
            ├─ bpmGateway.cancelProcess()                    [外部调用]
            ├─ packageCancelRecordGateway.updateStatusWithAudit() → REFUND_CANCELLED
            ├─ restoreEquityValid()                          [异常被吞!]
            │   ├─ EquityInfoQueryAbility.queryEquityInfo()
            │   └─ EquityRecordValidStatusUpdateAbility.updateToValid()
            └─ packageIssueOperateLogGateway.save()
```

**问题**: 无分布式锁，restoreEquityValid 异常被吞。

### Chain 3: refundBpmCallBack() — BPM 审批回调

```
Admin: ServicePackageRefundProviderImpl.refundBpmCallBack()
  → PackageRefundCenterGatewayImpl.refundBpmCallBack() [Dubbo RPC]
    → Center: PackageRefundProviderImpl.refundBpmCallBack()
      → RefundBpmCallbackCmdExe.execute()
        ├─ Accept: handleAccept()
        │   → PackageRefundService.executeAfterBpmApproveCancel()  [无分布式锁!]
        │     ├─ DecideStepsAbility → "CnCar_bpmApproveCancel"
        │     └─ TMF.execute(): EquityInfoQuery → EquityUsageCheck → RefundingStatusUpdate
        │        → VoucherRecall → PostRecallAction → OrderRefund
        ├─ Refuse: handleRefuse()
        │   → PackageRefundService.executeAfterBpmReject()  [无分布式锁!]
        │     → BpmRejectAbility.rejectRefund()
        └─ Cancel: handleCancel()
            → CancelRefundCmdExe.execute() [复用取消退款链路，同样无锁]
```

### Chain 4: refundCompletion() — 退款完成消息

```
Center: PackageRefundProviderImpl.handleRefundCompletion()
  → PackageRefundCompletionService.handleRefundCompletion()
    ├─ SerializableIsolationAbility.acquireLock()  [分布式锁 ✓]
    ├─ DecideStepsAbility → "CnCar_refundCompletion"
    └─ TMF.execute():
       Step 1: RefundCompletionParamParserStep
       Step 2: RefundCompletionInfoQueryStep
       Step 3: RefundCompletedStatusUpdateStep
              → RefundCompletedStatusUpdateAbility.updateStatus() [@Transactional]
                ├─ EquityRecordValidStatusUpdateAbility.updateToInvalid()  [新库+旧库]
                └─ packageCancelRecordGateway.updateStatus() → REFUND_SUCCESS [双写]
```

**保护机制**: 分布式锁 ✓，事务 ✓。

---

## 2. 查询模块 — Call Chain Trace

### Chain 5: getPackageDetail() (Center)

```
Center: PackageInfoProviderImpl.getPackageDetail()
  → PackageListQueryCmdExe.execute()
    → PackageInfoService.getPackageList()
      ├─ DecideStepsAbility.decideSteps()
      └─ TMF.execute(chainId, creator, main)
         Step 1: PackageListQueryParamParserStep — vid 非空校验 + 默认 displayType
         Step 2: ValidPackageInfoQueryStep       — 查有效权益包配置
         Step N: ... (后续步骤按 BP 编排，含 LocalEquityQuery, ExtendInfoEnrich 等)
    → CustomModelAbility.render()  — BP 前台响应模型扩展
```

### Chain 6: getAppPackageList() (Admin)

```
Admin: PackageInfoProviderImpl.getAppPackageList()
  → PackageInfoDomainService.getAppPackageList()
    → PackageInfoGateway.getAppPackageList() [Dubbo RPC → Center]
```

**查询链路评估**: 纯读操作，无状态变更，无并发风险。vid 参数校验完备。Admin 层做了 vid 非空校验 + mid 兜底（DubboUpcContextUtil.getOperatorMid()）。

---

## 3. 对 A.6 / 上轮已知问题的重新评估

### CR-001 (原 CRITICAL): IdempotentCheckStep key 含 currentTimeMillis

**重新评估**: 该问题在 `packageIssue`（权益下发）链路的 IdempotentCheckStep 中，**不在退款链路**。退款链路的幂等保护由 `DuplicateRefundCheckStep → RefundDuplicateCheckExt` 实现，使用 orderId 查 equity_refund_record 表判断状态（REFUNDING/REFUND_SUCCESS 拦截），**不涉及 currentTimeMillis**。退款记录的 idempotentId 格式为 `orderId + "_" + packageIssueId`（RefundRecordSaveAbility line 123），是确定性的。

**结论**: 退款链路幂等保护完备。原 CR-001 仅影响下发链路，不影响退款。**退款链路降级为 INFO**，下发链路仍为 CRITICAL。

### CR-002 (原 CRITICAL): 无状态机

**重新评估**: 代码中确实没有显式状态机类，但通过以下机制实现了等效的应用层保护：
1. `RefundDuplicateCheckExt.checkDuplicate()`: 状态为 REFUNDING/REFUND_SUCCESS 时拦截重复退款
2. `CancelRefundAbility.cancel()`: 校验 `status == REFUNDING` 才允许取消
3. `BpmRejectAbility.rejectRefund()`: 校验 `status == REFUNDING` 才执行拒绝

**但 SQL 层缺少 WHERE status 守卫**（见 NEW-001），应用层校验和 SQL 更新之间存在时间窗口。

**结论**: 应用层有状态校验覆盖了主要场景，但 SQL 层无 CAS 保护。**降级为 MAJOR**（从 CRITICAL）。

### CR-003 (原 CRITICAL): 无乐观锁

**重新评估**:
- `PackageRefundService.refund()`: 有分布式锁 ✓
- `PackageRefundCompletionService.handleRefundCompletion()`: 有分布式锁 ✓
- `CancelRefundAbility.cancel()`: **无分布式锁** ✗
- `BpmRejectAbility.rejectRefund()`: **无分布式锁** ✗
- `PackageRefundService.executeAfterBpmApproveCancel()`: **无分布式锁** ✗

主退款链路和退款完成链路有锁保护，覆盖了最高频场景。取消退款和 BPM 回调是低频操作，风险相对可控。

**结论**: **降级为 MAJOR**（从 CRITICAL），与 NEW-002 合并跟踪。

### CR-004 (原 MAJOR): 重复退款抛异常而非幂等响应

**重新评估**: `DuplicateRefundCheckStep` line 42 抛出 `BizException(REPEAT_PURCHASE, ...)`。错误码 REPEAT_PURCHASE 语义确实不准确（应为 DUPLICATE_REFUND），但功能上能正确拦截重复退款。

**结论**: **维持 MAJOR**，建议修改错误码语义。

### CR-009 (原 MAJOR): OrderRefundStep 退款失败不抛异常

**重新评估**: 当前代码中 `OrderRefundStep.process()` line 43-46，退款失败时调用 `RefundFailedStatusUpdateAbility.updateStatus()` 记录 REFUND_FAILED 状态，但**不抛异常**，Step 链正常结束。有定时重试任务（AdminPackageRefundTaskProviderImpl）补偿。

**结论**: **已改善**，异步重试模式合理。但凭证已回收+退款失败的补偿仍不完整（见 NEW-003）。

---

## 4. 新发现的 Code-Level Issues

### NEW-001 [MAJOR] SQL 状态更新无 WHERE status 条件守卫

**位置**:
- `PackageCancelRecordMapper.xml` line 153-158: `updateStatus` — `WHERE idempotent_id = #{idempotentId}`
- `PackageCancelRecordMapper.xml` line 161-167: `updateStatusWithAudit` — `WHERE idempotent_id = #{idempotentId}`
- `EquityRefundRecordMapper.xml` line 104-110: `updateStatusByIdempotentId` — `WHERE idempotent_id = #{idempotentId}`
- `PackageIssueRecordMapper.xml` line 94-98: `updateStatus` — `WHERE id = #{id}`

**问题**: 所有状态更新 SQL 均无 `AND status = #{expectedStatus}` 前置条件。虽然应用层在更新前做了状态校验，但在分布式环境下查询和更新之间存在时间窗口。如果两个请求同时通过应用层校验，都会执行 UPDATE 成功，导致状态被覆盖。

**影响场景**:
- 退款中 → 退款取消 和 退款中 → 退款成功（completion 消息）同时到达
- 退款失败 → 重新退款 和 退款失败 → 退款成功 竞争

**建议**: 所有状态更新 SQL 增加 `AND status = #{expectedStatus}`，Java 层检查 `updateRows == 0` 时抛异常或重试。

### NEW-002 [MAJOR] CancelRefund / BpmReject / BpmApproveCancel 缺分布式锁

**位置**:
- `CancelRefundAbility.cancel()` — 直接操作退款记录和权益状态，无锁
- `BpmRejectAbility.rejectRefund()` — 直接操作退款记录和权益状态，无锁
- `PackageRefundService.executeAfterBpmApproveCancel()` — 执行完整 TMF 链路（含凭证回收+订单退款），无锁

**对比**: `PackageRefundService.refund()` 和 `PackageRefundCompletionService.handleRefundCompletion()` 都有完整的锁保护。

**场景**: 用户发起退款（持锁）的同时，BPM 回调 Accept 到达（无锁），两者可能并发修改同一订单的权益状态和退款记录。

**建议**: 在 `PackageRefundCancelService.cancel()` 和 `RefundBpmCallbackCmdExe` 的 handleAccept/handleRefuse 入口增加与 refund() 相同的分布式锁逻辑。lockKey 使用 orderId 保持一致。

### NEW-003 [MAJOR] 凭证回收成功但退款失败 — 补偿不完整

**位置**: `OrderRefundStep.process()` line 30-46

**问题**: 当 `main.isEquityCancelled() == true`（凭证已回收）但 `OrderRefundAbility.refundOrder()` 返回 false 时：
1. 退款记录状态更新为 REFUND_FAILED（RefundFailedStatusUpdateAbility 有独立事务，不会回滚）
2. 权益发放记录状态保持「退款中」不恢复
3. 凭证已回收（流量包、延保等），不会自动恢复

**影响**: 用户的权益凭证已被回收，但退款未成功，用户既没有权益也没有退款。

**现有补偿**: 有 `FailedRefundRecordQuery` 链路和定时任务重试机制，重试时 VoucherRecallAbility 会跳过已回收的权益（filterNeedRecallEquities 检查 DONE 状态）。但如果订单退款接口持续失败，没有最大重试次数限制和告警升级机制。

**建议**:
1. 定时重试任务增加最大重试次数，超过后触发告警
2. 考虑在 OrderRefundStep 退款失败时记录「凭证已回收待退款」标记，便于运营排查

### NEW-004 [MAJOR] 新旧库双写非事务性，从表失败仅日志无补偿

**位置**: `PackageCancelRecordGatewayImpl` — save() line 96-106, update() line 126-137, updateStatus() line 191-200, updateStatusWithAudit() line 233-245

**问题**: equity 主表和 center 从表的双写不在同一事务中。从表写入失败时仅记录日志（`log.error ... 需要补偿`），但代码中**没有实现任何补偿机制**（无补偿任务、无消息队列、无重试）。

**关键影响**:
- `findByProcessInstanceId()` (line 284) 查的是**从表 center**，如果从表未同步，BPM 回调将查不到记录，导致审批通过/拒绝无法执行
- `findByIdempotentId()` (line 249) 也查的是**从表 center**

**建议**: 实现补偿任务定期扫描主从不一致的记录，或将关键查询（findByProcessInstanceId）改为查主表。

### NEW-005 [MINOR] CancelRefundAbility.restoreEquityValid() 异常被吞

**位置**: `CancelRefundAbility.restoreEquityValid()` line 130-143

**问题**: 恢复权益 valid 状态的操作在 try-catch 中，异常仅记录 warn 日志。`cancel()` 方法仍返回 true，调用方认为取消成功。

**影响**: 退款记录已更新为 REFUND_CANCELLED，但权益发放记录的 valid 状态可能仍为「退款中」，导致用户看不到权益。

**建议**: 恢复失败时应抛出异常或返回 false，让调用方感知到部分失败。

### NEW-006 [MINOR] VoucherRecallAbility 原地修改 equityIssues 列表

**位置**: `VoucherRecallAbility.recallVoucher()` line 93

**问题**: `main.setEquityIssues(needRecallEquities)` 将 main 中的权益发放记录列表替换为过滤后的子集。下游 Step（如 PostRecallActionStep、OrderRefundStep）看到的 equityIssues 是不完整的。

**影响**: 如果后续步骤需要完整的权益列表（如统计、日志），会遗漏已跳过的权益。

**建议**: 使用独立字段（如 `setNeedRecallEquities()`）存储过滤后的列表，保留原始 equityIssues 不变。

### NEW-007 [MINOR] 查询模块多个 Dubbo 接口空实现已暴露

**位置**: `query/car-equity-admin/.../PackageInfoProviderImpl.java` — getPackageConfig() line 47, setPackageExtraInfo() line 98, getFirstOwnerEquity() line 104, getPackageGrantInfo() line 110

**问题**: 4 个方法为空实现（返回 null 或仅打印 warn），但已通过 `@DubboService` 暴露为 RPC 接口。

**影响**: 外部调用方调用这些接口会得到空响应，可能导致上游业务异常。

**建议**: 未实现的方法应抛出 `UnsupportedOperationException` 或返回明确的错误码，而非静默返回 null。

---

## 5. 对上轮问题的状态更新

| 问题 ID | 原级别 | 描述 | 本轮状态 | 说明 |
|---------|--------|------|----------|------|
| CR-001 | CRITICAL | 幂等键含 currentTimeMillis | **退款链路 N/A** | 仅影响下发链路，退款链路用 orderId 查表，不涉及此问题 |
| CR-002 | CRITICAL | 无状态机 | **降级 MAJOR** | 应用层有状态校验覆盖主要场景，但 SQL 层无 CAS（合并入 NEW-001） |
| CR-003 | CRITICAL | 无乐观锁 | **降级 MAJOR** | 主链路有分布式锁，部分入口缺锁（合并入 NEW-002） |
| CR-004 | MAJOR | 重复退款错误码语义 | **维持** | REPEAT_PURCHASE 应改为 DUPLICATE_REFUND |
| CR-005 | MAJOR | EquityCancelProvider 空接口 | **已修复** | 统一走 PackageRefundProvider.refund() |
| CR-007 | MAJOR | 分布式锁失败静默标记 | **仅影响下发** | 退款链路锁失败直接抛 BizException |
| CR-009 | MAJOR | 退款失败不抛异常 | **已改善** | 改为 REFUND_FAILED + 异步重试，但补偿不完整（见 NEW-003） |
| CR-010 | HIGH | cancel() 无分布式锁 | **合并入 NEW-002** | — |
| CR-011 | HIGH | restoreEquityValid 异常被吞 | **合并入 NEW-005** | — |

---

## 6. REQ → CODE 覆盖度分析

| REQ/BR | 描述 | 代码覆盖 | 备注 |
|--------|------|----------|------|
| BR-101 | 权益作废操作 | ✅ | EquityCancel 链路 + CancelRefundAbility |
| BR-102 | 申请退款操作 | ✅ | PackageRefund 完整链路 12 步 |
| BR-103 | 查看详情 | ✅ | PackageRefundDetailQuery 链路 |
| SE-001 | 作废→已作废，订单不变 | ✅ | EquityCancel 链路仅更新权益状态 |
| SE-002 | 退款→权益已作废+订单已退款 | ✅ | VoucherRecall + OrderRefund 两步 |
| SE-003 | 已作废终态，按钮置灰 | ✅ | DuplicateRefundCheck 拦截重复操作 |
| SE-009 | 作废≠退款语义区分 | ✅ | EquityCancel vs PackageRefund 两条独立链路 |
| SE-011 | 权益包状态机 | ⚠️ | 无显式状态机，靠应用层 if 判断 + SQL 无 CAS |
| SE-012 | 订单状态机 | ✅ | 订单状态由外部订单系统管理，本系统仅调用退款接口 |
| GAP-001 | 作废幂等性 | ✅ | DuplicateRefundCheckStep 拦截 |
| GAP-002 | 退款失败回滚策略 | ⚠️ | 有重试任务但无凭证恢复（见 NEW-003） |
| GAP-003 | 并发控制 | ⚠️ | 主链路有锁，取消/BPM 回调无锁（见 NEW-002） |
| BR-201 | 售后工作台权益展示 | ✅ | PackageInfoService.getPackageList() + clientType 区分 |
| BR-202 | 零售通PAD权益展示 | ✅ | clientType=RETAIL_LINK |
| BR-203 | 客服工作台权益展示 | ✅ | clientType=CUSTOMER_SERVICE，displayAppSource 隔离 |
| BR-204 | APP端权益展示回归 | ✅ | getAppPackageList() / getAppPackageDetail() |

---

## 7. 发现汇总

| ID | 级别 | 描述 | 关键位置 |
|----|------|------|----------|
| NEW-001 | MAJOR | SQL 状态更新无 WHERE status CAS 守卫 | PackageCancelRecordMapper.xml, EquityRefundRecordMapper.xml, PackageIssueRecordMapper.xml |
| NEW-002 | MAJOR | CancelRefund/BpmReject/BpmApproveCancel 缺分布式锁 | CancelRefundAbility, BpmRejectAbility, PackageRefundService.executeAfterBpmApproveCancel |
| NEW-003 | MAJOR | 凭证回收成功但退款失败无完整补偿（无最大重试/告警） | OrderRefundStep |
| NEW-004 | MAJOR | 新旧库双写无事务保证且无补偿机制，关键查询走从表 | PackageCancelRecordGatewayImpl |
| NEW-005 | MINOR | restoreEquityValid 异常被吞，cancel 仍返回 true | CancelRefundAbility line 130-143 |
| NEW-006 | MINOR | VoucherRecallAbility 原地修改 equityIssues 列表影响下游 | VoucherRecallAbility line 93 |
| NEW-007 | MINOR | 查询模块 4 个 Dubbo 接口空实现已暴露 | query/car-equity-admin PackageInfoProviderImpl |
| CR-004 | MAJOR | 重复退款错误码 REPEAT_PURCHASE 语义不准确 | DuplicateRefundCheckStep line 42 |

---

## 8. 结论

**状态: CONDITIONAL_PASS**

**改善点（相比上轮）**:
- 退款主链路保护完备：分布式锁 + 幂等校验 + 事务边界清晰
- 作废入口统一，消除了 CR-005
- 退款失败改为异步重试模式，消除了 CR-009
- 原 3 个 CRITICAL 经链路追踪后降级：CR-001 不影响退款链路，CR-002/003 主链路已有保护

**上线前必须修复**:
1. NEW-001: SQL 增加 WHERE status CAS 守卫（防并发状态覆盖）
2. NEW-002: cancelRefund/BPM 回调入口增加分布式锁（防并发操作同一订单）

**上线前建议修复**:
3. NEW-004: findByProcessInstanceId 改查主表（防 BPM 回调因从表未同步而失败）
4. NEW-003: 定时重试任务增加最大重试次数 + 告警
