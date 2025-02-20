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
    return PROMPTS[key].format(**kwargs).strip()
