### Step 1 加载 Q05a
读取 EUT 矩阵，逐条绑定 test_file/test_method。

### Step 2 方法级追踪
验证每条 EUT 在 JUnit 方法块内有追踪标记，不用类级或文件级泛化标记替代。

### Step 3 断言补强
异常路径补充异常消息或副作用断言；gateway 空列表、防串单、文件一致性等路径补充 verify/never/ArgumentCaptor。

### Step 4 结论
Q05b 产物记录为 done=total，真实测试运行结果由独立 Maven gate 与 Q06 覆盖审计承接。
