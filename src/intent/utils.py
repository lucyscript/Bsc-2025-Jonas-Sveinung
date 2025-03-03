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
        sentiment=intent_data.get("sentiment", "neutral"),
    )
    return await generate(greeting_prompt)


async def handle_help_intent(intent_data: Dict[str, Any], context: str) -> str:
    """Generate response for help request intent."""
    question = intent_data.get("question", "")
    question_text = f"They specifically asked: '{question}'" if question else ""

    help_prompt = get_prompt(
        "help_response",
        context=context,
        help_type=intent_data.get("help_type", "general"),
        confidence=intent_data.get("confidence", 0.8),
        question_text=question_text,
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
        sentiment=intent_data.get("sentiment", "neutral"),
    )
    return await generate(clarification_prompt)


async def handle_source_intent(
    intent_data: Dict[str, Any], context: str
) -> str:
    """Generate response for source request intent."""
    question = intent_data.get("question", "")
    question_text = f"They specifically asked: '{question}'" if question else ""

    source_prompt = get_prompt(
        "source_response",
        context=context,
        topic=intent_data.get("topic", ""),
        question_text=question_text,
        sentiment=intent_data.get("sentiment", "neutral"),
    )
    return await generate(source_prompt)


async def handle_off_topic_intent(
    intent_data: Dict[str, Any], context: str
) -> str:
    """Generate response for off-topic conversation intent."""
    question = intent_data.get("question", "")
    question_text = f"They specifically asked: '{question}'" if question else ""

    off_topic_prompt = get_prompt(
        "off_topic_response",
        context=context,
        topic=intent_data.get("topic", ""),
        question_text=question_text,
        sentiment=intent_data.get("sentiment", "neutral"),
    )
    return await generate(off_topic_prompt)


async def handle_unknown_intent(
    intent_data: Dict[str, Any], context: str
) -> str:
    """Generate response for unknown or unclear intent."""
    question = intent_data.get("question", "")
    question_text = f"They might be asking: '{question}'" if question else ""

    unknown_prompt = get_prompt(
        "unknown_intent_response",
        context=context,
        topic=intent_data.get("topic", ""),
        question_text=question_text,
    )
    return await generate(unknown_prompt)
