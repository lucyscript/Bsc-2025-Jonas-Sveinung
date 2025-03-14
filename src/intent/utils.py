"""Intent detection for WhatsApp fact-checking bot."""

import json
import logging
import re
from typing import Any, Dict, Tuple

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
    message_text: str, context: str, claims: list = [], is_reply: bool = False
) -> Tuple[str, str, bool]:
    """Generate response for fact check intent.

    Args:
        message_text: The user's message text
        context: Previous conversation context
        claims: List of claims to fact check
        is_reply: Whether this is a reply to a previously suggested claim

    Returns:
        A tuple containing (prompt, evidence_text, has_evidence)
    """
    url_match = re.search(r"https?://\S+", message_text)
    final_evidence_text = ""
    has_evidence = False

    if url_match:
        url = url_match.group(0)

        fact_results = await fact_check(url)
        evidence = clean_facts(fact_results)

        if any("error" not in item for item in evidence):
            has_evidence = True

        final_evidence_text += f"{evidence}\n"

    for claim in claims:
        try:
            logger.log(logging.INFO, f"Handling claim: {claim}")
            fact_results = await stance_detection(claim)
            evidence = clean_facts(fact_results)

            if any("error" not in item for item in evidence):
                has_evidence = True

            final_evidence_text += f"{evidence}\n"
        except Exception:
            logger.log(logging.ERROR, "Error in for loop")
            raise

    if is_reply:
        fact_check_prompt = get_prompt(
            "fact_check_reply",
            message_text=message_text,
            claim=claims[0],
            context=context,
        )
    else:
        fact_check_prompt = get_prompt(
            "fact_check",
            message_text=claims[0],
            context=context,
        )

    return fact_check_prompt, final_evidence_text, has_evidence


async def handle_general_intent(message_text: str, context: str) -> str:
    """Generate response for general conversation intent."""
    general_prompt = get_prompt(
        "general",
        message_text=message_text,
        context=context,
    )
    return await generate(general_prompt, message_text)
