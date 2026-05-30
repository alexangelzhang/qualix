# Q06 reasoning log - smart-dispatch

### Step 1 输入读取

- 读取 `q01/structured.json`、`q05a/eut_matrix.json`、`q05b/code_status.json`。
- Q06 仅审计，不修改 Q05a、Q05b 或 Java 测试代码。

### Step 2 测试文件清单

1. `/Users/zhangyiqian/private-dev/asp-dispatch-service-private_0528/asp-dispatch-service/dispatch-api/src/test/java/com/mi/asp/dispatch/api/constant/DispatchAssignFailReasonEnumQ05bTest.java` - EUT 4 个，测试方法 4 个，示例：EUT-001, EUT-002, EUT-003, EUT-004
2. `/Users/zhangyiqian/private-dev/asp-dispatch-service-private_0528/asp-dispatch-service/dispatch-app/src/test/java/com/mi/asp/dispatch/convert/DispatchRecommendConvertQ05bTest.java` - EUT 1 个，测试方法 1 个，示例：EUT-639
3. `/Users/zhangyiqian/private-dev/asp-dispatch-service-private_0528/asp-dispatch-service/dispatch-app/src/test/java/com/mi/asp/dispatch/service/asign/DispatchRecommendEngineerProviderImplTest.java` - EUT 1 个，测试方法 3 个，示例：EUT-640
4. `/Users/zhangyiqian/private-dev/asp-dispatch-service-private_0528/asp-dispatch-service/dispatch-app/src/test/java/com/mi/asp/dispatch/service/asign/DispatchRecommendRpcAppServiceTest.java` - EUT 17 个，测试方法 12 个，示例：EUT-005, EUT-006, EUT-007, EUT-008, EUT-009, EUT-010, EUT-011, EUT-012
5. `/Users/zhangyiqian/private-dev/asp-dispatch-service-private_0528/asp-dispatch-service/dispatch-app/src/test/java/com/mi/asp/dispatch/service/config/EngineerWorkloadConfigProviderImplTest.java` - EUT 12 个，测试方法 31 个，示例：EUT-019, EUT-020, EUT-021, EUT-022, EUT-023, EUT-024, EUT-025, EUT-026
6. `/Users/zhangyiqian/private-dev/asp-dispatch-service-private_0528/asp-dispatch-service/dispatch-domain/src/test/java/com/mi/asp/dispatch/domain/asign/convert/RecommendEngineerResultConvertTest.java` - EUT 1 个，测试方法 2 个，示例：EUT-641
7. `/Users/zhangyiqian/private-dev/asp-dispatch-service-private_0528/asp-dispatch-service/dispatch-domain/src/test/java/com/mi/asp/dispatch/domain/asign/service/impl/DispatchRecommendDomainServiceImplTest.java` - EUT 22 个，测试方法 7 个，示例：EUT-037, EUT-038, EUT-039, EUT-040, EUT-041, EUT-042, EUT-043, EUT-044
8. `/Users/zhangyiqian/private-dev/asp-dispatch-service-private_0528/asp-dispatch-service/dispatch-domain/src/test/java/com/mi/asp/dispatch/domain/asign/strategy/DispatchStrategyOrchestratorTest.java` - EUT 3 个，测试方法 2 个，示例：EUT-054, EUT-055, EUT-056
9. `/Users/zhangyiqian/private-dev/asp-dispatch-service-private_0528/asp-dispatch-service/dispatch-domain/src/test/java/com/mi/asp/dispatch/domain/asign/strategy/fill/EngineerSaturationCalculateFillStrategyTest.java` - EUT 87 个，测试方法 8 个，示例：EUT-057, EUT-058, EUT-059, EUT-060, EUT-061, EUT-062, EUT-063, EUT-064
10. `/Users/zhangyiqian/private-dev/asp-dispatch-service-private_0528/asp-dispatch-service/dispatch-domain/src/test/java/com/mi/asp/dispatch/domain/asign/strategy/filter/AbstractDispatchFilterStrategyQ05bTest.java` - EUT 5 个，测试方法 5 个，示例：EUT-127, EUT-128, EUT-129, EUT-130, EUT-131
11. `/Users/zhangyiqian/private-dev/asp-dispatch-service-private_0528/asp-dispatch-service/dispatch-domain/src/test/java/com/mi/asp/dispatch/domain/asign/strategy/filter/EngineerBasicInfoFilterStrategyTest.java` - EUT 7 个，测试方法 2 个，示例：EUT-132, EUT-133, EUT-134, EUT-135, EUT-136, EUT-137, EUT-138
12. `/Users/zhangyiqian/private-dev/asp-dispatch-service-private_0528/asp-dispatch-service/dispatch-domain/src/test/java/com/mi/asp/dispatch/domain/asign/strategy/filter/EngineerCertificateFilterStrategyQ05bTest.java` - EUT 9 个，测试方法 4 个，示例：EUT-139, EUT-140, EUT-141, EUT-142, EUT-143, EUT-144, EUT-145, EUT-146
13. `/Users/zhangyiqian/private-dev/asp-dispatch-service-private_0528/asp-dispatch-service/dispatch-domain/src/test/java/com/mi/asp/dispatch/domain/asign/strategy/filter/EngineerHolidayFilterStrategyTest.java` - EUT 2 个，测试方法 2 个，示例：EUT-148, EUT-149
14. `/Users/zhangyiqian/private-dev/asp-dispatch-service-private_0528/asp-dispatch-service/dispatch-domain/src/test/java/com/mi/asp/dispatch/domain/asign/strategy/filter/EngineerLevelFilterStrategyTest.java` - EUT 2 个，测试方法 2 个，示例：EUT-150, EUT-151
15. `/Users/zhangyiqian/private-dev/asp-dispatch-service-private_0528/asp-dispatch-service/dispatch-domain/src/test/java/com/mi/asp/dispatch/domain/asign/strategy/filter/EngineerOverloadFilterStrategyTest.java` - EUT 12 个，测试方法 4 个，示例：EUT-152, EUT-153, EUT-154, EUT-155, EUT-156, EUT-157, EUT-158, EUT-568
16. `/Users/zhangyiqian/private-dev/asp-dispatch-service-private_0528/asp-dispatch-service/dispatch-domain/src/test/java/com/mi/asp/dispatch/domain/asign/strategy/plan/DispatchScenarioPlanResolverTest.java` - EUT 12 个，测试方法 3 个，示例：EUT-159, EUT-555, EUT-582, EUT-583, EUT-584, EUT-585, EUT-586, EUT-587
17. `/Users/zhangyiqian/private-dev/asp-dispatch-service-private_0528/asp-dispatch-service/dispatch-domain/src/test/java/com/mi/asp/dispatch/domain/asign/strategy/rank/EngineerProbabilityRankStrategyTest.java` - EUT 42 个，测试方法 9 个，示例：EUT-160, EUT-161, EUT-162, EUT-163, EUT-164, EUT-165, EUT-166, EUT-167
18. `/Users/zhangyiqian/private-dev/asp-dispatch-service-private_0528/asp-dispatch-service/dispatch-domain/src/test/java/com/mi/asp/dispatch/domain/asign/strategy/select/DistanceTierSelectStrategyTest.java` - EUT 6 个，测试方法 4 个，示例：EUT-190, EUT-191, EUT-192, EUT-193, EUT-620, EUT-621
19. `/Users/zhangyiqian/private-dev/asp-dispatch-service-private_0528/asp-dispatch-service/dispatch-domain/src/test/java/com/mi/asp/dispatch/domain/asign/strategy/select/SaturationMinSelectStrategyTest.java` - EUT 4 个，测试方法 3 个，示例：EUT-194, EUT-195, EUT-196, EUT-197
20. `/Users/zhangyiqian/private-dev/asp-dispatch-service-private_0528/asp-dispatch-service/dispatch-domain/src/test/java/com/mi/asp/dispatch/domain/config/convert/EngineerLevelConvertQ05bTest.java` - EUT 27 个，测试方法 8 个，示例：EUT-031, EUT-032, EUT-033, EUT-034, EUT-035, EUT-036, EUT-198, EUT-199
21. `/Users/zhangyiqian/private-dev/asp-dispatch-service-private_0528/asp-dispatch-service/dispatch-domain/src/test/java/com/mi/asp/dispatch/domain/config/service/impl/WorkloadConfigServiceImplTest.java` - EUT 148 个，测试方法 83 个，示例：EUT-216, EUT-217, EUT-218, EUT-219, EUT-220, EUT-221, EUT-222, EUT-223
22. `/Users/zhangyiqian/private-dev/asp-dispatch-service-private_0528/asp-dispatch-service/dispatch-infrastructure/src/test/java/com/mi/asp/dispatch/infrastructure/asign/convert/CandidateEngineerConvertTest.java` - EUT 4 个，测试方法 4 个，示例：EUT-348, EUT-349, EUT-350, EUT-351
23. `/Users/zhangyiqian/private-dev/asp-dispatch-service-private_0528/asp-dispatch-service/dispatch-infrastructure/src/test/java/com/mi/asp/dispatch/infrastructure/asign/convert/EngineerBasicInfoConvertTest.java` - EUT 4 个，测试方法 4 个，示例：EUT-352, EUT-353, EUT-354, EUT-355
24. `/Users/zhangyiqian/private-dev/asp-dispatch-service-private_0528/asp-dispatch-service/dispatch-infrastructure/src/test/java/com/mi/asp/dispatch/infrastructure/asign/convert/ServiceItemConvertTest.java` - EUT 4 个，测试方法 4 个，示例：EUT-356, EUT-357, EUT-358, EUT-359
25. `/Users/zhangyiqian/private-dev/asp-dispatch-service-private_0528/asp-dispatch-service/dispatch-infrastructure/src/test/java/com/mi/asp/dispatch/infrastructure/asign/gateway/DispatchCandidateGatewayImplTest.java` - EUT 19 个，测试方法 4 个，示例：EUT-360, EUT-361, EUT-362, EUT-363, EUT-364, EUT-365, EUT-366, EUT-367
26. `/Users/zhangyiqian/private-dev/asp-dispatch-service-private_0528/asp-dispatch-service/dispatch-infrastructure/src/test/java/com/mi/asp/dispatch/infrastructure/asign/gateway/DispatchEngineerBasicInfoGatewayImplTest.java` - EUT 3 个，测试方法 4 个，示例：EUT-368, EUT-369, EUT-370
27. `/Users/zhangyiqian/private-dev/asp-dispatch-service-private_0528/asp-dispatch-service/dispatch-infrastructure/src/test/java/com/mi/asp/dispatch/infrastructure/asign/gateway/DispatchEngineerCertificateGatewayImplTest.java` - EUT 3 个，测试方法 5 个，示例：EUT-371, EUT-372, EUT-373
28. `/Users/zhangyiqian/private-dev/asp-dispatch-service-private_0528/asp-dispatch-service/dispatch-infrastructure/src/test/java/com/mi/asp/dispatch/infrastructure/asign/gateway/DispatchEngineerHolidayGatewayImplTest.java` - EUT 5 个，测试方法 3 个，示例：EUT-374, EUT-375, EUT-376, EUT-377, EUT-378
29. `/Users/zhangyiqian/private-dev/asp-dispatch-service-private_0528/asp-dispatch-service/dispatch-infrastructure/src/test/java/com/mi/asp/dispatch/infrastructure/asign/gateway/DispatchEngineerUnfinishedTaskGatewayImplTest.java` - EUT 23 个，测试方法 5 个，示例：EUT-379, EUT-380, EUT-381, EUT-382, EUT-383, EUT-384, EUT-385, EUT-386
30. `/Users/zhangyiqian/private-dev/asp-dispatch-service-private_0528/asp-dispatch-service/dispatch-infrastructure/src/test/java/com/mi/asp/dispatch/infrastructure/asign/gateway/DispatchServiceItemCategoryGatewayImplTest.java` - EUT 3 个，测试方法 3 个，示例：EUT-402, EUT-403, EUT-404
31. `/Users/zhangyiqian/private-dev/asp-dispatch-service-private_0528/asp-dispatch-service/dispatch-infrastructure/src/test/java/com/mi/asp/dispatch/infrastructure/config/convert/InfrastructureUtilityQ05bTest.java` - EUT 16 个，测试方法 5 个，示例：EUT-405, EUT-406, EUT-407, EUT-408, EUT-409, EUT-410, EUT-411, EUT-412
32. `/Users/zhangyiqian/private-dev/asp-dispatch-service-private_0528/asp-dispatch-service/dispatch-infrastructure/src/test/java/com/mi/asp/dispatch/infrastructure/config/datasource/DispatchSlaveReadAspectQ05bTest.java` - EUT 1 个，测试方法 1 个，示例：EUT-419
33. `/Users/zhangyiqian/private-dev/asp-dispatch-service-private_0528/asp-dispatch-service/dispatch-infrastructure/src/test/java/com/mi/asp/dispatch/infrastructure/config/gateway/CategoryGatewayImplTest.java` - EUT 12 个，测试方法 34 个，示例：EUT-420, EUT-421, EUT-422, EUT-423, EUT-424, EUT-425, EUT-426, EUT-427
34. `/Users/zhangyiqian/private-dev/asp-dispatch-service-private_0528/asp-dispatch-service/dispatch-infrastructure/src/test/java/com/mi/asp/dispatch/infrastructure/config/gateway/EngineerWorkloadConfigGatewayImplTest.java` - EUT 63 个，测试方法 65 个，示例：EUT-432, EUT-433, EUT-434, EUT-435, EUT-436, EUT-437, EUT-438, EUT-439
35. `/Users/zhangyiqian/private-dev/asp-dispatch-service-private_0528/asp-dispatch-service/dispatch-infrastructure/src/test/java/com/mi/asp/dispatch/infrastructure/config/gateway/FileUploadGatewayImplTest.java` - EUT 13 个，测试方法 7 个，示例：EUT-495, EUT-496, EUT-497, EUT-498, EUT-499, EUT-500, EUT-501, EUT-502
36. `/Users/zhangyiqian/private-dev/asp-dispatch-service-private_0528/asp-dispatch-service/dispatch-infrastructure/src/test/java/com/mi/asp/dispatch/infrastructure/config/gateway/UserGatewayImplTest.java` - EUT 33 个，测试方法 26 个，示例：EUT-508, EUT-509, EUT-510, EUT-511, EUT-512, EUT-513, EUT-514, EUT-515
37. `/Users/zhangyiqian/private-dev/asp-dispatch-service-private_0528/asp-dispatch-service/dispatch-infrastructure/src/test/java/com/mi/asp/dispatch/infrastructure/datasource/DispatchDataSourceContextHolderTest.java` - EUT 4 个，测试方法 2 个，示例：EUT-415, EUT-416, EUT-417, EUT-418
38. `/Users/zhangyiqian/private-dev/asp-dispatch-service-private_0528/asp-dispatch-service/dispatch-infrastructure/src/test/java/com/mi/asp/dispatch/infrastructure/region/gateway/RegionGatewayImplTest.java` - EUT 7 个，测试方法 36 个，示例：EUT-541, EUT-542, EUT-543, EUT-544, EUT-545, EUT-546, EUT-547

### Step 3 逐 EUT 审计策略

- 审计项严格来自 Q05a `eut_items`，每条 audit item 只绑定一个 `eut_id`。
- `COVERED` 必须绑定 Q05b `passes:true` 任务、测试方法、EUT 标记和 `assertion_lines`。
- evidence 由 `validators/evidence_fill.py` 从 Q05b 断言行机械回填。

### Step 4 覆盖率与路径统计

- 增量行覆盖率：92.8%。
- 增量分支覆盖率：80.23%。
- Boundary: 236/236
- Concurrent: 3/3
- Exception: 131/131
- Happy Path: 271/271

### Step 5 风险记录

- Q05a non_testable_items：37 个，Q06 作为人工/集成验收风险保留。
