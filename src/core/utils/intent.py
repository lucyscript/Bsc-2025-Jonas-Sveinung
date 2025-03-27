"""Intent detection for WhatsApp fact-checking bot."""

import json
import logging
from typing import Any, Dict

from src.core.config.prompts import get_prompt
from src.core.factiverse.client import (
    generate,
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
