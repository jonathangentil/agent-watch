"""Passive collectors implementing the shared ScanResult contract."""
from .alethe import AletheAdapter
from .claude import ClaudeAdapter
from .codex import CodexAdapter

__all__ = ["AletheAdapter", "ClaudeAdapter", "CodexAdapter"]
