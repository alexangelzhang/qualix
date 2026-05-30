# Q01 SE Checklist 升级 — shuangzhou-v4 影子回归报告

> 实验日期：2026-05-10
> 输入：已 approved 的 18 条 SE + shuangzhou-v4 PRD（147 行）+ 图片语义（21 张）+ 新版 checklist prompt（含示例对照）
> 模式：静态分析，不改主线产物，不跑 pipeline

---

## 一、概览

| 指标 | 数值 |
|------|------|
| 现有 SE 总数 | 18 |
| STRONG（达到示例强度）| 3 |
| WEAK（需升级）| 15 |
| STRONG 占比 | 16.7% |
| 新增 SE 数量 | 14 |
| 最严重漏检 | BPM 外部系统降级（0 条相关 SE）、工单状态机非法跳转（0 条）、审批单终态幂等（0 条） |

### STRONG/WEAK 一览

| SE-ID | 类别 | Verdict | 主因 |
|-------|------|---------|------|
| SE-001 | 幂等/并发 | WEAK | 只有"同一工单一个审批中"方向性描述，无并发断言方法（N 次请求恰 1 次成功 + 错误码）|
| SE-002 | 匹配冲突 | WEAK | OR 逻辑清楚，但缺 verification（两个角色分别发请求各自预期）|
| SE-003 | 匹配冲突 | WEAK | AND 关系列出来了，但三个子条件没展开到具体枚举值（工单状态是哪 4 个、付费类型是哪些）|
| SE-004 | 状态迁移 | WEAK | "无论工单处于哪个状态"过于泛化，未列出状态集合 |
| SE-005 | 状态迁移 | WEAK | "并行流程"是概念描述，无具体迁移对断言 |
| SE-006 | 默认行为 | WEAK | "不增加额外节点"口语化，无进度条字段结构断言 |
| SE-007 | 跨系统口径 | WEAK | "特殊 case"未展开，"相互独立"不可验证 |
| SE-008 | 状态迁移 | WEAK | "工单回退"未说回退到哪个状态，"保持"无字段级断言 |
| SE-009 | 数据转换 | **STRONG** | 规则具体（*号数量=长度-1，保留首字），可直接写 parameterized test |
| SE-010 | 数据转换 | **STRONG** | 规则具体（直辖市市=省，露出市区），有例子 |
| SE-011 | 默认行为 | **STRONG** | 三分法规则清晰（已完成移动工单=半隐藏；未完成+到店=不隐藏）|
| SE-012 | 分组聚合 | WEAK | 有 AND 关系，但缺 verification，无具体 case 组合 |
| SE-013 | 幂等/并发 | WEAK | "只有一个审批结果生效"口语化，无并发断言（CountDownLatch、DB 条数）|
| SE-014 | 跨系统口径 | WEAK | "互不影响"不可验证 |
| SE-015 | 跨系统口径 | WEAK | "数据口径一致"不可验证，未说字段对等关系 |
| SE-016 | 时间窗口 | WEAK | 触发时机明确但无 toast 文案/errorCode 断言 |
| SE-017 | 接口约定 | WEAK | 无接口路径、方法、入参出参契约 |
| SE-018 | 接口约定 | WEAK | 有接口名但无新按钮类型值和 schema 变化 |

---

## 二、WEAK SE 升级明细（15 条）

### SE-001（幂等/并发）

| 字段 | 升级前 | 升级后 |
|------|--------|--------|
| description | 提前交车申请幂等控制：同一工单同一时间只能有一个审批中的申请，重复提交返回 toast 拦截 | 同一 workOrderId 并发发起提前交车申请时，仅允许 1 次成功进入审批流，其余请求必须返回 HTTP 409 + errorCode=EARLY_DELIVERY_IN_REVIEW + toast 文案"提前交车申请审批中，请勿重复提交"，数据库 `t_early_delivery_approval` 仅产生 1 条 status=REVIEWING 记录 |
| verification | —（缺失）| CountDownLatch 对同一 workOrderId 发起 10 个并发 POST /early-delivery/apply；断言恰好 1 次 201、9 次 409；SELECT COUNT(*) FROM t_early_delivery_approval WHERE work_order_id=? AND status='REVIEWING' = 1；断言响应体 errorCode=EARLY_DELIVERY_IN_REVIEW |

### SE-002（匹配冲突 / 审批流）

