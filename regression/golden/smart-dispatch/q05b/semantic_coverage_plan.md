# Q05b 一次性测试批次计划

## 结论

本计划把 Q01/Q05a 业务语义覆盖和 JaCoCo 增量覆盖率作为同等最高优先级。先按本计划写测试，再统一运行目标测试，避免多轮猜测式补测。

## 增量覆盖账本

| 指标 | 当前 covered/total | 当前覆盖率 | 阈值需要 | 带缓冲目标 | 硬缺口 | 缓冲缺口 |
|---|---:|---:|---:|---:|---:|---:|
| 增量行覆盖 | 2128/2293 | 92.80% | 1835 | 1838 | 0 | 0 |
| 增量分支覆盖 | 1031/1285 | 80.23% | 1028 | 1036 | 0 | 5 |

## 优先补测批次

| 优先级 | 类 | EUT | 路径分布 | missed branch | hard deficit | 说明 |
|---:|---|---|---|---:|---:|---|
| 1 | `EngineerSaturationCalculateFillStrategy` | EUT-057, EUT-058, EUT-059, EUT-060, EUT-061, EUT-062, EUT-063, EUT-064, EUT-065, EUT-066, EUT-067, EUT-068, EUT-069, EUT-070, EUT-071, EUT-072, EUT-073, EUT-074, EUT-075, EUT-076, EUT-077, EUT-078, EUT-079, EUT-080, EUT-081, EUT-082, EUT-083, EUT-084, EUT-085, EUT-086, EUT-087, EUT-088, EUT-089, EUT-090, EUT-091, EUT-092, EUT-093, EUT-094, EUT-095, EUT-096, EUT-097, EUT-098, EUT-099, EUT-100, EUT-101, EUT-102, EUT-103, EUT-104, EUT-105, EUT-106, EUT-107, EUT-108, EUT-109, EUT-110, EUT-111, EUT-112, EUT-113, EUT-114, EUT-115, EUT-116, EUT-117, EUT-118, EUT-119, EUT-120, EUT-121, EUT-122, EUT-123, EUT-124, EUT-125, EUT-126, EUT-557, EUT-602, EUT-603, EUT-604, EUT-605, EUT-606, EUT-607, EUT-608, EUT-609, EUT-612, EUT-613, EUT-614, EUT-615, EUT-634, EUT-635, EUT-636, EUT-637 | Boundary:39, Concurrent:2, Exception:4, Happy Path:42 | 129 | 76 | 同时存在语义 EUT 与 JaCoCo 分支/行覆盖缺口或缓冲不足 |
| 2 | `WorkloadConfigServiceImpl` | EUT-216, EUT-217, EUT-218, EUT-219, EUT-220, EUT-221, EUT-222, EUT-223, EUT-224, EUT-225, EUT-226, EUT-227, EUT-228, EUT-229, EUT-230, EUT-231, EUT-232, EUT-233, EUT-234, EUT-235, EUT-236, EUT-237, EUT-238, EUT-239, EUT-240, EUT-241, EUT-242, EUT-243, EUT-244, EUT-245, EUT-246, EUT-247, EUT-248, EUT-249, EUT-250, EUT-251, EUT-252, EUT-253, EUT-254, EUT-255, EUT-256, EUT-257, EUT-258, EUT-259, EUT-260, EUT-261, EUT-262, EUT-263, EUT-264, EUT-265, EUT-266, EUT-267, EUT-268, EUT-269, EUT-270, EUT-271, EUT-272, EUT-273, EUT-274, EUT-275, EUT-276, EUT-277, EUT-278, EUT-279, EUT-280, EUT-281, EUT-282, EUT-283, EUT-284, EUT-285, EUT-286, EUT-287, EUT-288, EUT-289, EUT-290, EUT-291, EUT-292, EUT-293, EUT-294, EUT-295, EUT-296, EUT-297, EUT-298, EUT-299, EUT-300, EUT-301, EUT-302, EUT-303, EUT-304, EUT-305, EUT-306, EUT-307, EUT-308, EUT-309, EUT-310, EUT-311, EUT-312, EUT-313, EUT-314, EUT-315, EUT-316, EUT-317, EUT-318, EUT-319, EUT-320, EUT-321, EUT-322, EUT-323, EUT-324, EUT-325, EUT-326, EUT-327, EUT-328, EUT-329, EUT-330, EUT-331, EUT-332, EUT-333, EUT-334, EUT-335, EUT-336, EUT-337, EUT-338, EUT-339, EUT-340, EUT-341, EUT-342, EUT-343, EUT-344, EUT-345, EUT-346, EUT-347, EUT-556, EUT-590, EUT-591, EUT-592, EUT-593, EUT-594, EUT-595, EUT-596, EUT-597, EUT-598, EUT-599, EUT-600, EUT-601, EUT-631, EUT-632, EUT-633 | Boundary:57, Exception:38, Happy Path:53 | 24 | 0 | 同时存在语义 EUT 与 JaCoCo 分支/行覆盖缺口或缓冲不足 |
| 3 | `EngineerBasicInfoFilterStrategy` | EUT-132, EUT-133, EUT-134, EUT-135, EUT-136, EUT-137, EUT-138 | Boundary:3, Exception:1, Happy Path:3 | 8 | 4 | 同时存在语义 EUT 与 JaCoCo 分支/行覆盖缺口或缓冲不足 |
| 4 | `DispatchRecommendDomainServiceImpl` | EUT-037, EUT-038, EUT-039, EUT-040, EUT-041, EUT-042, EUT-043, EUT-044, EUT-045, EUT-046, EUT-047, EUT-048, EUT-049, EUT-050, EUT-051, EUT-052, EUT-053, EUT-554, EUT-560, EUT-580, EUT-581, EUT-616 | Boundary:6, Exception:8, Happy Path:8 | 9 | 3 | 同时存在语义 EUT 与 JaCoCo 分支/行覆盖缺口或缓冲不足 |
| 5 | `DispatchCandidateGatewayImpl` | EUT-360, EUT-361, EUT-362, EUT-363, EUT-364, EUT-365, EUT-366, EUT-367, EUT-562, EUT-563, EUT-564, EUT-565, EUT-566, EUT-567, EUT-618, EUT-619, EUT-627, EUT-628, EUT-638 | Boundary:5, Exception:7, Happy Path:7 | 7 | 3 | 同时存在语义 EUT 与 JaCoCo 分支/行覆盖缺口或缓冲不足 |
| 6 | `RegionGatewayImpl` | EUT-541, EUT-542, EUT-543, EUT-544, EUT-545, EUT-546, EUT-547 | Boundary:3, Exception:1, Happy Path:3 | 13 | 3 | 同时存在语义 EUT 与 JaCoCo 分支/行覆盖缺口或缓冲不足 |
| 7 | `EngineerProbabilityRankStrategy` | EUT-160, EUT-161, EUT-162, EUT-163, EUT-164, EUT-165, EUT-166, EUT-167, EUT-168, EUT-169, EUT-170, EUT-171, EUT-172, EUT-173, EUT-174, EUT-175, EUT-176, EUT-177, EUT-178, EUT-179, EUT-180, EUT-181, EUT-182, EUT-183, EUT-184, EUT-185, EUT-186, EUT-187, EUT-188, EUT-189, EUT-572, EUT-573, EUT-574, EUT-575, EUT-576, EUT-577, EUT-578, EUT-579, EUT-623, EUT-624, EUT-625, EUT-626 | Boundary:12, Exception:9, Happy Path:21 | 17 | 2 | 同时存在语义 EUT 与 JaCoCo 分支/行覆盖缺口或缓冲不足 |
| 8 | `EngineerHolidayFilterStrategy` | EUT-148, EUT-149 | Boundary:1, Happy Path:1 | 6 | 3 | 同时存在语义 EUT 与 JaCoCo 分支/行覆盖缺口或缓冲不足 |
| 9 | `UnfinishedStatsQueryExecutorConfig` | EUT-031, EUT-032 | Concurrent:1, Happy Path:1 | 0 | 0 | 同时存在语义 EUT 与 JaCoCo 分支/行覆盖缺口或缓冲不足 |
| 10 | `EngineerOverloadFilterStrategy` | EUT-152, EUT-153, EUT-154, EUT-155, EUT-156, EUT-157, EUT-158, EUT-568, EUT-569, EUT-570, EUT-571, EUT-622 | Boundary:6, Exception:1, Happy Path:5 | 7 | 2 | 同时存在语义 EUT 与 JaCoCo 分支/行覆盖缺口或缓冲不足 |
| 11 | `EngineerWorkloadConfigGatewayImpl` | EUT-432, EUT-433, EUT-434, EUT-435, EUT-436, EUT-437, EUT-438, EUT-439, EUT-440, EUT-441, EUT-442, EUT-443, EUT-444, EUT-445, EUT-446, EUT-447, EUT-448, EUT-449, EUT-450, EUT-451, EUT-452, EUT-453, EUT-454, EUT-455, EUT-456, EUT-457, EUT-458, EUT-459, EUT-460, EUT-461, EUT-462, EUT-463, EUT-464, EUT-465, EUT-466, EUT-467, EUT-468, EUT-469, EUT-470, EUT-471, EUT-472, EUT-473, EUT-474, EUT-475, EUT-476, EUT-477, EUT-478, EUT-479, EUT-480, EUT-481, EUT-482, EUT-483, EUT-484, EUT-485, EUT-486, EUT-487, EUT-488, EUT-489, EUT-490, EUT-491, EUT-492, EUT-493, EUT-494 | Boundary:22, Exception:18, Happy Path:23 | 0 | 0 | 同时存在语义 EUT 与 JaCoCo 分支/行覆盖缺口或缓冲不足 |
| 12 | `DispatchEngineerUnfinishedTaskGatewayImpl` | EUT-379, EUT-380, EUT-381, EUT-382, EUT-383, EUT-384, EUT-385, EUT-386, EUT-387, EUT-388, EUT-389, EUT-390, EUT-391, EUT-392, EUT-393, EUT-394, EUT-395, EUT-396, EUT-397, EUT-398, EUT-399, EUT-400, EUT-401 | Boundary:8, Exception:7, Happy Path:8 | 8 | 1 | 同时存在语义 EUT 与 JaCoCo 分支/行覆盖缺口或缓冲不足 |
| 13 | `DispatchDataSourceContextHolder` | EUT-415, EUT-416, EUT-417, EUT-418 | Boundary:1, Exception:2, Happy Path:1 | 1 | 1 | 同时存在语义 EUT 与 JaCoCo 分支/行覆盖缺口或缓冲不足 |
| 14 | `SaturationMinSelectStrategy` | EUT-194, EUT-195, EUT-196, EUT-197 | Boundary:2, Happy Path:2 | 2 | 1 | 同时存在语义 EUT 与 JaCoCo 分支/行覆盖缺口或缓冲不足 |
| 15 | `DispatchStrategyOrchestrator` | EUT-054, EUT-055, EUT-056 | Boundary:1, Exception:1, Happy Path:1 | 2 | 1 | 同时存在语义 EUT 与 JaCoCo 分支/行覆盖缺口或缓冲不足 |
| 16 | `DispatchServiceItemCategoryGatewayImpl` | EUT-402, EUT-403, EUT-404 | Boundary:1, Exception:1, Happy Path:1 | 2 | 1 | 同时存在语义 EUT 与 JaCoCo 分支/行覆盖缺口或缓冲不足 |
| 17 | `DispatchEngineerBasicInfoGatewayImpl` | EUT-368, EUT-369, EUT-370 | Boundary:1, Exception:1, Happy Path:1 | 2 | 1 | 同时存在语义 EUT 与 JaCoCo 分支/行覆盖缺口或缓冲不足 |
| 18 | `EngineerLevelFilterStrategy` | EUT-150, EUT-151 | Boundary:1, Happy Path:1 | 2 | 1 | 同时存在语义 EUT 与 JaCoCo 分支/行覆盖缺口或缓冲不足 |
| 19 | `UserGatewayImpl` | EUT-508, EUT-509, EUT-510, EUT-511, EUT-512, EUT-513, EUT-514, EUT-515, EUT-516, EUT-517, EUT-518, EUT-519, EUT-520, EUT-521, EUT-522, EUT-523, EUT-524, EUT-525, EUT-526, EUT-527, EUT-528, EUT-529, EUT-530, EUT-531, EUT-532, EUT-533, EUT-534, EUT-535, EUT-536, EUT-537, EUT-538, EUT-539, EUT-540 | Boundary:11, Exception:10, Happy Path:12 | 0 | 0 | 同时存在语义 EUT 与 JaCoCo 分支/行覆盖缺口或缓冲不足 |
| 20 | `DispatchSlaveReadAspect` | EUT-419 | Happy Path:1 | 1 | 1 | 同时存在语义 EUT 与 JaCoCo 分支/行覆盖缺口或缓冲不足 |
| 21 | `DispatchRecommendRpcAppService` | EUT-005, EUT-006, EUT-007, EUT-008, EUT-009, EUT-010, EUT-011, EUT-012, EUT-013, EUT-014, EUT-015, EUT-016, EUT-017, EUT-018, EUT-559, EUT-561, EUT-617 | Boundary:5, Exception:4, Happy Path:8 | 2 | 0 | 同时存在语义 EUT 与 JaCoCo 分支/行覆盖缺口或缓冲不足 |
| 22 | `AbstractDispatchFilterStrategy` | EUT-127, EUT-128, EUT-129, EUT-130, EUT-131 | Boundary:2, Exception:1, Happy Path:2 | 2 | 0 | 同时存在语义 EUT 与 JaCoCo 分支/行覆盖缺口或缓冲不足 |
| 23 | `EngineerWorkloadConfigProviderImpl` | EUT-019, EUT-020, EUT-021, EUT-022, EUT-023, EUT-024, EUT-025, EUT-026, EUT-027, EUT-028, EUT-029, EUT-030 | Boundary:4, Exception:4, Happy Path:4 | 0 | 0 | 同时存在语义 EUT 与 JaCoCo 分支/行覆盖缺口或缓冲不足 |
| 24 | `FileUploadGatewayImpl` | EUT-495, EUT-496, EUT-497, EUT-498, EUT-499, EUT-500, EUT-501, EUT-502, EUT-503, EUT-504, EUT-505, EUT-506, EUT-507 | Boundary:4, Exception:4, Happy Path:5 | 0 | 0 | 同时存在语义 EUT 与 JaCoCo 分支/行覆盖缺口或缓冲不足 |
| 25 | `EngineerCertificateFilterStrategy` | EUT-139, EUT-140, EUT-141, EUT-142, EUT-143, EUT-144, EUT-145, EUT-146, EUT-147 | Boundary:4, Exception:1, Happy Path:4 | 5 | 0 | 同时存在语义 EUT 与 JaCoCo 分支/行覆盖缺口或缓冲不足 |
| 26 | `CategoryGatewayImpl` | EUT-420, EUT-421, EUT-422, EUT-423, EUT-424, EUT-425, EUT-426, EUT-427, EUT-428, EUT-429, EUT-430, EUT-431 | Boundary:6, Happy Path:6 | 0 | 0 | 同时存在语义 EUT 与 JaCoCo 分支/行覆盖缺口或缓冲不足 |
| 27 | `DistanceTierSelectStrategy` | EUT-190, EUT-191, EUT-192, EUT-193, EUT-620, EUT-621 | Boundary:3, Exception:1, Happy Path:2 | 2 | 0 | 同时存在语义 EUT 与 JaCoCo 分支/行覆盖缺口或缓冲不足 |
| 28 | `DispatchEngineerHolidayGatewayImpl` | EUT-374, EUT-375, EUT-376, EUT-377, EUT-378 | Boundary:2, Exception:1, Happy Path:2 | 3 | 0 | 同时存在语义 EUT 与 JaCoCo 分支/行覆盖缺口或缓冲不足 |
| 29 | `DispatchScenarioPlanResolver` | EUT-159, EUT-555, EUT-582, EUT-583, EUT-584, EUT-585, EUT-586, EUT-587, EUT-588, EUT-589, EUT-629, EUT-630 | Exception:2, Happy Path:10 | 0 | 0 | 同时存在语义 EUT 与 JaCoCo 分支/行覆盖缺口或缓冲不足 |
| 30 | `DispatchAssignFailReasonEnum` | EUT-001, EUT-002, EUT-003, EUT-004 | Boundary:2, Happy Path:2 | 0 | 0 | 同时存在语义 EUT 与 JaCoCo 分支/行覆盖缺口或缓冲不足 |
| 31 | `DispatchEngineerCertificateGatewayImpl` | EUT-371, EUT-372, EUT-373 | Boundary:1, Exception:1, Happy Path:1 | 0 | 0 | 同时存在语义 EUT 与 JaCoCo 分支/行覆盖缺口或缓冲不足 |

## 写测试规则

- REQ/BR/SE/EUT 语义覆盖和 JaCoCo 增量覆盖率同为最高优先级，任何一边不满足都不能把批次视为完成。
- 先生成本计划，再写 Java 测试；禁止写完测试后才第一次计算覆盖率缺口。
- 默认按类批量写测试，统一运行目标测试命令，避免每条 EUT 单独编译。
- 补测目标不只追平阈值，应至少满足 line_buffer_target 和 branch_buffer_target，避免刚过线后因小改动回退。
- 报告只展示增量目标覆盖率；全仓全量覆盖率不是本流程关注指标。
