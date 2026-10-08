"""History provider abstraction.

AIOS never touches agent-history storage internals directly:

    AIOS -> HistoryProvider -> OpenCodeHistoryProvider -> opencode.db / CLI
"""
from .base import (
    HistoryProvider,
    HistoryProviderError,
    SessionContext,
    SessionInfo,
)
from .opencode_history import OpenCodeHistoryProvider

__all__ = [
    "HistoryProvider",
    "HistoryProviderError",
    "SessionContext",
    "SessionInfo",
    "OpenCodeHistoryProvider",
]
