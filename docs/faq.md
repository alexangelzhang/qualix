# 常见问题 FAQ

## 环境配置

### Q: dqg-run 命令找不到？

```bash
# 确认已安装
pip install -e /path/to/dev-quality-gate

# 或直接使用模块调用
python -m dqg.core.runner <project_id> <command>
```

### Q: doctor 报错"缺少依赖"？

```bash
pip install pydantic jinja2

# 可选依赖（不影响核心功能）
pip install deepeval tree-sitter
```

### Q: 飞书 token 无效？

```bash
# 安装 larkkit
pip install larkkit

# 登录授权
uvx larkkit auth login

# 验证
uvx larkkit auth status
```

## 项目初始化

### Q: 第一次使用，不知道从哪开始？

```bash
# 1. 环境检查
dqg-run any doctor

# 2. 初始化项目
dqg-run my-project init --profile java-ddd-tmf

# 3. 在 AI IDE 中启动
@dqg_starter.md 执行
```

### Q: output 目录下已有项目，如何继续？

直接在 AI IDE 中 `@dqg_starter.md 执行`，会自动检测已有项目。如果有多个项目会列出让你选择。

### Q: 如何切换 profile？

```bash
dqg-run <project_id> status --profile go-service
```

## Phase 执行

### Q: AI 产物不符合预期？（最高频痛点）

```bash
# ❌ 不好的方式
> 重新生成

# ✅ 好的方式：明确指出问题
> BR-003 的字段列表不完整，缺少"审核状态"和"审核时间"字段，请补充

# ✅ 好的方式：提供参考
> 参考 Phase Q01 中 REQ-001 的 BR 拆分方式，对 REQ-003 重新拆分

# ✅ 好的方式：分步确认
> 先列出你识别到的所有 REQ，我确认后再拆 BR
```

核心原则：越具体的反馈，AI 修正越准确。"重新生成"是最低效的方式。

### Q: Phase 执行中断，如何继续？

```bash
# 重新启动
@dqg_starter.md 执行

# 选择中断的 Phase 继续执行
# 如果状态显示 in_progress，可以重新选择执行
```

### Q: 某个 Phase 显示 🔒 锁定，怎么解锁？

锁定说明前置 Phase 未完成。查看依赖关系：

```
Q01 → Q02 → Q03 → Q04 → Q07
Q01 → Q05 → Q06
```

找到最近的未完成 Phase，先完成它。

### Q: 已完成的 Phase 想重新执行？

在菜单中选择已完成的 Phase 编号，进入详情页后选择 `[r] 重新执行`。

### Q: finalize 报错"推理日志不存在"？

每个 Phase 必须输出 `_reasoning_log.md`。如果 AI 跳过了，提示它：

```
> 请输出 _reasoning_log.md，记录每步的决策过程
```

### Q: finalize 报错"产物数量回退"？

重跑 Phase 时，新版产物数量不能少于旧版（REQ/BR/SE/GAP/OPEN 数量）。检查是否有遗漏，补齐后重新 finalize。

## 菜单交互

### Q: 快捷键 v 和 g 是什么？

- `v`（详情模式）：展示每个 Phase 的交付物清单、校验结果、Judge 评分
- `g`（全局进度）：展示完成率、总耗时、平均质量分汇总
- 数字：选择要执行的阶段

### Q: 如何查看某个 Phase 的产物？

```bash
dqg-run <project_id> detail <phase_id>
```

或在菜单中选择已完成的 Phase 编号。

## 版本与升级

### Q: 如何查看当前版本？

```bash
dqg-run <project_id> version
```

### Q: 如何升级 DQG？

```bash
dqg-run <project_id> update
```

会自动 git pull 并同步 version.json。

## 其他

### Q: DQG 和 VAF 有什么区别？

- DQG 聚焦质量门禁（审计+防漏），产出审计报告
- VAF 聚焦全流程自动化（需求→代码→测试），产出实际代码
- 两者可以互补：VAF 生成代码，DQG 审计质量

### Q: 能否跳过某个 Phase？

可以，但不建议。跳过会导致下游 Phase 缺少输入：

```bash
dqg-run <project_id> skip <phase_id> -c "跳过原因"
```
