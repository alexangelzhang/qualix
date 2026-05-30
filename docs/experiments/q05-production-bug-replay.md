# T12：Q05 生产缺陷回归实验协议

目标：在受控样本上度量「真实生产缺陷 → Q05 EUT 是否可稳定复现」的能力，验证 T6 三步范式与门禁是否降低漏测。

## 样本设计

- **项目数**：3（建议：不同语言栈或不同业务域，至少一个含异常分支较多的服务）。
- **每项目缺陷数**：10（从已修复的 production bug / incident ticket 抽取，含根因链接与修复 commit）。
- **入选标准**：缺陷可由单测或集成测试稳定表达；排除纯配置/纯数据问题（除非 Q05 明确覆盖此类场景）。

## 执行步骤（每 bug）

1. 在目标 commit **之前** 检出代码，确认缺陷可复现（测试失败或手工步骤）。
2. 仅使用当前 Qualix Q05 skill 与三步范式（见 `skills/unit-test-generation/references/q05-three-step-paradigm.md`）生成/补充 EUT。
3. 运行项目既有测试命令，记录是否失败（期望：在修复前 EUT 应失败）。
4. 合并修复 commit 后再次运行，记录是否通过。

## 指标

| 指标 | 定义 |
|------|------|
| EUT 复现率 | 修复前运行中，因本 bug 相关断言而失败的次数 / 有效 bug 数 |
| 假阴性率 | 修复前测试通过但生产曾失败的占比 |
| 范式遵从率 | 产物含 Step A 分支清单且 Step C 含 Exception 类 EUT 的比例（可由 `_internal/_q05_branch_inventory.json` 与 EUT 结构核对） |

## 产物

- 每项目一页原始记录表（bug id、复现命令、EUT id、修复前/后结果）。
- 汇总表：三项目 × 10 bug 的 EUT 复现率与备注。

## 自动化

清单校验与指标草稿可由仓库脚本生成：

```bash
python scripts/q05_production_bug_replay.py --template > experiment-manifest.template.json
python scripts/q05_production_bug_replay.py --manifest experiment-manifest.json
```

`experiment-manifest.json` 为 JSON 数组或 `{"runs":[...]}`，字段见脚本 `--help`。
