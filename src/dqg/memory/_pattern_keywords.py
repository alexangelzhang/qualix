"""共享模式关键词：knowledge_network 和 hyperedge 共用."""

from __future__ import annotations

from types import MappingProxyType
from typing import Final

PATTERN_KEYWORDS: Final = MappingProxyType({
    "并发": ["并发", "幂等", "锁", "竞争", "冲突"],
    "权限": ["权限", "隔离", "越权", "鉴权", "角色"],
    "状态机": ["状态机", "状态流转", "状态迁移", "驳回", "循环"],
    "金额": ["金额", "计算", "精度", "BigDecimal", "分"],
    "超时": ["超时", "重试", "降级", "熔断", "补偿"],
    "通知": ["通知", "消息", "推送", "飞书", "提醒"],
    "导出": ["导出", "异步", "大数据量"],
    "缓存": ["缓存", "失效", "一致性"],
})
