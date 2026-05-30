# Qualix Flow — 快速启动

> **Skill 豁免**：Qualix 有自己的 skill 驱动执行机制。启动和执行期间跳过 superpowers skill 检查（brainstorming / writing-plans / executing-plans 等），直接按本文件和 Phase skill 执行。不要在 Qualix 流程中调用任何 superpowers skill。

## 启动指令

当用户触发本命令时，直接进入流程，无需询问用户意图：

1. 输出 `Qualix Flow 模式已激活`
2. 异步启动监控看板（后台运行，不阻塞主流程）：
   ```bash
   pgrep -f "streamlit run.*dashboard" > /dev/null || nohup streamlit run src/qualix/reporting/dashboard_app.py > /tmp/qualix-dashboard.log 2>&1 &
   ```
   - 若已在运行则跳过（幂等）
   - 输出提示：`监控看板已在后台启动 -> http://localhost:8501`
3. 扫描 `output/` 目录下包含 `state.json` 的项目：
   - 1 个项目：自动使用
   - 多个项目：列出让用户选择
   - 无项目：提示 `qualix-run <project_id> init`
4. 执行 `qualix-run --base-dir <project_root> <project_id> startup`
5. 解析 JSON 输出，渲染菜单
6. **等待用户选择**

> 禁止手动构造菜单，必须调用脚本获取状态。

## 菜单渲染格式

```
==========================================
  Qualix — <project_id>
  进度: X/7 (XX%) | 总耗时: XXs
==========================================

  [1] ✅ Phase Q01  需求结构化           (已完成, XXs)
  [2] ⬜ Phase Q02  技术方案生成          ← 可执行 (可选，已有方案可 skip)
  [3] 🔒 Phase Q03  技术方案质量评审       (依赖 Q02)
  [4] 🔒 Phase Q04  技术方案覆盖度审计     (依赖 Q03)
  [5] ⬜ Phase Q05  单测生成             ← 可执行
  [6] ⬜ Phase Q06  单测覆盖审计          ← 可执行
  [7] 🔒 Phase Q07  代码评审             (依赖 Q01)
  [8] 📊 查看执行记录

  快捷键: [v] 详情模式  [g] 全局进度  [数字] 执行阶段

请选择:
```

### 菜单交互规则

- `available: true` → 可执行
- `available: false` 且前置未完成 → 锁定，选择时提示解锁条件
- `status: approved` → 已完成，选择时执行 `qualix-run detail <phase>` 展示详情页
- `v` → 详情模式（每个 Phase 的交付物清单、校验结果、Judge 评分）
- `g` → 全局进度（从 JSON 的 `progress` 字段渲染）

### 已完成 Phase 详情页

执行 `qualix-run --base-dir <project_root> <project_id> detail <phase_id>` 后展示：
- 产物摘要（交付物列表 + 关键指标）
- 操作选项：`[b] 返回菜单` / `[r] 重新执行此 Phase`
- **等待用户选择**

## 用户选择 Phase 后 → 按需加载执行流程

读取 `qualix_starter.md` 中的执行流程（步骤二~五），然后按流程执行：

1. **收集输入**（逐步交互，每次只问一个）
2. **执行 Phase**（Orchestrator 模式：构造 SubAgent prompt → 派发执行 → 收集结果；简单 Phase 可直接执行）
3. **Finalize**（`qualix-run finalize` → 展示校验结果 → 等待确认）
4. **Approve**（`qualix-run approve` → 刷新菜单 → 等待下一步选择）

> 执行细节、sidecar 列表、finalize handler、Adaptive Loop 等均在 `qualix_starter.md` 中定义，选择 Phase 后再加载，启动时不需要。

## 启动阶段核心规则

1. **脚本驱动状态** — 状态管理必须通过 `qualix-run`，禁止手动构造
2. **逐步交互** — 每次只展示一个问题，等待用户回复后再展示下一个
3. **等待用户输入** — 菜单展示、确认点必须等待用户输入，禁止自动继续
4. **控制权交还** — Phase 产出后进入 finalize 流程，不自动建议下一步

> 完整规则（11 条）见 `qualix_starter.md` 核心规则章节。
