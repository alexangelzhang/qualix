"""DQG Runtime 包：执行引擎、生命周期管理、结构化结果.

分层定位：
- runtime/ = Harness 层（通用执行引擎 + lifecycle 机制）
- handlers_execute.py / handlers_finalize.py = Domain 层（DQG 特有的 sidecar 逻辑）

Import 本包时自动注册所有 handler。
"""

from dqg.runtime.handlers_execute import register_execute_handlers
from dqg.runtime.handlers_finalize import register_finalize_handlers

# 自动注册 handler
register_execute_handlers()
register_finalize_handlers()
