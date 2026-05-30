# Q05a Reasoning Log

### Step 1: Baseline 校准

检查 `origin/master...HEAD` 时只发现测试文件变更，`build_code_index.py` 产出 0 个生产 diff 文件。为避免 Q05a 误判无生产逻辑，本阶段改用 `origin/feature_init...HEAD`，重新生成 code_index，得到 108 个真实生产 Java diff 和 101 个当前类。

### Step 2: 代码阅读结论

核心推荐链路为 DispatchRecommendDomainServiceImpl -> DispatchStrategyOrchestrator -> DispatchScenarioPlanResolver。普通智能派单走基础信息、证书、请假、负荷、距离梯队、概率排序；VIP 派单跳过距离梯队，走高阶等级过滤和最小饱和度选择。负荷配置集中在 WorkloadConfigServiceImpl 和 EngineerSaturationCalculateFillStrategy。

### Step 3: Diff 分类

纳入 EUT 的文件共 44 个，包含所有有变更分支的方法和关键推荐/配置协作者。排除 64 个文件，主要是已删除旧类、DTO/model/interface/mapper、启动/协议适配和无业务分支文件。删除旧类不作为 Q05b 单测目标，但其替代链路已经通过新 asign 包 EUT 覆盖。

### Step 4: 分支绑定

branch_inventory 共 165 个方法目标，553 个分支后果。复杂方法按 code_index 的 line_count、branch_signal_count 和 complex_reasons 标记，最少场景数不低于 build_code_index 估算。

### Step 5: 不可测项处理

CDP/VIP 标签识别、PC/App UI、菜单、工作流释放节点、地图慧同步和容量合同指标没有当前 Java 实现证据，因此未伪造 EUT，统一记录在 non_testable_items。

### Step 6: 类到 EUT 覆盖

每个 included_diff_files 中的类均至少出现在一个 EUT 的 given/when 中。核心类 DispatchRecommendDomainServiceImpl、DispatchScenarioPlanResolver、EngineerSaturationCalculateFillStrategy、EngineerProbabilityRankStrategy、WorkloadConfigServiceImpl、DispatchCandidateGatewayImpl 均有 Happy/Exception/Boundary EUT。
