"""Intent detection for WhatsApp fact-checking bot."""

import json
import logging
from typing import Any, Dict

from src.config.prompts import get_prompt
from src.fact_checker.utils import (
    clean_facts,
    detect_claims,
    generate,
    get_microfacts,
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
        return {
            "intent_type": "fact_check",
            "confidence": 0.7,
            "sentiment": "neutral",
            "context_reference": False,
            "url_present": False,
        }


async def handle_fact_check_intent(
    intent_data: Dict[str, Any], message_text: str, context: str
) -> str:
    """Generate response for fact check intent."""
    claims = await detect_claims(message_text)
    final_evidence_text = ""

    if claims:
        for claim in claims:
            try:
                fact_results = await stance_detection(claim)

                relevant_results = clean_facts(fact_results)

                evidence_text = json.dumps(relevant_results, ensure_ascii=False)
                final_evidence_text += f"{evidence_text}\n"

            except Exception as e:
                logger.error(f"Stance detection failed: {str(e)}")

        fact_check_prompt = get_prompt(
            "fact_check",
            message_text=message_text,
            context=context,
            confidence=intent_data.get("confidence", 0.8),
            sentiment=intent_data.get("sentiment", "neutral"),
        )

        return await generate(fact_check_prompt, final_evidence_text)
    else:
        general_prompt = get_prompt(
            "general",
            message_text=message_text,
            context=context,
            topic=intent_data.get("topic", ""),
            question=intent_data.get("question", ""),
            sentiment=intent_data.get("sentiment", "neutral"),
            context_reference=str(
                intent_data.get("context_reference", False)
            ).lower(),
        )
        return await generate(general_prompt)


async def handle_check_fact_intent(
    intent_data: Dict[str, Any], message_text: str, context: str
) -> str:
    """Generate response for check fact intent using microfacts."""
    microfacts_data = await get_microfacts(message_text)

    topic = intent_data.get("topic", "")
    question = intent_data.get("question", "")

    if (
        microfacts_data
        and microfacts_data.get("spots")
        and len(microfacts_data.get("spots")) > 0
    ):
        if not topic and microfacts_data.get("spots"):
            first_spot = microfacts_data.get("spots")[0]
            if first_spot.get("entity") and first_spot.get("entity").get(
                "title"
            ):
                topic = first_spot.get("entity").get("title")

    check_fact_prompt = get_prompt(
        "check_fact",
        message_text=message_text,
        context=context,
        topic=topic,
        question=question or message_text,
        sentiment=intent_data.get("sentiment", "neutral"),
    )

    if microfacts_data:
        return await generate(check_fact_prompt, json.dumps(microfacts_data))

    return await generate(check_fact_prompt)


async def handle_bot_help_intent(
    intent_data: Dict[str, Any], message_text: str, context: str
) -> str:
    """Generate response for bot help intent."""
    bot_help_prompt = get_prompt(
        "bot_help",
        message_text=message_text,
        context=context,
        topic=intent_data.get("topic", ""),
        question=intent_data.get("question", ""),
        sentiment=intent_data.get("sentiment", "neutral"),
    )
    return await generate(bot_help_prompt)


async def handle_general_intent(
    intent_data: Dict[str, Any], message_text: str, context: str
) -> str:
    """Generate response for general conversation intent."""
    general_prompt = get_prompt(
        "general",
        message_text=message_text,
        context=context,
        topic=intent_data.get("topic", ""),
        question=intent_data.get("question", ""),
        sentiment=intent_data.get("sentiment", "neutral"),
        context_reference=str(
            intent_data.get("context_reference", False)
        ).lower(),
    )
    return await generate(general_prompt)
