---
date: 2026-05-18
session_topic: Q05/Q01 gate 体系深度修复——防幻觉/防绕过/交叉验证全面升级
project: qualix
status: in-progress
---

## Active Task
home-replace-renewal Q05 待执行（Q01 approved，Q05 单测代码已在业务仓库但未走 finalize）

## 断点状态
- 已完成：Q05+Q01 所有 gate 修复已提交（共 12 个 commit），代码需用户手动 push
- 下一步：执行 home-replace-renewal Q05 finalize（需传 --code-repo 参数）
- 阻塞项：neptune maven plugin SSL 错误，-Dneptune.skip=true 可绕过

## 架构发现
- Q05 两层产物解耦：EUT 矩阵 JSON（L1）vs .java 测试代码（L2），两层必须交叉验证才能防绕过
- _resolve_output_dir bug：.dqg/output/ 存在时全局切换导致旧项目失联（已修复）
- check_phase_b_compilation 存在但未接入 finalize 流程（B1 核心漏洞，已修复）
- Q01 是整个流水线源头，SE 来源虚报会让下游所有 gate 验证假前提

## 关键决策
- 防绕过三层防御：文件存在 + summary 数字一致 + impl_class 在@InjectMocks 里交叉验证
- Step 0.5 gate：_q05_target_modules.json 强制要求，三层验证防 JSON 造假
- Q01 SE.verification：从 WARN 升级为 FAIL，对标 Q05 then_must_be_concrete
- 动态门槛：R-EUT-COUNT 改为 >= REQ+BR+SE，R-SE-BOUND 改为逐条比对

## 今日 Commit 清单（main 分支）
- 7968c300 fix(runner): _resolve_output_dir 路径路由 bug
- 6745596c fix(gates): B1-B6 编译/测试/设计矩阵 gate 接入
- ef196ab9 fix(rules): EUT 动态门槛/路径四维度/SE 逐条
- 8c1d7333 fix(q05): BR 100%/代码分支100%/路径四维度/Judge 4.7
- 4d67bea8 fix(q05): 6个LLM绕过漏洞（断言/异常/矩阵/T1/never）
- b1a269cf fix(q05): SKILL同步+6类系统性绕过路径修复
- d4aa3058 fix(q05): Step 0.5三层驱动强制gate+uncovered BR理由
- 0539bfc4 fix(q05): C1-C8八个交叉验证缺口
- 95f02ad4 fix(q01): Q01五项L0-L1交叉验证缺口
- 3c9214cd fix(q01): Q1-2代码反推检测+Q1-4 BR密度合理性

## 未完成工作
- [ ] home-replace-renewal Q05 执行（代码已在业务仓库，需 finalize）
- [ ] Q02-Q03-Q04 需重跑（之前 session 产物全部丢失）
- [ ] git push（hook 拦截，用户手动执行）

## 下次会话建议
执行 qualix-run home-replace-renewal startup 确认状态，然后跑 Q05。
今天修复了大量 gate，finalize 时会触发新门禁拦截属正常现象，根据报错修复产物即可。
feature: /Users/zhangyiqian/git_dev/wmx-logistic-exchange/asp-aftersale-service (feature-wmx-logistic-exchange)
master: /Users/zhangyiqian/git_dev/asp-aftersale-service
