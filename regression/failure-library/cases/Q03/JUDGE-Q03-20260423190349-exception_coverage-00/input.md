# Judge 提取的 Bug Case

- 项目: shuangzhou-v4
- Phase: Q03
- 维度: exception_coverage (3/5)
- 时间: 2026-04-23T19:03:49.617805

## 问题描述

异常矩阵仅 6 行，缺少 3 类标准异常：(1) 数据库唯一键冲突；(2) 乐观锁冲突（无 version 字段，应分析是否需要）；(3) BPM 流程 key 配置错误时的处理

## 证据

标准 9 类异常矩阵 vs 报告中仅覆盖 6 类
