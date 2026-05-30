# Q01 Reasoning Log — wmx-logistic-exchange

### Step 1: 证据采集

**证据文件：**
- `prd.md`：飞书文档《【PRD】大件上门换新-售后系统-26.1.26》，251行
- 代码 diff（feature-wmx-logistic-exchange vs master）：
  - `LogisticExchangeIdentifyManager.java`（新增，248行）—— 核心识别逻辑
  - `LogisticExchangeIdentifyParam.java`（新增）—— 参数 DTO
  - `ExchangeOrderService.java`（修改，+138行）—— 换货单创建扩展
  - `LogisticsService.java`（修改）—— 删除转寄离线下单方法
  - `LogisticsFaceOrderService.java`（修改）—— 删除国际逻辑
  - `SrvVerificationService.java`（修改，大量删除）—— 删除换新中台通知相关逻辑

**图片资源：** static/ 目录 22 张截图（业务流程图、工单展示样例），但由于 larkkit 生成为占位符，以文字描述为准。

### Step 2: 假设前置

**假设 A1（低置信度）**：PRD 未明确"检测改换货"场景与标准换货在物流取旧送新流程中是否有差异。根据代码实现，`buildLogisticExchangeExtInfo` 直接取 items 数据，无分支区分——假设两类场景处理方式相同。需产品确认。

**假设 A2（低置信度）**：PRD 第 2 节提到"品类 ID"和"商品 SKU"白/黑名单字段，但未说明多品类工单（一单多商品）的判断规则（OR/AND）。代码中 `passPrecheck(Set<String> goodsIds)` 用 AND 逻辑（全部不在黑名单才通过）。假设与代码一致。

**假设 A3（高置信度）**：`logistic_exchange_enable_time` 配置项是上线切量机制，PRD 未提及，来自代码注释。不作为需求文档需求，作为 GAP 记录。

**假设 A4（中置信度）**：PRD "换货取消"章节提及"上游原因取消"时"仍然对网点进行业务结算"，未说明结算时机是否与普通完成一致。假设结算逻辑复用已有机制，不新增。

**假设 A5（低置信度）**：拒收换流程 PRD 极简（一句话："上游操作拒收换，触发 OC 生成第二张换新单，售后进行换绑"），换绑的具体操作（换绑工单 ID？新建工单？）未说明。记为 OPEN。

### Step 3: 全量理解

**角色：** 信息员（网点）、工程师（上门检测）、物流配送员、物流系统（TMS/OC）、履约中心（FulfillmentRuleInterfaceService）、XMS（工单系统）

**关键状态迁移（换货工单）：**
```
建单 → 待上门（派单）→ 待服务（到达确认）→ 业务完成 → 换货中 → 待用户收货 → 已妥投完成/服务完成
                                                    ↓ 物流原因取消
                                                  服务完成（+物流原因取消日志）
```

**外部系统依赖：**
- 履约中心（FulfillmentRuleInterfaceService.isSendAndInstallSupported）—— 识别能力校验
- OC（换新订单系统）—— 创建换新单、取旧单，妥投消息
- TMS —— 生成取旧单

### Step 4: 批评者复查结果

**第一轮自检发现的遗漏：**
- 遗漏：入库单忽略规则（物流取旧时网点不出入库）—— 已补 BR-006
- 遗漏：上线时间校验是关键分支（旧版本工作流工单不打标）—— 已补 BR-009 和 GAP-001
- 遗漏：特批单号传递给物流 —— 已补 BR-010
- 遗漏：物流原因取消后 SN 允许再次建单 —— 已补 BR-011 和 OPEN-002

**第二轮（批评者视角）补充：**
- 履约中心异常降级（不打标、不阻断主链路）是 SE 而非 BR，已纳入 SE-003
- 多商品工单判断逻辑已纳入 SE-008（A2 假设场景）
- 重复打标幂等性需要验证（假设 A1 范围）—— 已纳入 SE-009
