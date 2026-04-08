"""模型注册表：感知当前使用的模型，提供 token budget 计算.

支持的模型族：
- Claude (Opus/Sonnet/Haiku)
- GPT-4 系列
- Qwen 系列
- 通用 fallback
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelProfile:
    """模型能力描述."""

    name: str
    context_window: int  # 总 token 数
    output_limit: int  # 最大输出 token
    reserve_for_output: int  # 为输出预留的 token
    reserve_for_prompt: int  # 为 skill prompt 预留的 token

    @property
    def available_for_context(self) -> int:
        """可用于注入上游产物的 token 数."""
        return self.context_window - self.reserve_for_output - self.reserve_for_prompt


# 常见模型配置
_MODELS: dict[str, ModelProfile] = {
    # Claude 系列
    "claude-opus-4": ModelProfile("claude-opus-4", 200_000, 32_000, 32_000, 15_000),
    "claude-sonnet-4": ModelProfile("claude-sonnet-4", 200_000, 16_000, 16_000, 15_000),
    "claude-haiku-3.5": ModelProfile("claude-haiku-3.5", 200_000, 8_192, 10_000, 15_000),
    "claude-opus-4-1m": ModelProfile("claude-opus-4-1m", 1_000_000, 32_000, 32_000, 15_000),
    "claude-sonnet-4-1m": ModelProfile("claude-sonnet-4-1m", 1_000_000, 16_000, 16_000, 15_000),
    # GPT 系列
    "gpt-4o": ModelProfile("gpt-4o", 128_000, 16_384, 16_384, 10_000),
    "gpt-4-turbo": ModelProfile("gpt-4-turbo", 128_000, 4_096, 8_000, 10_000),
    # Qwen 系列
    "qwen-max": ModelProfile("qwen-max", 128_000, 8_192, 10_000, 10_000),
    "qwen-plus": ModelProfile("qwen-plus", 128_000, 8_192, 10_000, 10_000),
}

# 默认 fallback：保守估计
_DEFAULT = ModelProfile("unknown", 128_000, 8_192, 10_000, 10_000)


def get_model_profile(model_name: str | None = None) -> ModelProfile:
    """获取模型配置.

    支持模糊匹配：'claude-opus-4-6[1m]' → 'claude-opus-4-1m'
    """
    if not model_name:
        return _DEFAULT

    name = model_name.lower().strip()

    # 精确匹配
    if name in _MODELS:
        return _MODELS[name]

    # 模糊匹配
    if "opus" in name and "1m" in name:
        return _MODELS["claude-opus-4-1m"]
    if "sonnet" in name and "1m" in name:
        return _MODELS["claude-sonnet-4-1m"]
    if "opus" in name:
        return _MODELS["claude-opus-4"]
    if "sonnet" in name:
        return _MODELS["claude-sonnet-4"]
    if "haiku" in name:
        return _MODELS["claude-haiku-3.5"]
    if "gpt-4o" in name:
        return _MODELS["gpt-4o"]
    if "gpt-4" in name:
        return _MODELS["gpt-4-turbo"]
    if "qwen" in name and "max" in name:
        return _MODELS["qwen-max"]
    if "qwen" in name:
        return _MODELS["qwen-plus"]

    return _DEFAULT


def estimate_tokens(text: str) -> int:
    """粗略估算文本的 token 数.

    中文约 1.5 token/字，英文约 1.3 token/word。
    这里用简单的字符数估算，偏保守。
    """
    if not text:
        return 0
    # 单次线性扫描：CJK 字符按空格处理，非 CJK 连续片段按词计数。
    cjk_count = 0
    word_count = 0
    in_word = False

    for char in text:
        is_cjk = "\u4e00" <= char <= "\u9fff"
        if is_cjk:
            cjk_count += 1
            in_word = False
            continue

        if char.isspace():
            in_word = False
            continue

        if not in_word:
            word_count += 1
            in_word = True

    return int(cjk_count * 1.5 + word_count * 1.3)
