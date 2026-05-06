# Judge 提取的 Bug Case

- 项目: shuangzhou-v4
- Phase: Q05
- 维度: eut_coverage (3/5)
- 时间: 2026-04-29T16:41:13.595006

## 问题描述

VIN 半隐藏规则(BR-026) 无独立 EUT，desensitizaChar(EUT-030) 是通用方法测试，未验证 VIN 特定的后8位逻辑

