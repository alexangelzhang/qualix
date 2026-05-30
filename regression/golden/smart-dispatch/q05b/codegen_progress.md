# Q05b 代码生成进度 - smart-dispatch

## 批次 q05b-branch-boost-001

本批目标是把增量分支覆盖率从 Q05b 基线的 78.83% 拉到不低于 80%，同时保持测试可追溯到 Q05a EUT，不新增孤儿测试。

### 实现的 EUT

| EUT | 目标类 | 测试文件 | 测试方法 | 核心断言 |
|---|---|---|---|---|
| EUT-001 | DispatchAssignFailReasonEnum | `/Users/zhangyiqian/private-dev/asp-dispatch-service-private_0528/asp-dispatch-service/dispatch-api/src/test/java/com/mi/asp/dispatch/api/constant/DispatchAssignFailReasonEnumQ05bTest.java` | `fromId_knownWorkloadConfigReason_returnsBusinessEnum` | `fromId(110)` 返回 `NO_ENGINEER_WORKLOAD_CONFIG`，联合原因文案正确。 |
| EUT-002 | DispatchAssignFailReasonEnum | 同上 | `fromId_nullAndUnknownId_returnsNullInsteadOfWrongReason` | `null` 与未知 id 返回 `null`，避免错误派单失败原因。 |
| EUT-003 | DispatchAssignFailReasonEnum | 同上 | `fromName_knownEnumName_returnsBusinessEnum` | `fromName("NO_ENGINEER_BINDING")` 返回对应枚举与业务描述。 |
| EUT-004 | DispatchAssignFailReasonEnum | 同上 | `fromName_blankNullAndUnknownName_returnsNullInsteadOfWrongReason` | `null`、空白、未知名称均返回 `null`。 |
| EUT-139 | EngineerCertificateFilterStrategy | `/Users/zhangyiqian/private-dev/asp-dispatch-service-private_0528/asp-dispatch-service/dispatch-domain/src/test/java/com/mi/asp/dispatch/domain/asign/strategy/filter/EngineerCertificateFilterStrategyQ05bTest.java` | `apply_workHighNotRequired_keepsCandidatesAndMarksSkillMatched` | 品类不要求高空作业时保留候选人，并标记技能匹配。 |
| EUT-140 | EngineerCertificateFilterStrategy | 同上 | `apply_workHighRequired_filtersMissingBasicInfoAndInvalidCertificates` | 要求高空作业时过滤缺基础信息、缺证书、缺保险和保险过期候选人，只保留有效候选人。 |
| EUT-143 | EngineerCertificateFilterStrategy | 同上 | `apply_workHighRequired_acceptsLegacyParsableCertificateDate` | 旧格式可解析有效期仍被接受，候选人不被误过滤。 |
| EUT-144 | EngineerCertificateFilterStrategy | 同上 | `apply_workHighRequired_treatsEmptyBlankAndMalformedDatesAsExpired` | 空、空白和不可解析有效期均按过期处理，候选人被过滤。 |
| EUT-419 | DispatchSlaveReadAspect | `/Users/zhangyiqian/private-dev/asp-dispatch-service-private_0528/asp-dispatch-service/dispatch-infrastructure/src/test/java/com/mi/asp/dispatch/infrastructure/config/datasource/DispatchSlaveReadAspectQ05bTest.java` | `aroundSlaveRead_switchesToSlaveAndRestoresPreviousRoute` | 读库切面执行期间切到 SLAVE，结束后恢复原路由。 |

### 测试运行凭证

`python3 validators/run_test_batch.py --manifest artifacts/smart-dispatch/manifest.json --artifact-dir artifacts/smart-dispatch --batch-id q05b-branch-boost-001`

- receipt: `q05b-branch-boost-001-20260528T121430`
- phase: `test`
- exit_code: `0`
- 运行方法数：9 个 Q05b 测试方法。

### JaCoCo 刷新

先执行模块 verify 生成 domain/app/infrastructure 覆盖率报告：

`mvn -pl dispatch-api,dispatch-domain,dispatch-app,dispatch-infrastructure -am verify -DskipITs -Dcheckstyle.skip=true -Dsurefire.failIfNoSpecifiedTests=false`

然后单独刷新 API 模块 JaCoCo，确保 `DispatchAssignFailReasonEnumQ05bTest` 计入 `dispatch-api/target/site/jacoco/jacoco.csv`：

`mvn -pl dispatch-api org.jacoco:jacoco-maven-plugin:0.8.7:prepare-agent test org.jacoco:jacoco-maven-plugin:0.8.7:report -Dcheckstyle.skip=true -Dsurefire.failIfNoSpecifiedTests=false`

本次合并以下模块 CSV 为 `q05b/coverage/jacoco-merged.csv`：

- `dispatch-api/target/site/jacoco/jacoco.csv`
- `dispatch-domain/target/site/jacoco/jacoco.csv`
- `dispatch-app/target/site/jacoco/jacoco.csv`
- `dispatch-infrastructure/target/site/jacoco/jacoco.csv`

### 覆盖率变化

| 指标 | 基线 | 本批后 | 变化 | 门槛 |
|---|---:|---:|---:|---:|
| 增量行覆盖 | 2100/2293, 91.58% | 2128/2293, 92.80% | +28 行, +1.22pp | >=80% |
| 增量分支覆盖 | 1013/1285, 78.83% | 1031/1285, 80.23% | +18 分支, +1.40pp | >=80% |

结论：本批后增量行覆盖率和增量分支覆盖率均达到 80% 门槛。分支覆盖率距离缓冲目标 `1036/1285` 仍差 5 个 covered branch，后续若要提高抗回退余量，可继续补 `EngineerSaturationCalculateFillStrategy` 或其他高 missed branch 类。
