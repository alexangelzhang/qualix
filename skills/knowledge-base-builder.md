---
name: knowledge-base-builder
description: "知识库构建：扫描代码仓库，提取稳定的架构知识，供后续 Phase 直接引用"
trigger: "用户要求构建知识库，或首次分析一个新的代码仓库"
allowed-tools:
  - Bash
  - Read
  - Write
  - Edit
  - Grep
  - AskUserQuestion
---

# 知识库构建

## 目的

扫描代码仓库一次，提取稳定的架构知识，持久化为 JSON + Markdown。后续 Phase 直接加载知识库，不再重复扫描代码。

## 适用场景

- 首次接入一个代码仓库
- 代码仓库发生大规模重构后刷新
- 日常增量需求不需要重新构建（核心链路稳定）

## 知识库内容

### 1. 项目元信息 (meta)
- 项目名称、Git 仓库地址、主分支
- 技术栈：Java 版本、框架（Spring Boot/Dubbo/TMF）、构建工具
- DDD 分层结构：各模块路径和职责
- 外部依赖清单（RPC 服务、MQ、Redis、DB）

### 2. API 契约索引 (api_index)
- 所有 Provider 接口清单（接口名、方法签名、所在文件）
- 按业务域分组
- 入参/出参 DTO 清单

### 3. 核心调用链路 (call_chains)
- 每个 Provider 方法的完整 DDD 调用链：
  Provider → ProviderImpl → CmdExe → DomainService → Repository/Gateway → Mapper
- 对于 TMF 项目额外追踪：
  DomainService → TMF.execute → decideSteps → Step → Ability → Extension
- 标注每条链路的保护点（事务、锁、幂等、状态校验）

### 4. 领域模型 (domain_model)
- 聚合根清单
- 实体和值对象
- 领域事件
- 状态机定义（如有）

### 5. 数据模型 (data_model)
- 核心表清单（表名、关键字段、索引）
- 表间关系
- 分库分表策略（如有）

### 6. 测试基线 (test_baseline)
- 测试文件统计（按层分布）
- 测试质量基线（强/中/弱占比）
- 已知的测试缺口

## 输出格式

```
knowledge/<project_id>/
├── meta.json                 # 项目元信息
├── api_index.json            # API 契约索引
├── call_chains.md            # 核心调用链路（人可读）
├── call_chains.json          # 核心调用链路（机器可读）
├── domain_model.md           # 领域模型
├── data_model.md             # 数据模型
├── test_baseline.json        # 测试基线
└── knowledge_summary.md      # 知识库摘要（供 context_loader 加载）
```

## 执行流程

> 以下每个 Step 由 Agent 自行决定具体扫描策略，下方提供参考命令模板。

### Step 1: 项目元信息采集

读取构建配置文件，提取技术栈和模块结构：

```bash
# Java/Maven 项目
cat pom.xml | grep -E '<groupId>|<artifactId>|<version>|<dependency>' | head -50

# Java/Gradle 项目
cat build.gradle | grep -E 'implementation|api|plugins' | head -50

# 扫描模块目录结构
find . -name "pom.xml" -not -path "*/target/*" | sort

# 识别 DDD 分层（按目录名推断）
find . -type d -name "domain" -o -name "infrastructure" -o -name "application" -o -name "client" | grep -v target | sort
```

### Step 2: API 契约扫描

```bash
# 扫描所有 Provider 接口
grep -rn "interface.*Provider" --include="*.java" . | grep -v target | grep -v test

# 提取 Provider 方法签名
grep -A 5 "interface.*Provider" --include="*.java" -r . | grep -v target
```

### Step 3: 核心链路追踪

对每个 Provider 方法，按 DDD+TMF 链路逐层追踪：

```bash
# 找 ProviderImpl
grep -rn "implements.*Provider" --include="*.java" . | grep -v target

# 找 CmdExe 调用
grep -rn "CmdExe\|CommandExecutor" --include="*.java" . | grep -v target

# 找 TMF 链路入口
grep -rn "TMF.execute\|decideSteps\|findAbility" --include="*.java" . | grep -v target

# 找 Gateway 实现
grep -rn "implements.*Gateway" --include="*.java" . | grep -v target
```

### Step 4: 领域模型提取

```bash
# 扫描聚合根和实体
find . -path "*/domain/model/*" -o -path "*/domain/entity/*" -o -path "*/domain/aggregate/*" | grep -v target | sort

# 扫描领域事件
find . -path "*/domain/event/*" -name "*.java" | grep -v target

# 扫描状态机
grep -rn "StateMachine\|enum.*Status\|enum.*State" --include="*.java" . | grep -v target
```

### Step 5: 数据模型提取

```bash
# 从 Mapper XML 提取表结构
find . -name "*Mapper.xml" | grep -v target
grep -h "resultMap\|<id\|<result" $(find . -name "*Mapper.xml" -not -path "*/target/*") 2>/dev/null | head -50

# 从 DO 类推断
find . -path "*/infrastructure/*" -name "*DO.java" -o -name "*PO.java" | grep -v target
```

### Step 6: 测试基线采集

```bash
# 统计测试文件分布（按 DDD 层）
find . -path "*/test/*" -name "*Test.java" | grep -v target | sed 's|.*/test/||' | cut -d/ -f1-3 | sort | uniq -c | sort -rn

# 抽样检查断言质量
grep -c "assertEquals\|assertThat\|verify(" $(find . -path "*/test/*" -name "*Test.java" -not -path "*/target/*" | head -10) 2>/dev/null
```

## 知识库使用方式

### 在 Phase 中引用
context_loader 自动检测知识库目录，优先加载知识库而非重新扫描代码：

```python
# context_loader.py 的加载优先级：
# 1. 知识库 (knowledge/<project_id>/)
# 2. 上游 Phase 结构化产物
# 3. 上游 Phase markdown 报告
```

### 增量更新
知识库不需要每次重建。只在以下情况刷新：
- 新增 Provider 接口
- DDD 分层结构变化
- 核心链路重构
- 新增外部依赖

日常增量需求（新增 Step/Ability/Extension）不需要刷新知识库。

## 禁止事项

1. 禁止将业务数据写入知识库（只存架构知识）
2. 禁止将敏感信息（密码、密钥）写入知识库
3. 禁止在知识库中存储临时状态（如当前分支、未提交代码）
