"""Centralized prompt templates for fact-checking responses."""

import json
from pathlib import Path

PROMPTS_FILE = Path(__file__).parent / "prompts.json"


def _load_prompts():
    with open("src/config/prompts.json", "r", encoding="utf-8") as f:
        return json.load(f)


PROMPTS = _load_prompts()


def get_prompt(key: str, **kwargs) -> str:
    """Get formatted prompt template with keyword arguments."""
    # Sanitize user-provided fields that might contain quotes
    sanitized_kwargs = {
        k: v.replace('"', "'") if isinstance(v, str) else v
        for k, v in kwargs.items()
    }

    return PROMPTS[key].format(**sanitized_kwargs).strip()