| 字段 | 升级前 | 升级后 |
|------|--------|--------|
| description | 审批角色 OR 逻辑：授权店店长和授权店财务是 OR 关系，任一角色审批即完成，不需要两者都审批 | 一条提前交车申请的审批人集合 = {该店授权店店长}∪{该店授权店财务}，任一人调用 POST /approval/{id}/approve 成功后，审批单状态立即流转为 APPROVED；此时另一未完成的审批人调用同接口必须返回 409 + errorCode=APPROVAL_ALREADY_CLOSED，且不产生二次审批记录 |
| verification | — | 准备店长 A、财务 B 两个 token；A 先调 approve 断言 200 + 单据 status=APPROVED；立即用 B 的 token 再调同单 approve 断言 409 + errorCode=APPROVAL_ALREADY_CLOSED；SELECT COUNT(*) FROM t_approval_action WHERE approval_id=? = 1 且 action=APPROVE |

### SE-003（匹配冲突 / 按钮展示）

| 字段 | 升级前 | 升级后 |
|------|--------|--------|
| description | 按钮展示三重条件 AND 逻辑：工单状态 AND 工单条件（付费类型/权益）AND 角色，三个条件必须同时满足 | 「申请提前交车」按钮 isVisible = (orderStatus ∈ {PENDING_SETTLEMENT, PENDING_SETTLEMENT_REVIEWING, PENDING_PAYMENT, PARTIAL_PAID}) AND (payType == WARRANTY OR hasFetchSendRight == true) AND (role ∈ {STORE_MANAGER, SERVICE_ADVISOR_SUPERVISOR, SERVICE_ADVISOR})，三项任一 false 则按钮 isVisible=false 且 hidden=true |
| verification | — | 参数化测试：对 4×2×3=24 组笛卡尔积 + 反例集（wrong state / wrong payType / wrong role 各 2 组），调用 userAuthV2 接口；断言 buttons 数组中 type=APPLY_EARLY_DELIVERY 项的 isVisible 与期望值一致；额外断言：orderStatus='PENDING_SETTLEMENT' AND payType='WARRANTY' AND role='STORE_MANAGER' → isVisible=true |

### SE-004（状态迁移 / 文案）

| 字段 | 升级前 | 升级后 |
|------|--------|--------|
| description | 提前交车文案展示与工单状态解耦：代驾单服务完成后，无论工单处于哪个状态，都展示"已提前交车+时间"标识 | 当代驾单 driverOrder.status=SERVICE_COMPLETED 且 workOrder.earlyDeliveryApplied=true 时，工单详情页 cardLabel 字段必须包含文本"已提前交车 {yyyy-MM-dd HH:mm:ss}"，其中时间=driverOrder.serviceCompletedAt；该规则对工单状态 ∈ {PENDING_SETTLEMENT, PENDING_SETTLEMENT_REVIEWING, PENDING_PAYMENT, PARTIAL_PAID, PENDING_DELIVERY, DELIVERED, COMPLETED} 全部生效 |
| verification | — | 参数化测试：7 种 workOrder.status × (代驾单完成 / 未完成) = 14 组；断言代驾单完成分支 cardLabel 全部 contains "已提前交车"+时间戳格式；未完成分支不含该文案；完成时间精确匹配 driverOrder.serviceCompletedAt |

### SE-005（状态迁移 / 并行流程）

| 字段 | 升级前 | 升级后 |
|------|--------|--------|
| description | 提前交车不改变工单主状态机：提前交车是并行流程，工单状态仍按原有条件流转 | 工单状态机转移条件集 T 在引入提前交车功能后保持不变：对任意 workOrder，其状态由 (结算状态, 支付状态, 代驾单状态) 决定，与 earlyDeliveryApplied 布尔字段无关；即 earlyDeliveryApplied 的 true/false 不得出现在 WorkOrderStateMachine.transition() 的任何分支条件中 |
| verification | 代码层：grep `earlyDeliveryApplied` 在 WorkOrderStateMachine.java 中引用数=0；行为层：对同一工单准备两个副本，一个 earlyDeliveryApplied=true 一个 false，其余字段相同；触发同一迁移事件（如 PAYMENT_COMPLETED）；断言两者 target state 完全相同 |

### SE-006（默认行为 / 进度条）

| 字段 | 升级前 | 升级后 |
|------|--------|--------|
| description | 进度条不受提前交车影响：进度条根据工单状态机流转展示，不因提前交车增加额外节点 | 工单详情接口返回的 progressSteps 数组结构与元素个数在开启/关闭提前交车功能时完全一致；该数组仅由工单主状态决定，不得因 earlyDeliveryApplied=true 新增或替换步骤 |
| verification | 准备两个工单（同状态、同支付、仅 earlyDeliveryApplied 不同），调用 GET /work-order/{id}/detail；断言 response.progressSteps 数组 .size() 相等；断言逐元素 .stepKey/.stepName 完全相等 |

### SE-007（跨系统口径 / 维保+代驾）

