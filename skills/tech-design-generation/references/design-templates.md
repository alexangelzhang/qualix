# 接口设计模板

## 接口设计模板

```
接口名称: XxxCmd / XxxQuery
触发场景: <对应的 REQ/BR ID>

入参:
  - field: <字段名>
    type: <类型>
    required: true/false
    validation: <校验规则>
    note: <业务含义>

出参:
  - field: <字段名>
    type: <类型>
    note: <业务含义>

幂等设计:
  - 幂等键: <字段>
  - 幂等范围: <时间窗口/业务范围>
  - 重复请求处理: <返回成功/报错/忽略>

处理步骤:
  1. 参数校验（Provider 层）
  2. 幂等检查（Provider/CmdExe 层）
  3. 加载领域对象
  4. 执行业务规则（Domain 层）
  5. 持久化（Infrastructure 层）
  6. 发布领域事件（如有）
  7. 返回结果

事务边界: <哪些操作在同一事务内>
异常处理:
  - <异常场景> → <错误码> → <处理策略>
```

## TMF 链路设计模板

```
Provider.execute()
  └─ CmdExe.execute()
       ├─ 前置校验
       ├─ TMF.execute(context)
       │    ├─ decideSteps() → [Step1, Step2, ...]
       │    └─ Step.execute()
       │         └─ Ability.execute()
       │              └─ ExtPt.execute() ← 扩展点
       └─ 后置处理（事件发布/缓存更新）
```

## 技术方案文档结构

```markdown
# 技术方案：<项目名>

## 1. 需求映射矩阵
| REQ/BR ID | 业务描述 | 技术实现 |
|-----------|---------|---------|

## 2. 整体架构（HLD）
### 2.1 系统上下文
### 2.2 分层架构
### 2.3 核心数据模型
### 2.4 状态机（如有）

## 3. 详细设计（LLD）
### 3.1 接口设计
### 3.2 TMF 链路（如有）
### 3.3 关键业务流程

## 4. 非功能性设计
### 4.1 并发控制
### 4.2 性能设计
### 4.3 可观测性
### 4.4 AI/LLM 集成（如有）

## 5. GAP/OPEN 处理

## 6. 风险与约束
```

## 结构化产物模板

```json
{
  "phase": "A.3",
  "project_id": "<project_id>",
  "architecture_style": "ddd-tmf | crud | event-driven | ai-pipeline",
  "req_mapping": [
    {"req_id": "REQ-001", "design_ref": "接口XxxCmd", "coverage": "full|partial|gap"}
  ],
  "interfaces": [
    {
      "name": "XxxCmd",
      "type": "command|query",
      "idempotent": true,
      "transaction_boundary": "...",
      "risks": []
    }
  ],
  "data_models": [],
  "gaps": [
    {"id": "GAP-001", "handling": "designed|pending|blocked", "risk": "P0|P1|P2"}
  ],
  "blockers": []
}
```

## 范围外发现模板

```markdown
## 范围外发现
- [架构] 现有 XxxService 的职责过重（>800 行），建议拆分（与本次需求无关）
- [数据] YyyTable 缺少 version 字段，无法支持乐观锁（影响并发安全但不在本次范围）
- [需求] Phase Q01 的 REQ-005 描述不够细，技术方案基于假设设计（已标记 UPSTREAM_UPDATE_NEEDED）
```
