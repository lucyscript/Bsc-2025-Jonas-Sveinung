"""Intent detection for WhatsApp fact-checking bot."""

import asyncio
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
        logger.info(f"Failed to decode intent response: {intent_response}")
        return {"intent_type": "general"}


async def handle_fact_check_intent(
    message_text: str, context: str, claims: list = []
) -> Tuple[str, str]:
    """Generate response for fact check intent.

    Args:
        message_text: The user's message text
        context: Previous conversation context
        claims: List of claims to fact check

    Returns:
        A tuple containing (prompt, evidence_text)
    """
    url_match = re.search(r"https?://\S+", message_text)
    final_evidence_text = ""

    if url_match:
        url = url_match.group(0)
        fact_results = await fact_check(url)
        evidence = clean_facts(fact_results)

        final_evidence_text += f"{evidence}\n"

    if claims:
        try:
            claim_tasks = [stance_detection(claim) for claim in claims]
            logger.info(
                f"Created {len(claim_tasks)} tasks for claims processing"
            )
            fact_results_list = await asyncio.gather(
                *claim_tasks, return_exceptions=True
            )

            for i, result in enumerate(fact_results_list):
                if isinstance(result, Exception):
                    logger.error(
                        f"Error processing claim {claims[i]}: {str(result)}"
                    )
                    continue

                if not isinstance(result, BaseException):
                    evidence = clean_facts(result)
                    final_evidence_text += f"{evidence}\n"

        except Exception as e:
            logger.error(f"Error in concurrent claim processing: {str(e)}")
            raise

    fact_check_prompt = get_prompt(
        "fact_check",
        message_text=message_text,
        context=context,
    )

    return fact_check_prompt, final_evidence_text


async def handle_general_intent(message_text: str, context: str) -> str:
    """Generate response for general conversation intent."""
    general_prompt = get_prompt(
        "general",
        message_text=message_text,
        context=context,
    )
    return await generate(general_prompt, message_text)