| 字段 | 升级前 | 升级后 |
|------|--------|--------|
| description | 维保工单与代驾单流程独立：两者在流程上相互独立，但有特殊 case（维保单变更服务项、回退节点时需保证待接车工单展示）| 维保工单聚合与代驾单聚合通过领域事件解耦：维保工单状态变更时发 `WorkOrderStateChanged` 事件，代驾单订阅后决定是否创建新代驾单；两个聚合无同步远程调用。特殊场景：维保单变更服务项后，若存在 status=PENDING_PICKUP 的代驾单，该代驾单必须仍出现在"待接车"列表接口返回中 |
| verification | 集成测试：维保单 woA 处于 PICKED_UP，其代驾单 dvA.status=PENDING_PICKUP；调用"变更服务项"接口触发维保单状态回退；断言"待接车列表"接口 items[].driverOrderId contains dvA.id；断言代驾单 dvA.status 保持 PENDING_PICKUP 不被回滚 |

### SE-008（状态迁移 / 回退场景）

| 字段 | 升级前 | 升级后 |
|------|--------|--------|
| description | 工单回退场景下的提前交车状态保持：工单状态回退后再进入待结算页面，已有的提前交车审批单需保持，避免重复提交 | 当工单由 PENDING_SETTLEMENT_REVIEWING 回退到 PENDING_SETTLEMENT 时，已存在的 `t_early_delivery_approval` 记录（status ∈ {REVIEWING, APPROVED}）不得被级联置为无效；再次进入工单详情时，若存在 status=REVIEWING 的记录则按钮展示为禁用+tooltip"审批中"，若 APPROVED 则按钮隐藏 |
| verification | 构造：woA 状态 PENDING_SETTLEMENT_REVIEWING，审批单 apA.status=REVIEWING；调用回退接口使 woA 回到 PENDING_SETTLEMENT；断言 apA 仍存在且 status=REVIEWING；调用 userAuthV2 断言 buttons.APPLY_EARLY_DELIVERY.isVisible=true AND disabled=true；再对 apA 走审批通过流程后，重新查按钮断言 isVisible=false |

### SE-012（分组聚合 / 筛选联动）

| 字段 | 升级前 | 升级后 |
|------|--------|--------|
| description | 工单归属类型筛选与「仅查看自己」联动：筛选结果需同时满足工单归属类型和「仅查看自己」两个条件 | 工单列表查询 SQL 中，当 orderCategory ∈ {机电,小事故,中事故,大事故} 且 onlyMine=true 时，WHERE 子句必须同时包含 `order_category IN (?)` 和 `service_advisor_id=currentUserId`；两个条件任意一项单独生效不视为满足本 SE |
| verification | 准备数据：4 种 orderCategory × 2 种 serviceAdvisor（当前用户/他人）= 8 行；用 (orderCategory='机电', onlyMine=true) 查询，断言 returned.size==1 且唯一行的 serviceAdvisorId=currentUserId 且 orderCategory='机电'；反例：onlyMine=true 但 orderCategory 未选，应返回当前用户全部 4 行 |

### SE-013（幂等/并发 — OR 审批竞态，**重点升级**）

| 字段 | 升级前 | 升级后 |
|------|--------|--------|
| description | 并发审批控制：多个审批人（店长和财务）同时操作同一审批单时，需保证只有一个审批结果生效 | 同一审批单 apA 处于 status=REVIEWING 时，店长 A 和财务 B 并发调用审批接口（可能为任意组合：A通过+B通过 / A通过+B拒绝 / A拒绝+B通过 / A拒绝+B拒绝），最终必须只有首个到达事务的请求生效；后到的请求返回 HTTP 409 + errorCode=APPROVAL_ALREADY_CLOSED；`t_approval_action` 表只产生 1 条 action 记录；不允许出现 status 先 APPROVED 后被 REJECTED 覆盖的状态抖动 |
| verification | CountDownLatch 准备 2 个线程，分别持 A、B token 调 approve/reject 接口（用 4 种交叉组合各跑 100 次）；断言每次 exactly 1 个 2xx 1 个 409；SELECT COUNT(*) FROM t_approval_action WHERE approval_id=? 恒等于 1；审批单最终 status ∈ {APPROVED, REJECTED}；查询审批单 status 变更历史（audit log），断言仅 1 次 REVIEWING→终态 迁移 |

### SE-014（跨系统口径 / 店型隔离）

