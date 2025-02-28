"""Intent detection for WhatsApp fact-checking bot."""

import json
import logging
from typing import Any, Dict

from src.config.prompts import get_prompt
from src.fact_checker.utils import generate

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
    print(f"INTENT RESPONSE: {intent_response}")
    try:
        intent_data = json.loads(intent_response)
        return intent_data
    except json.JSONDecodeError:
        return {
            "intent_type": "fact_check_request",
            "confidence": 0.7,
            "has_question": False,
        }


async def handle_greeting_intent(
    intent_data: Dict[str, Any], context: str
) -> str:
    """Generate response for greeting intent."""
    greeting_prompt = get_prompt(
        "greeting_response",
        context=context,
        confidence=intent_data.get("confidence", 0.9),
    )
    return await generate(greeting_prompt)


async def handle_help_intent(intent_data: Dict[str, Any], context: str) -> str:
    """Generate response for help request intent."""
    help_prompt = get_prompt(
        "help_response",
        context=context,
        help_type=intent_data.get("help_type", "general"),
    )
    return await generate(help_prompt)


async def handle_clarification_intent(
    intent_data: Dict[str, Any], context: str
) -> str:
    """Generate response for clarification request intent."""
    clarification_prompt = get_prompt(
        "clarification_response",
        context=context,
        topic=intent_data.get("topic", ""),
        question=intent_data.get("question", ""),
    )
    return await generate(clarification_prompt)


async def handle_source_intent(
    intent_data: Dict[str, Any], context: str
) -> str:
    """Generate response for source request intent."""
    source_prompt = get_prompt(
        "source_response", context=context, topic=intent_data.get("topic", "")
    )
    return await generate(source_prompt)


async def handle_feedback_intent(
    intent_data: Dict[str, Any], context: str
) -> str:
    """Generate response for user feedback intent."""
    sentiment = intent_data.get("sentiment", "neutral")
    feedback_prompt = get_prompt(
        "feedback_response", context=context, sentiment=sentiment
    )
    return await generate(feedback_prompt)


async def handle_off_topic_intent(
    intent_data: Dict[str, Any], context: str
) -> str:
    """Generate response for off-topic conversation intent."""
    off_topic_prompt = get_prompt(
        "off_topic_response",
        context=context,
        topic=intent_data.get("topic", ""),
    )
    return await generate(off_topic_prompt)


async def handle_unknown_intent(
    intent_data: Dict[str, Any], context: str
) -> str:
    """Generate response for unknown or unclear intent."""
    unknown_prompt = get_prompt("unknown_intent_response", context=context)
    return await generate(unknown_prompt)
