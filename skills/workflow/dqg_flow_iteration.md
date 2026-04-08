---
name: dqg-flow-iteration
description: "迭代工作流：问题修复后增量重跑、代码更新后部分重跑"
---

# DQG 迭代工作流

## 适用场景

1. Phase D 发现问题，开发修复后需要重新评审
2. Phase C 审计不通过，补充测试后需要重新审计
3. 代码仓库有新提交，需要增量重跑部分 Phase
4. PRD 变更，需要从 Phase A 重新开始

## 迭代类型

### 类型 1: 问题修复后重跑单个 Phase

**场景**: Phase D 发现 CRITICAL 问题，开发修复后重新评审

**流程**:
```
Phase D 发现问题 → 开发修复代码 → 重置 Phase D → 重新执行 Phase D
```

**操作**:
```bash
# 手动重置状态（编辑 _state.json 或未来支持 dqg-run reset 命令）
# 重新执行
dqg-run PROJ execute D
# ... 执行 skill ...
dqg-run PROJ finalize D
dqg-run PROJ approve D
```

**注意**: 重跑时会自动加载最新的上游产物上下文，无需重跑上游 Phase。

### 类型 2: 补充测试后重跑 Phase C

**场景**: Phase C 审计为 FAIL，补充测试后重新审计

**流程**:
```
Phase C FAIL → 补充测试（Phase B 或手动） → 重置 Phase C → 重新执行 Phase C
```

**可选**: 如果需要 Phase B 重新生成测试，先重置 B 再重置 C。

### 类型 3: 代码更新后增量重跑

**场景**: 代码仓库有新提交（如本次 rights-platform 退款模块重构），需要重新评审

**流程**:
```
代码更新 → 确定影响范围 → 重置受影响的 Phase → 重新执行
```

**影响范围判断**:
| 变更类型 | 需重跑的 Phase |
|---------|--------------|
| PRD 变更 | A → A.5 → A.6 → B → C → D（全部） |
| 技术方案变更 | A.5 → A.6（不影响 B/C/D） |
| 代码重构（不改接口） | C → D |
| 新增代码 | B → C → D |
| 仅补充测试 | C |

### 类型 4: 按模块增量重跑

**场景**: 多模块项目中，某个模块代码更新，只重跑该模块

**流程**:
```
模块 X 代码更新 → 重置 Phase A.6/B/C/D → 重新执行（仅模块 X 的部分）
```

**注意**: Phase A 和 A.5 通常不需要重跑（需求和覆盖度不受单模块代码变更影响）。

## 状态重置规则

### 当前方式（手动编辑）
编辑 `output/<project_id>_state.json`，将目标 Phase 的 status 改为 `not_started`。

### 未来支持（TODO）
```bash
dqg-run PROJ reset D                    # 重置单个 Phase
dqg-run PROJ reset B C D                # 重置多个 Phase
dqg-run PROJ reset --from A.6           # 重置 A.6 及其下游
dqg-run PROJ reset --module 权益退款 D   # 重置某模块的某个 Phase
```

## 产物保留策略

重跑时，旧产物不自动删除：
- 报告文件会被覆盖（同名文件）
- telemetry 记录追加（可追溯历史）
- temp/ 目录的测试文件会被覆盖

如需保留历史版本，在重跑前手动备份：
```bash
cp output/PROJ/phaseD/review_report.md output/PROJ/phaseD/review_report_v2.md
```

## 迭代收敛判断

一个项目的质量门禁在以下条件下视为收敛：
1. Phase A: 所有 GAP/OPEN 已闭环或显式延期
2. Phase A.5: REQ 覆盖率 100%，GAP 闭环率 >= 60%
3. Phase A.6: 无 CRITICAL_GAP，P0 问题已有方案
4. Phase B: EUT 矩阵覆盖所有 REQ/BR/SE
5. Phase C: PASS 或 PASS_WITH_RISKS（无 FAIL）
6. Phase D: DONE 或 DONE_WITH_CONCERNS（无 BLOCKED）

如果多次迭代后仍无法收敛，应升级为项目风险，由技术负责人决策是否接受风险上线。