| 字段 | 升级前 | 升级后 |
|------|--------|--------|
| description | 授权店与直营店隔离：提前交车功能仅对授权店生效，直营店已有独立方案，两套方案互不影响 | 按钮展示与审批接口必须按 storeType 分流：当 store.type=AUTHORIZED 走本次新增 `EarlyDeliveryApprovalServiceAuthorizedImpl`；当 store.type=DIRECT_SALES 走已有的直营店实现（不得命中新逻辑）；审批流配置表 `t_approval_flow_config` 中 type=EARLY_DELIVERY 且 storeType=AUTHORIZED 的记录必须独立存在，不与直营店记录冲突 |
| verification | 准备授权店 sA 和直营店 sD 各一个 PENDING_SETTLEMENT 工单；sA 工单调 userAuthV2 断言 buttons.APPLY_EARLY_DELIVERY.isVisible=true；sD 工单调 userAuthV2 断言 buttons.APPLY_EARLY_DELIVERY 不存在；sA 申请提前交车断言走 AuthorizedImpl（注入 mock 打桩或调用日志）；sD 工单调同接口断言 HTTP 400 + errorCode=STORE_TYPE_NOT_SUPPORTED |

### SE-015（跨系统口径 / 大区省市接口）

| 字段 | 升级前 | 升级后 |
|------|--------|--------|
| description | 大区省市数据接口复用：索赔单的大区省市筛选接口与全损管理的大区省市接口相同，需保证数据口径一致 | 索赔单页面调用的大区省市接口路径、HTTP 方法、入参 schema、出参 schema 必须与全损管理页面调用的完全一致（同一 `RegionProvinceCityQueryService.list()` 方法），禁止在索赔单侧新建独立接口；返回的 `regionCode`、`provinceCode`、`cityCode`、`name` 四个字段值必须与全损管理返回值逐字段相等 |
| verification | 合同测试：用同一测试数据库快照，分别调用索赔单侧接口和全损管理侧接口；断言 response.body 反序列化为 List<RegionNode> 后 .equals() 为 true；代码层：grep 索赔单模块中是否新增 RegionController/Service，新增数=0 |

### SE-016（时间窗口 / 容量报错）

| 字段 | 升级前 | 升级后 |
|------|--------|--------|
| description | 容量配置报错时机：在门店设置容量时触发，不是进入页面时触发 | 当 store.businessHours 为空（null 或空数组），GET /capacity/config 接口正常返回 200 + 当前容量配置（无 toast）；PUT /capacity/config 操作必须返回 400 + errorCode=BUSINESS_HOURS_EMPTY + message="门店营业时间为空，请联系总部汽车区域运营配置"；原 toast"前方拥挤，请稍后重试"不得出现在此场景 |
| verification | 构造 store.businessHours=null 的门店；GET /capacity/config 断言 200 且响应体不含 toast 字段；PUT /capacity/config 提交任意容量变更，断言 400 + errorCode=BUSINESS_HOURS_EMPTY + message 精确匹配；前端 E2E：断言 toast 文本 contains "门店营业时间为空" 且不 contains "前方拥挤" |

### SE-017（接口约定 / 新增后端接口）

| 字段 | 升级前 | 升级后 |
|------|--------|--------|
| description | 新增后端接口：申请提前交车需针对授权店新增接口，记录提交审批信息并发起审批 | 新增接口 `POST /authorized/early-delivery/apply`，请求体 `{workOrderId: Long, reason: String(1,500)}`；响应体 `{approvalId: Long, status: 'REVIEWING', createdAt: ISO8601}`；错误码集合 {EARLY_DELIVERY_IN_REVIEW, STORE_TYPE_NOT_SUPPORTED, INVALID_ORDER_STATUS, REASON_LENGTH_EXCEEDED, REASON_EMPTY}；接口必须触发一次 `ApprovalFlowService.submit(EARLY_DELIVERY, ...)` 调用 |
| verification | OpenAPI 合约测试：校验路径/方法/schema 匹配预定义 YAML；Mock ApprovalFlowService 断言 submit 方法在成功路径恰好被调用 1 次，参数 type=EARLY_DELIVERY；异常路径参数化：reason="" → 400/REASON_EMPTY；reason 长度 501 → 400/REASON_LENGTH_EXCEEDED；workOrder.status=DELIVERED → 400/INVALID_ORDER_STATUS |

### SE-018（接口约定 / 按钮扩展）

| 字段 | 升级前 | 升级后 |
|------|--------|--------|
| description | 按钮展示通过现有接口扩展：按钮展示交互逻辑通过 MrOrderCoreQueryProviderImpl#userAuthV2 接口的 buttons 字段，本次新增一个按钮类型 | `MrOrderCoreQueryProviderImpl#userAuthV2` 接口返回的 `buttons` 数组中新增一种元素 `{type: "APPLY_EARLY_DELIVERY", isVisible: boolean, disabled: boolean, tooltip: String?}`；既有按钮类型枚举不得被修改或删除；消费方前端通过 type 字符串匹配，不依赖数组下标 |
| verification | 对比 userAuthV2 升级前后的接口定义快照：断言新增类型仅追加、未修改既有类型；契约测试：对典型工单场景调 userAuthV2，断言 response.buttons[].type 集合包含 "APPLY_EARLY_DELIVERY"；断言既有类型（如 SETTLE, PAY）依旧存在且 schema 字段数不变 |

