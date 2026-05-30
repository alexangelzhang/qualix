# Q05a Reasoning Log — entitlement-lifecycle

### Step 1：加载 Q01 产物

- REQ-001/002, BR-001~007, SE-001~009 全部加载
- 9条 BR 和 9条 SE 映射到 WarrantyFacadeImpl 和 WarrantyUpdateCommandHandler

### Step 2：build_code_index.py 运行结果

- 6个 diff 文件，6个 Java 类识别
- 主要变更类：WarrantyFacadeImpl（5个方法改动）、WarrantyUpdateCommandHandler（1个方法）
- 排除：MafGatewayImpl（日志）、WarrantyUpdateTypeEnum（注释）、SrvThreeGuarantee（注解）、WarrantyUpdateParam（DTO）

### Step 3：变更 Java 实现类清单及覆盖

| 类 | 变更方法 | 覆盖 EUT |
|---|---|---|
| WarrantyFacadeImpl | resolveStartTimeTypeId | EUT-006~009 |
| WarrantyFacadeImpl | parseFixWarrantyEndDate | EUT-004, 005 |
| WarrantyFacadeImpl | validateAndParseFixWarrantyParam | EUT-002, 003（间接） |
| WarrantyFacadeImpl | fixWarrantyData | EUT-001, 010, 013, 014, 018, 019 |
| WarrantyFacadeImpl | fixMaterialWarrantyData | EUT-015, 016, 017 |
| WarrantyUpdateCommandHandler | handle | EUT-011, 012 |

### Step 4：分支补充推导

**resolveStartTimeTypeId** — 三步解析链 + null 守卫 = 4个分支
**parseFixWarrantyEndDate** — strToDate 命中 / fallback strToShortDate / 两者 null = 3个分支（另加 blank 守卫）
**fixWarrantyData** — 入口 fail / DB null / revisable=YES / revisable=NO = 4个分支
**WarrantyUpdateCommandHandler.handle** — command null / threeGuarantee null / happy = 3个分支

### Step 5：assertion_blueprint 质量自检

- 所有 19 条 EUT 均有 assertion_blueprint（type/target/expected）
- Exception EUT 均指定 assertThrows 或 fail+code
- Happy Path EUT 均包含 side_effects（verify）
- 无空 then

### Step 6：覆盖完整性验证

- REQ-001: EUT-001, 010, 013, 014, 018, 019 ✓
- REQ-002: EUT-015, 016, 017 ✓
- BR-001: EUT-001, 018 ✓
- BR-002: EUT-002, 003 ✓
- BR-003: EUT-004, 005 ✓
- BR-004: EUT-006, 007, 008, 009 ✓
- BR-005: EUT-010, 019 ✓
- BR-006: EUT-011, 012 ✓
- BR-007: EUT-013, 014 ✓
- SE-001: EUT-001 ✓, SE-002: EUT-002 ✓, SE-003: EUT-004 ✓
- SE-004: EUT-006 ✓, SE-005: EUT-007 ✓, SE-006: EUT-008 ✓
- SE-007: EUT-010 ✓, SE-008: EUT-011 ✓, SE-009: EUT-015 ✓
