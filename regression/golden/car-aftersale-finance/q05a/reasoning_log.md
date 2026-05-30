### Step 1 读取 Q01
读取 4 条 REQ、11 条 BR、16 条 SE，并将 BR-010/SE-015/SE-016 作为外部系统或缺实现证据的 non_testable，不伪造后端可测项。

### Step 2 Java 结构扫描
用 stdlib 正则按类名/方法名定位 Java 方法块，识别 happy、boundary、exception、defense 分支，并将 line_start 绑定到真实方法块内。

### Step 3 分支清单到业务后果
为每个方法分支生成 B-*，为每个 B-* 生成 O-*，再把 EUT 显式绑定到 branch_ids/outcome_ids，形成“分支清单 -> 业务后果 -> EUT”的机器链路。

### Step 4 Q01 覆盖补齐
补齐 REQ-001、REQ-003、SE-001、SE-002、SE-004、SE-009 的 EUT 绑定，并复用真实测试方法增加可追踪 EUT 标记。

### Step 5 结论
Q05a 已具备 Java-only standalone 的轻量结构分析产物；未实现或外部系统项保留为 non_testable/GAP，不在 EUT 中伪通过。