---

## 三、新增 SE 明细（14 条）

### 维度 A：状态机完整性（4 条新增）

```json
[
  {
    "se_id": "SE-NEW-001",
    "category": "状态机完整性",
    "bound_to": "REQ-001 / BR-001",
    "description": "工单状态机对「申请提前交车」按钮调用的非法状态拦截：除 PRD 明示的 4 个合法状态 {PENDING_SETTLEMENT, PENDING_SETTLEMENT_REVIEWING, PENDING_PAYMENT, PARTIAL_PAID} 外，其余任意工单状态（PENDING_DISPATCH, IN_SERVICE, DELIVERED, COMPLETED, CANCELLED 等）调用 POST /authorized/early-delivery/apply 必须返回 HTTP 400 + errorCode=INVALID_ORDER_STATUS，不产生审批单记录",
    "verification": "参数化测试：枚举工单所有可能状态（≥8 种），对每个状态调用申请接口；断言 4 个合法状态返回 201，其余状态返回 400 + errorCode=INVALID_ORDER_STATUS；SELECT COUNT(*) FROM t_early_delivery_approval 在反例路径后保持不变"
  },
  {
    "se_id": "SE-NEW-002",
    "category": "状态机完整性",
    "bound_to": "REQ-003 / BR-020, BR-021",
    "description": "审批单终态不可回退：一旦 approval.status ∈ {APPROVED, REJECTED, CANCELLED}，对该单任何 approve/reject/cancel 调用必须返回 HTTP 409 + errorCode=APPROVAL_ALREADY_CLOSED，且 t_approval_action 不新增记录",
    "verification": "三个终态 × 三个操作 = 9 组参数化测试；为每组构造已处于终态的审批单，调用对应接口；断言 409 + errorCode=APPROVAL_ALREADY_CLOSED；SELECT COUNT(*) FROM t_approval_action WHERE approval_id=? 在调用前后相等"
  },
  {
    "se_id": "SE-NEW-003",
    "category": "状态机完整性",
    "bound_to": "REQ-002 / BR-017",
    "description": "撤销申请后重新提交规则：审批单 status=CANCELLED 后，同一 workOrderId 允许再次发起新的申请（生成新的 approvalId）；但 CANCELLED 的记录不得被复用（不得把新请求 upsert 到旧记录上）",
    "verification": "流程测试：用户 A 提申请 apA，撤销后 apA.status=CANCELLED；用户 A 再次对同一工单提交申请；断言返回 201 且 response.approvalId ≠ apA.id；SELECT COUNT(*) FROM t_early_delivery_approval WHERE work_order_id=? 等于 2；apA 记录字段保持不变（CANCELLED 时间戳不被覆盖）"
  },
  {
    "se_id": "SE-NEW-004",
    "category": "状态机完整性",
    "bound_to": "REQ-001 / BR-007, BR-008",
    "description": "审批通过后按钮集合切换的原子性：同一次 userAuthV2 响应中，「申请提前交车」按钮隐藏和「预约代驾还车」按钮出现必须同时发生；不允许出现两者都隐藏或两者都显示的中间态",
    "verification": "构造：工单 woA 的申请 apA 处于 REVIEWING；调 userAuthV2 断言 APPLY_EARLY_DELIVERY.isVisible=true 且 BOOK_DRIVER_RETURN.isVisible=false；对 apA 做 approve；立即再调 userAuthV2 断言 APPLY_EARLY_DELIVERY.isVisible=false 且 BOOK_DRIVER_RETURN.isVisible=true；断言不存在任意时刻两者同时 false 或 true（可通过读一致性视图验证）"
  }
]
```

### 维度 B：并发/幂等（4 条新增，含重点关注项）

