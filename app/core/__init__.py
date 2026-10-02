"""Core runtime for Aishin.

The core keeps identity, persistent state, memory, events and cognition separate
from any specific LLM provider.
"""

from .engine import AishinEngine

__all__ = ["AishinEngine"]
