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

### Step 1: 项目元信息采集
```bash
# 自动检测
- 读取 pom.xml / build.gradle 获取依赖和版本
- 扫描模块目录结构
- 识别 DDD 分层
```

### Step 2: API 契约扫描
```bash
# 扫描所有 Provider 接口
grep -r "interface.*Provider" --include="*.java" <api_module>/
# 提取方法签名
```

### Step 3: 核心链路追踪
对每个 Provider 方法：
1. 找到 ProviderImpl
2. 追踪 CmdExe 或直接调用的 DomainService
3. 追踪 DomainService 内部逻辑
4. 对 TMF 项目追踪 Step/Ability/Extension 链路
5. 追踪 Gateway → Mapper

### Step 4: 领域模型提取
- 扫描 domain 模块的 model/entity/aggregate 目录
- 识别聚合根（通常是最大的实体类）
- 扫描 event 目录识别领域事件
- 扫描 StateMachine 或状态枚举

### Step 5: 数据模型提取
- 扫描 Mapper XML 或注解获取表结构
- 或从 infrastructure 的 DO 类推断

### Step 6: 测试基线采集
- 统计测试文件分布
- 抽样评估质量

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