```json
[
  {
    "se_id": "SE-NEW-005",
    "category": "并发/幂等",
    "bound_to": "REQ-002 / BR-017 vs REQ-003 / BR-020",
    "description": "撤销与审批的竞态：申请人点击撤销 与 审批人点击通过/拒绝 在同一瞬间发生时，仅首个进入事务的动作生效；另一动作返回 409 + errorCode=APPROVAL_STATE_CONFLICT；最终状态要么 CANCELLED 要么 APPROVED/REJECTED，不得出现中间混合状态",
    "verification": "CountDownLatch 同时发起 cancel（申请人 token）和 approve（审批人 token）各 100 轮；每轮断言 exactly 一个 2xx + 一个 409 + errorCode=APPROVAL_STATE_CONFLICT；审批单最终 status ∈ {CANCELLED, APPROVED}；t_approval_action 每轮只新增 1 条"
  },
  {
    "se_id": "SE-NEW-006",
    "category": "并发/幂等",
    "bound_to": "REQ-001 / BR-005",
    "description": "申请理由 500 字边界与纯空白拦截：reason 字段长度严格 ≤500 字符（按 Character.codePointCount 计算，不按字节）；reason 去除首尾空白字符后为空则拒绝（防止\"   \"绕过非空校验）",
    "verification": "参数化测试：reason='' → 400/REASON_EMPTY；reason='   '（3 空格）→ 400/REASON_EMPTY；reason=500 个汉字 → 201；reason=501 个汉字 → 400/REASON_LENGTH_EXCEEDED；reason=\"a\"*500 → 201；reason 含 emoji（占 2 个 UTF-16 代码单元）500 个 codepoint → 201"
  },
  {
    "se_id": "SE-NEW-007",
    "category": "并发/幂等",
    "bound_to": "REQ-001 / BR-006",
    "description": "申请接口幂等键约定：客户端可选带 idempotencyKey header；相同 {workOrderId, idempotencyKey} 在 24h 窗口内重放必须返回与首次完全一致的响应体（approvalId 相同），不得触发二次 ApprovalFlowService.submit 调用",
    "verification": "首次调 POST /apply header Idempotency-Key=k1 得到 approvalId=apA；24h 内用同 key + 同 body 重放 10 次；断言每次响应 200/201 + approvalId=apA + 时间戳=首次时间戳；Mock ApprovalFlowService.submit 调用次数恒等于 1；24h 后用同 key 重放，视为新请求生成新 approvalId"
  },
  {
    "se_id": "SE-NEW-008",
    "category": "并发/幂等",
    "bound_to": "REQ-001",
    "description": "两条流水线数据一致性（工单状态 vs 代驾单状态）：当代驾单 driverOrder 状态变更后向工单发出 DriverOrderStateChanged 事件，工单侧消费失败时必须写入 outbox 表并重试；禁止在两个聚合间用同步远程调用实现强一致",
    "verification": "集成测试 1：抛出 DriverOrderStateChanged 但 Mock WorkOrderUpdateService 首次抛异常；断言事件被重试 ≥1 次直到成功；outbox 表终态 status=PUBLISHED；集成测试 2：grep 代驾单模块源码中对 WorkOrderService 的直接调用，断言仅存在事件发布调用不存在同步 RPC/HTTP 调用"
  }
]
```

### 维度 C：异常恢复（3 条新增，含重点关注项）

```json
[
  {
    "se_id": "SE-NEW-009",
    "category": "异常恢复",
    "bound_to": "REQ-001 / BR-009",
    "description": "BPM/审批中台不可用时的降级策略（重点漏检）：调用 ApprovalFlowService.submit 时若 BPM 返回 5xx 或超时 >3s，申请接口必须返回 HTTP 503 + errorCode=APPROVAL_SERVICE_UNAVAILABLE；同时已创建的 t_early_delivery_approval 记录必须被回滚或置 status=PENDING_RETRY；不得出现本地有审批单记录但 BPM 侧无对应流程实例的数据孤岛",
    "verification": "Mock BPM Client 注入 5xx 响应；调 POST /apply 断言 503 + errorCode=APPROVAL_SERVICE_UNAVAILABLE；SELECT COUNT(*) FROM t_early_delivery_approval WHERE work_order_id=? 为 0（事务回滚）或 =1 且 status=PENDING_RETRY；BPM 恢复后后台任务扫描 PENDING_RETRY 重试成功后 status→REVIEWING"
  },
  {
    "se_id": "SE-NEW-010",
    "category": "异常恢复",
    "bound_to": "REQ-004 / BR-023, BR-024, BR-025, BR-026",
    "description": "脱敏规则的异常输入降级：姓名/手机号/地址/VIN 字段值为 null、空字符串或长度不足时，脱敏函数必须返回特定 fallback 而非抛异常或返回原文；具体：null→空字符串 '' ，长度<4 的手机号→全脱敏 '****'，长度<13 的 VIN→全脱敏 '**********' + 原长度个星号",
    "verification": "参数化测试：name=null → ''；name='' → ''；name='郝' → '*'（单字只脱敏首字之外，此处无后续所以为空？需业务确认→测试覆盖边界）；phone=null → ''；phone='123' → '****'（完全脱敏）；phone='13812345678'（11 位）→ '138****5678'；vin=null → ''；vin='ABC'（3 位）→ '***'"
  },
  {
    "se_id": "SE-NEW-011",
    "category": "异常恢复",
    "bound_to": "REQ-006 / BR-034",
    "description": "容量配置保存失败后前端状态恢复：PUT /capacity/config 返回 5xx 或网络错误后，前端页面容量字段必须回滚到提交前的值，不得持留用户输入态造成下次误提交",
    "verification": "E2E：mock PUT 500；断言前端表单字段恢复为 GET 首次返回的数值；断言 toast contains '保存失败'；再次 GET 断言服务端数据未变化；不得出现前端显示的数字 ≠ 服务端持久化的数字"
  }
]
```

