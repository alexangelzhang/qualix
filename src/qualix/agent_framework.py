"""Multi-Agent Phase 2: 模型无关的真 Multi-Agent 框架.

支持多模型后端（Claude/OpenAI/Qwen/Kimi 等）。

架构:
  Agent → LLMBackend（抽象层）→ 具体模型 API
  Orchestrator → 调度多个 Agent → 通过文件交换数据

用法:
    from qualix.agent_framework import Agent, Orchestrator, LLMConfig

    worker = Agent(
        name="worker",
        system_prompt="...",
        model=LLMConfig(primary="claude-opus-4-6"),
    )
    result = worker.run("分析这个 PRD...")

此文件为向后兼容 facade，实际实现拆分至:
  - qualix.llm_backends: LLMConfig, LLMBackend, AnthropicBackend, OpenAICompatibleBackend, GeminiBackend, create_backend
  - qualix.agent: AgentMessage, AgentResult, Agent
  - qualix.agent_orchestrator: AgentOrchestrator
"""

from qualix.agents.agent import (
    Agent,
    AgentMessage,
    AgentResult,
)
from qualix.agents.agent_orchestrator import AgentOrchestrator
from qualix.agents.dag_scheduler import DAGScheduler
from qualix.agents.llm_backends import (
    AnthropicBackend,
    GeminiBackend,
    LLMBackend,
    LLMConfig,
    OpenAICompatibleBackend,
    create_backend,
)

__all__ = [
    "Agent",
    "AgentMessage",
    "AgentOrchestrator",
    "AgentResult",
    "AnthropicBackend",
    "DAGScheduler",
    "GeminiBackend",
    "LLMBackend",
    "LLMConfig",
    "OpenAICompatibleBackend",
    "create_backend",
]
