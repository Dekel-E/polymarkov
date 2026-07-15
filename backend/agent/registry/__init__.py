"""Agent registry: formal tool/module specs (tools.py) + system prompts
(prompts/*.txt). See tools.py for the contract."""

from backend.agent.registry.tools import CANONICAL_MODULES, MODULES, PROMPT_FILES

__all__ = ["CANONICAL_MODULES", "MODULES", "PROMPT_FILES"]