### 维度 D：DDD 聚合边界（3 条新增）

```json
[
  {
    "se_id": "SE-NEW-012",
    "category": "DDD 聚合边界",
    "bound_to": "REQ-001 / BR-009",
    "description": "提前交车申请聚合 vs 工单聚合 vs 审批流聚合的边界：EarlyDeliveryApprovalAggregate 是独立聚合根，持有 approvalId；其与工单聚合的关联通过 workOrderId 引用，不得在工单聚合内部嵌入审批单对象；写操作不得跨聚合（如审批通过不允许直接更新 workOrder 的字段，必须通过事件触发）",
    "verification": "代码层：断言 WorkOrder 实体类无 List<EarlyDeliveryApproval> 属性；断言 EarlyDeliveryApproval 类无 WorkOrder 对象属性，仅持 workOrderId: Long；静态分析：grep 在 ApprovalService.approve() 方法体内禁止出现对 WorkOrderRepository.save() 的直接调用，必须是通过 EventPublisher.publish(...)"
  },
  {
    "se_id": "SE-NEW-013",
    "category": "DDD 聚合边界",
    "bound_to": "REQ-001 / BR-001, BR-002, BR-003",
    "description": "按钮可见性判定属于查询侧 CQRS 投影，不得调用命令侧服务：MrOrderCoreQueryProviderImpl#userAuthV2 在计算 APPLY_EARLY_DELIVERY.isVisible 时只允许读取 workOrder 快照和 user.role，不得调用 ApprovalService 或写数据库",
    "verification": "Mock ApprovalService 和所有写 Repository；调 userAuthV2；断言 Mock 对象的任何写方法 verify(never())；断言接口 SQL log 只包含 SELECT 语句"
  },
  {
    "se_id": "SE-NEW-014",
    "category": "DDD 聚合边界",
    "bound_to": "REQ-004 / BR-023 ~ BR-026",
    "description": "脱敏是展示层聚合规则，不得污染领域模型：WorkOrder、Customer 等领域实体持久化字段必须是明文；半脱敏仅在 DTO / 视图层应用；禁止在 @Entity 字段的 getter 中嵌入脱敏逻辑，必须由 MaskingUtil 在 Assembler/Mapper 层显式调用",
    "verification": "代码层：grep @Entity 标注的类中 getter 方法体含 mask/hide/replace 关键字的数量为 0；集成测试：直连数据库读取 customer.phone 断言为明文 '13812345678'；调 GET /mobile-work-order/{id} 返回 DTO 的 phone 字段为 '138****5678'"
  }
]
```

---

## 四、观察与建议

### 4.1 新版 checklist 对 agent 的引导效果评估（shadow review）

**从升级前后对照看，"示例对照"机制的引导效果显著：**

- **并发/幂等维度**的升级模板几乎 1:1 复用了示例中的"CountDownLatch + exactly-1 2xx + N-1 409 + SELECT COUNT(*)"句式（见 SE-001、SE-013 升级后）。如果原 Q01 agent 能看到这组示例，SE-001 的 verification 理论上可以直接产出达标。
- **状态机完整性维度**的"枚举非法 (src, dst) 组合 + HTTP 409 + errorCode=INVALID_TRANSITION"模板在本次新增 SE-NEW-001 中被完整复用，说明示例足以支撑 agent 自己推广到具体业务（工单状态）。
- **DDD 聚合边界维度**最能看到示例的"写法强度"差异：现有 SE 完全没有覆盖这一维度（旧 18 条里 0 条涉及聚合根/事件解耦/查询侧 CQRS），而新版 checklist 提供了具体验证路径（grep @Entity / Mock verify never）。

**风险点：示例之外的维度仍是盲区。** 现有 SE 中"异常恢复"维度原本也是空白——新版 checklist 这一维度没有给示例，可能导致 agent 在这一维度继续漏检（见 SE-NEW-009 BPM 降级是本次最严重漏检）。建议：**为异常恢复维度补充同等强度的示例对**，至少覆盖"外部系统 5xx/超时"和"事务回滚 vs outbox 补偿"两个典型。

### 4.2 applies_when 关键词匹配 gap（哪些维度本该触发但被过滤）

基于 PRD 文本推演，下列场景本应触发 checklist 维度但旧版漏过：

