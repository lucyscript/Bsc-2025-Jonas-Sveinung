"""Intent detection for WhatsApp fact-checking bot."""

import json
import logging
import re
from typing import Any, Dict

from src.config.prompts import get_prompt
from src.fact_checker.utils import (
    clean_facts,
    fact_check,
    generate,
    stance_detection,
)

logger = logging.getLogger(__name__)


async def detect_intent(message_text: str, context: str = "") -> Dict[str, Any]:
    """Detect the user's intent from their message.

    Args:
        message_text: The user's message text
        context: Previous conversation context

    Returns:
        Dictionary containing intent type and relevant details
    """
    intent_prompt = get_prompt(
        "intent_detection", message_text=message_text, context=context
    )

    intent_response = await generate(intent_prompt, message_text)
    try:
        intent_data = json.loads(intent_response)
        return intent_data
    except json.JSONDecodeError:
        return {"intent_type": "fact_check", "short_message": True}


async def handle_fact_check_intent(
    message_text: str, context: str, claims: list = []
) -> str:
    """Generate response for fact check intent."""
    url_match = re.search(r"https?://\S+", message_text)
    final_evidence_text = ""

    if url_match:
        url = url_match.group(0)

        fact_results = await fact_check(url)
        relevant_results = clean_facts(fact_results)
        evidence_text = json.dumps(relevant_results, ensure_ascii=False)
        final_evidence_text += f"{evidence_text}\n"

    for claim in claims:
        try:
            print(f"Claim: {claim}")
            fact_results = await stance_detection(claim)
            relevant_results = clean_facts(fact_results)
            evidence_text = json.dumps(relevant_results, ensure_ascii=False)
            final_evidence_text += f"{evidence_text}\n"
        except Exception as e:
            raise e

    fact_check_prompt = get_prompt(
        "fact_check",
        message_text=message_text,
        context=context,
    )

    return await generate(fact_check_prompt, final_evidence_text)


async def handle_bot_help_intent(message_text: str, context: str) -> str:
    """Generate response for bot help intent."""
    bot_help_prompt = get_prompt(
        "bot_help",
        message_text=message_text,
        context=context,
    )
    return await generate(bot_help_prompt)


async def handle_general_intent(message_text: str, context: str) -> str:
    """Generate response for general conversation intent."""
    general_prompt = get_prompt(
        "general",
        message_text=message_text,
        context=context,
    )
    return await generate(general_prompt)
