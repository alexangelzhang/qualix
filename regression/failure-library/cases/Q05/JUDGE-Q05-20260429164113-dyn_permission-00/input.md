# Judge 提取的 Bug Case

- 项目: shuangzhou-v4
- Phase: Q05
- 维度: dyn_permission (2/5)
- 时间: 2026-04-29T16:41:13.595006

## 问题描述

SE-014（授权店与直营店隔离）仅通过 EUT-003/013/014 验证了 isCarAuthorityBusinessMode 的 true/false，未验证直营店调用提前交车接口时的拦截行为