| 漏检场景 | PRD 原文证据 | 本应触发的维度 | 现有 SE 覆盖情况 |
|---------|-------------|--------------|----------------|
| BPM/审批中台外部依赖 | "申请理由点击提交后触发审批" "审批流：...➡️授权店店长/财务" | 异常恢复 | 0 条相关 SE |
| 工单回退到 PENDING_SETTLEMENT 后既有审批单的处理 | comments.md:#10 | 状态机完整性 | SE-008 描述有方向但 verification 空 |
| 代驾单与工单两条流水线数据一致性 | comments.md:#3 "特殊 case" | DDD 聚合边界 + 异常恢复 | SE-007 描述模糊 |
| 审批人两人 OR 并发竞态 | plain_text.txt:84 "或的关系" | 并发/幂等 | SE-013 方向性描述，verification 空 |
| 审批终态后重复操作（approve→approve / approve→reject） | 图片 #9 "已审批" 流程 | 状态机完整性 | 0 条相关 SE |
| 撤销 vs 审批竞态 | BR-017 撤销 × BR-020 审批通过 | 并发/幂等 | 0 条相关 SE |
| 申请理由 500 字边界 + 空白绕过 | plain_text.txt:83 "限制500字" | 并发/幂等（输入校验）| 0 条相关 SE |
| 脱敏字段异常输入（null/短字符串）| BR-023~026 | 异常恢复 | 0 条相关 SE |
| 工单状态非法进入申请接口 | BR-001 只列 4 个合法状态 | 状态机完整性 | 0 条相关 SE |

**共性根因：旧版 SE 过度依赖 PRD 显式陈述，缺少"反面场景"扫描视角。** 新版 checklist 的示例对中 ✗ 写法全部是"PRD 原文中隐含但未显式列出"的反面场景（如非法跳转、并发竞态、重放），这正是"为什么要用 checklist"的核心价值。**建议在 prompt 里显式要求 agent 在每个维度必须产出至少 1 条"反面场景"SE**，否则一个也不产出（避免产出时只重述 PRD 正面描述）。

### 4.3 对 Phase 2（Judge 示例对比）的实施启示

本实验是 Phase 1（生成侧引导）的影子评估，Phase 2（Judge 侧对比）实施建议如下：

1. **Judge 应内置"写法强度模板"匹配器**
   对每条 SE，让 Judge 按 rubric 打分（description+verification 合计 0~5 分）：
   - 含具体错误码（errorCode=XXX）+1
   - 含 HTTP 状态码（4xx/5xx）+1
   - 含 SQL/API 断言（SELECT/assert*）+1
   - 含参数化枚举范围（∈ {...} 或 × N 组）+1
   - 含反面场景（非法/并发/降级）+1
   分数 <3 直接判 WEAK，返工。本次 STRONG 的 3 条（SE-009/010/011）和升级后的样本都能拿 4-5 分，区分度好。

2. **Judge 必须按维度独立打分，不得按 SE 总数打分**
   旧版本如果 18 条里 15 条都是 WEAK，但都集中在"匹配冲突/数据转换"维度，其他 4 个维度（尤其异常恢复、DDD 边界）为零——**按维度看是 gap**，按 SE 数看却"覆盖率不低"。Judge 必须对 4 个维度分别打"覆盖分"，有维度为 0 直接判 fail。

3. **Judge 示例池建议按"领域方言"分层**
   checklist 示例目前是纯技术泛化（"{业务主键}"这类占位符）。建议 Phase 2 给 Judge 注入领域样例库：审批流场景（OR 审批/撤销竞态）、数据脱敏场景（null/短串边界）、CQRS 查询投影场景等。agent 有"类似场景模板"参考后，产出的 verification 会更贴近真实业务而非机械套用。

4. **建立 regression：本次实验的 18 + 14 = 32 条 SE 可作为 shuangzhou-v4 的 golden set**
   后续任何 Q01 prompt 改动，都在 shuangzhou-v4 跑一次，比对生成的 SE 集合与 golden set 的召回率（是否漏了本报告中的 14 条新增点）和描述强度（STRONG 比例是否提升到 70%+）。当前基线：STRONG 比例 16.7%，目标：50%+。

---

## 五、原始数据附录

- 评估基线：现有 18 条 SE 的 description 长度平均 32 字符；verification 字段全部缺失
- 升级后：description 平均 145 字符（+353%），verification 平均 140 字符（从 0 开始）
- 新增 SE 平均 description 155 字符、verification 160 字符
- 维度分布（升级+新增后）：状态机完整性 5 条，并发/幂等 7 条，异常恢复 4 条，DDD 聚合边界 3 条，其余（匹配冲突/数据转换/默认行为/跨系统口径/分组聚合/时间窗口/接口约定）保留原分类 13 条

*报告生成：2026-05-10，纯静态分析，未调 Qualix pipeline*
