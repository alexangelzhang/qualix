# Q01 推理日志

### Step 1 输入确认

读取 `artifacts/parts-outbound/manifest.json`，确认本次 Q01 的 PRD 主输入为 `input/prd.md`，图片目录为 `input/prd_source/static`，补充知识库为本地维保服务知识库。`input/scope.md` 明确约束：Q01 核心关注 6.6 工单相关修改，6.2 门店计划仅作为推理参考，不覆盖 PRD 原文证据。

### Step 2 阶段规则确认

读取 `skills/q01-requirement-structuring/SKILL.md`、`references/q01-structuring-rules.md`、`references/phase-personas-and-principles.md` 和 `references/quality-objectives.md`。本阶段只输出 REQ、BR、SE、GAP、OPEN，不输出 EUT、测试设计或代码建议。所有结论必须带 PRD 行号证据。

### Step 3 证据采集

主证据集中在 `prd.md:119` 到 `prd.md:157`：章节标题为“工单相关修改”，包含“支持编辑小数配件”和“支持展示小数配件”两组规则。评论证据补充了预授权入口、门店交付报价、配件使用数量即最大可退数量、组套多配件文案、默认值仍为 1、押金延期二期和提前交车不编辑等判断。

### Step 4 范围决策

将 `prd.md:139` 拆成编辑、精度、步长、退款、单价校验、拦截文案多条 BR，避免一条规则吞掉多个可验证分支。将 `prd.md:151` 到 `prd.md:157` 拆成展示范围、页面覆盖和押金二期范围控制。`prd.md:184` 只进入 REQ-005 作为参考背景，避免 Q01 主范围越界到门店计划算法。

### Step 5 不确定项处理

预授权入口需要区分工单入口和质量技术入口，但 PRD 未给出字段或枚举，因此沉淀为 OPEN-001。展示范围中多个页面缺少字段清单，因此沉淀为 GAP-001。押金和提前交车被标记延期到二期，但一期代码处理方式未明确，因此沉淀为 OPEN-002。

### Step 6 自检

确认未输出测试设计或 EUT。REQ/BR/SE 均有 `prd.md:行号` 证据；BR 保留了小数出库标记、两位小数、步长固定 1、退款上限、仅允许全额退款、整数使用数量维持部分退款、前后端整数单价校验、拦截文案和二期排除等规则。GAP 有 risk_level 和 required_clarification；OPEN 均有 decision_owner。

### Step 7 批评者复查

重点复查了容易遗漏的异常与边界：小数使用数量退款不可编辑、整数使用数量不能误伤、后端不可被绕过、服务项组套多配件提示、押金二期隔离、预授权来源区分、6.2 售前工单剔除仅作为背景。结论为可以进入 validator 校验，若 validator 报 source 相关问题再修正证据行号或描述。
