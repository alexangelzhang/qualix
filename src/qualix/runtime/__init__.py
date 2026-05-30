"""DQG Runtime 包：执行引擎、生命周期管理、结构化结果.

分层定位：
- runtime/ = Harness 层（通用执行引擎 + lifecycle 机制）
- handlers/ = Domain 层（DQG 特有的 sidecar 逻辑 + 流程完整性检查）

Import 本包时自动注册所有 handler。
"""

from __future__ import annotations

from qualix.compat import install_module_aliases
from qualix.runtime.handlers.handlers_execute import register_execute_handlers
from qualix.runtime.handlers.handlers_finalize import register_finalize_handlers
from qualix.runtime.handlers.handlers_flow_integrity import register_flow_integrity_handler

# 自动注册 handler
register_execute_handlers()
register_finalize_handlers()
register_flow_integrity_handler()

_ALIASES: dict[str, str] = {
    "qualix.runtime.handler_utils": "qualix.runtime.handlers.handler_utils",
    "qualix.runtime.handlers_detection": "qualix.runtime.handlers.handlers_detection",
    "qualix.runtime.handlers_execute": "qualix.runtime.handlers.handlers_execute",
    "qualix.runtime.handlers_finalize": "qualix.runtime.handlers.handlers_finalize",
    "qualix.runtime.handlers_flow_integrity": "qualix.runtime.handlers.handlers_flow_integrity",
    "qualix.runtime.handlers_prompt_policy": "qualix.runtime.handlers.handlers_prompt_policy",
    "qualix.runtime.handlers_protocol": "qualix.runtime.handlers.handlers_protocol",
    "qualix.runtime.handlers_superset": "qualix.runtime.handlers.handlers_superset",
}

install_module_aliases(_ALIASES, __name__)
