"""评估器模块，按需导入以保持静态校验不依赖模型配置。"""

from typing import Any

__all__ = [
    "BaseEvaluator",
    "IntentEvaluator",
    "ExtractionEvaluator",
    "MemoryEvaluator",
    "ContextCompressionEvaluator",
]


def __getattr__(name: str) -> Any:
    if name == "BaseEvaluator":
        from .base import BaseEvaluator

        return BaseEvaluator
    if name == "IntentEvaluator":
        from .intent_evaluator import IntentEvaluator

        return IntentEvaluator
    if name == "ExtractionEvaluator":
        from .extraction_evaluator import ExtractionEvaluator

        return ExtractionEvaluator
    if name == "MemoryEvaluator":
        from .memory_evaluator import MemoryEvaluator

        return MemoryEvaluator
    if name == "ContextCompressionEvaluator":
        from .context_compression_evaluator import ContextCompressionEvaluator

        return ContextCompressionEvaluator
    raise AttributeError(name)
