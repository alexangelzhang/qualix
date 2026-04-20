---
name: skill-audit
description: 审计已安装 skill 的 description 压缩、6 维质量评估、安全扫描。基于 SkillReducer + Skill-Insight + SkillProbe。
triggers:
  - /skill-audit
  - 审计 skill
  - skill 瘦身
  - skill 安全
---

# Skill Audit — 全面质量审计

综合 SkillReducer (arXiv:2603.29919)、Skill-Insight (openEuler) 和 SkillProbe (arXiv:2603.21019) 的方法，对已安装 skill 进行三层审计：description 压缩、质量评估、安全扫描。

## 审计模式

用户可以选择执行哪些层：

- `/skill-audit` — 执行全部三层
- `/skill-audit desc` — 只做 description 压缩
- `/skill-audit quality` — 只做质量评估
- `/skill-audit security` — 只做安全扫描

---

## 第一层：Description 压缩（SkillReducer）

每个 skill 的 description 都会注入 system prompt。SkillReducer 发现压缩 48% 后功能质量反而提升 2.8%。

### 扫描脚本

```bash
python3 << 'PYEOF'
import os, re, glob

skills_dirs = [
    os.path.expanduser("~/.claude/skills"),
    os.path.expanduser("~/.claude/plugins/marketplaces/anthropic-agent-skills/skills"),
    os.path.expanduser("~/.claude/plugins/marketplaces/superpowers-marketplace/skills"),
]
for d in glob.glob(os.path.expanduser("~/.claude/plugins/cache/*/*/skills")):
    skills_dirs.append(d)

results = []
seen = set()
for base in skills_dirs:
    for root, dirs, files in os.walk(base):
        if "SKILL.md" in files:
            path = os.path.join(root, "SKILL.md")
            skill_name = os.path.basename(root)
            if skill_name in seen:
                continue
            seen.add(skill_name)
            try:
                content = open(path).read()
                fm_match = re.search(r'^---\s*\n(.*?)\n---', content, re.DOTALL)
                desc = ""
                if fm_match:
                    fm = fm_match.group(1)
                    desc_match = re.search(r'description:\s*(.+?)(?:\n[a-z]|\n---|\Z)', fm, re.DOTALL)
                    if desc_match:
                        desc = desc_match.group(1).strip().strip('"').strip("'")
                desc_words = len(desc.split())
                results.append((skill_name, desc_words, len(content), desc, path))
            except:
                pass

results.sort(key=lambda x: x[1], reverse=True)
for name, dw, bc, desc, path in results:
    flag = "🔴" if dw > 50 else "🟡" if dw > 30 else "🟢"
    print(f"{flag} {name}: {dw} words, body {bc} chars")
    if dw > 50:
        print(f"   PATH: {path}")
        print(f"   DESC: {desc[:200]}")
        print()
PYEOF
```

### 压缩规则

一个好的 description 只需要三个路由信号：
1. **Primary Capability** — 做什么（1 句话）
2. **Trigger Conditions** — 什么时候触发
3. **Unique Identifier** — 和其他 skill 的区分点

目标：每个 description 控制在 20-40 words（中文 15-30 字）。

---

## 第二层：6 维质量评估（Skill-Insight）

对每个 skill 的 SKILL.md 进行 6 个维度评估，每维度 1-5 分：

### 评估维度

| 维度 | 评估标准 | 常见问题 |
|------|---------|---------|
| **职责明确性** | skill 是否只做一件事？边界是否清晰？ | 一个 skill 包揽太多不相关功能 |
| **结构规范性** | frontmatter 完整？步骤有序？格式一致？ | 缺 description/triggers，步骤混乱 |
| **指令适配性** | 指令是否足够具体让 LLM 正确执行？ | 过于模糊（"做好它"）或过于死板 |
| **内容一致性** | description 声明的能力和 body 实际内容是否匹配？ | Over-declaration（声明能做但 body 没教怎么做）或 Under-declaration（body 有隐藏功能） |
| **风险可控性** | 是否有危险操作？是否有用户确认环节？ | 无确认直接删除文件、执行 rm -rf |
| **脚本/引用质量** | 引用的脚本/reference 是否存在且有效？ | 引用了不存在的文件，脚本有语法错误 |

### 评估流程

1. 读取 SKILL.md 全文
2. 逐维度打分（1-5），附一句话理由
3. 总分 < 18 的标记为 🔴 需要改进，18-24 标记为 🟡 可优化，25-30 标记为 🟢 良好
4. 对 🔴 skill 生成具体改进建议

### 语义-行为一致性检测（SkillProbe）

特别关注第 4 维"内容一致性"，检查：
- **Over-declaration**：description 说能做 X，但 body 里没有关于 X 的指令
- **Under-declaration**：body 里有功能 Y，但 description 没提到（shadow function）
- **Mixed**：部分匹配，部分偏差

---

## 第三层：安全扫描（SkillProbe）

对每个 skill 的 body 和引用脚本进行安全检查：

### 检查项

| 检查项 | 严重度 | 示例 |
|--------|--------|------|
| **危险命令** | 🔴 Critical | `rm -rf`、`chmod 777`、`curl \| bash`、`eval` |
| **敏感路径访问** | 🔴 Critical | 读写 `~/.ssh/`、`~/.aws/`、`/etc/passwd` |
| **网络外传** | 🟡 Warning | `curl -X POST` 到外部 URL、`wget` 下载未知脚本 |
| **过度权限** | 🟡 Warning | 要求 sudo、修改系统配置 |
| **无确认破坏性操作** | 🟡 Warning | 删除文件/分支/数据库操作没有用户确认步骤 |
| **环境变量泄露** | 🟡 Warning | 打印或传输 API key、token |

### 扫描方法

1. 用 Grep 扫描 SKILL.md 和 scripts/ 目录下的所有文件
2. 匹配危险模式（正则）
3. 对每个匹配项判断是否在安全上下文中（如有 `--dry-run` 或用户确认步骤则降级）
4. 输出安全报告

---

## 输出格式

```markdown
# Skill Audit Report — {date}

## 概览
- 扫描 skill 数: {N}
- Description 🔴: {n1} / 🟡: {n2} / 🟢: {n3}
- 质量评估 🔴: {n4} / 🟡: {n5} / 🟢: {n6}
- 安全问题: {n7} Critical / {n8} Warning

## Description 压缩建议
| Skill | 原始 | 压缩后 | 压缩率 |
...

## 质量评估详情
| Skill | 职责 | 结构 | 指令 | 一致性 | 风险 | 脚本 | 总分 |
...

## 安全问题
| Skill | 严重度 | 问题 | 位置 |
...

## Top 5 改进建议
1. ...
```

## 约束

- 不自动修改任何文件，所有修改需用户确认
- 插件目录下的 skill 提醒用户会被更新覆盖
- 安全扫描只做静态分析，不执行任何代码
- 质量评估基于 SKILL.md 内容，不测试实际执行效果
