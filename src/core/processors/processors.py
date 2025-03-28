"""WhatsApp message processing functions."""

import logging
from typing import Dict, List, Optional, Tuple

from src.core.client.client import generate
from src.core.handlers.handlers import (
    handle_claim_suggestions,
    handle_fact_check_intent,
    handle_image,
    handle_message_with_intent,
    handle_rating,
    handle_reaction,
)
from src.platform.telegram.utils import process_telegram_message
from src.platform.whatsapp.utils import process_whatsapp_message

logger = logging.getLogger(__name__)

message_context: Dict[str, list[str]] = {}
message_id_to_bot_message: Dict[str, str] = {}
button_id_to_claim: Dict[str, str] = {}


def initialize_state(
    context: Dict[str, list[str]],
    id_to_message: Dict[str, str],
    id_to_claim: Dict[str, str],
):
    """Initialize the state dictionaries from routers.py."""
    global message_context, message_id_to_bot_message, button_id_to_claim

    message_context = context
    message_id_to_bot_message = id_to_message
    button_id_to_claim = id_to_claim


async def process_message_response(
    user_id: str,
    phone_number: str,
    message_id: str,
    message_text: str,
    context: str,
    platform: str,
):
    """Process a message and send the response via WhatsApp."""
    try:
        result = await handle_message_with_intent(message_text, context)

        if isinstance(result, tuple) and len(result) == 3:
            buttons, btn_id_to_claim, response = result

            for btn_id, claim in btn_id_to_claim.items():
                button_id_to_claim[btn_id] = claim

            await process_tracked_message(
                user_id,
                phone_number,
                message_id,
                response,
                buttons,
                platform,
            )
        elif result:
            await process_tracked_message(
                user_id, phone_number, message_id, result, None, platform
            )
        else:
            error_msg = (
                "Sorry, I couldn't process your request. "
                "Please try again or rephrase your message."
            )
            await process_tracked_message(
                user_id, phone_number, message_id, error_msg, None, platform
            )
    except Exception as e:
        logger.error(f"Error processing message: {e}")
        error_msg = "Sorry, I encountered an error processing your request."
        await process_tracked_message(
            user_id, phone_number, message_id, error_msg, None, platform
        )


async def process_fact_check_response(
    user_id: str,
    phone_number: str,
    message_id: str,
    message_text: str,
    context: str,
    claim: str,
    platform: str,
):
    """Process a fact check request from button selection and send response."""
    try:
        result = await handle_fact_check_intent(message_text, context, [claim])

        if isinstance(result, tuple) and len(result) == 2:
            prompt, evidence_data = result

            if evidence_data.strip() == "[]":
                suggestion_data: Tuple[
                    List[Dict[str, str]], Dict[str, str], str
                ] = await handle_claim_suggestions(message_text, context)
                buttons, btn_id_to_claim, response = suggestion_data

                for btn_id, claim in btn_id_to_claim.items():
                    button_id_to_claim[btn_id] = claim

                await process_tracked_message(
                    user_id,
                    phone_number,
                    message_id,
                    response,
                    buttons,
                    platform,
                )
            else:
                response = await generate(prompt, evidence_data)
                await process_tracked_message(
                    user_id, phone_number, message_id, response, None, platform
                )
        else:
            error_msg = "Sorry, I couldn't process this fact check request."
            await process_tracked_message(
                user_id,
                phone_number,
                message_id,
                error_msg,
                None,
                platform,
            )
    except Exception as e:
        logger.error(f"Error processing fact check: {e}")
        error_msg = "Sorry, I encountered an error checking this claim."
        await process_tracked_message(
            user_id, phone_number, message_id, error_msg, None, platform
        )


async def process_image_response(
    user_id: str,
    phone_number: str,
    message_id: str,
    image_id: str,
    caption: str,
    platform: str,
):
    """Process an image message and send the response via platform."""
    try:
        text_from_image = await handle_image(image_id, caption, platform)

        message_context[user_id].append(
            f"User sent image with text: {text_from_image}\n"
        )

        if text_from_image is None or not text_from_image.strip():
            error_msg = """I can only understand text in images...\n
            No text was found in this one."""
            await process_tracked_message(
                user_id, phone_number, message_id, error_msg, None, platform
            )
            return

        context = "\n".join(message_context[user_id][:-1])
        await process_message_response(
            user_id,
            phone_number,
            message_id,
            text_from_image,
            context,
            platform,
        )

    except Exception as e:
        logger.error(f"Error processing image: {e}")
        error_msg = "Sorry, I encountered an error processing your image."
        await process_tracked_message(
            user_id, phone_number, message_id, error_msg, None, platform
        )


async def process_rating(
    rating: str,
    claim_text: str,
):
    """Process user numerical ratings (1-6) for messages."""
    try:
        success = await handle_rating(rating, claim_text)
        if not success:
            logger.warning(
                f"Failed to process rating for user: {rating} on {claim_text}"
            )
    except Exception as e:
        logger.error(f"Error in rating processing: {e}")


async def process_reaction(
    emoji: str,
    claim_text: str,
):
    """Process user reactions (emoji) to messages."""
    try:
        success = await handle_reaction(emoji, claim_text)
        if not success:
            logger.warning(
                f"Failed to process reaction for user: {emoji} on {claim_text}"
            )
    except Exception as e:
        logger.error(f"Error in reaction processing: {e}")


async def process_tracked_message(
    user_id: str,
    phone_number: str,
    message_id: str,
    response: str,
    buttons: Optional[List[Dict[str, str]]] = None,
    platform: str = "",
    add_rating: bool = True,
) -> None:
    """Send a message and track it in the context.

    Args:
        user_id: The user's ID
        phone_number: The user's phone number
        message_id: The original message ID
        response: The response text to send
        buttons: List of button objects if using interactive buttons
        platform: The platform to send the message to
        add_rating: Whether to add rating options to the message
    """
    try:
        message_context[user_id].append(f"Bot: {response}\n")

        if platform == "whatsapp":
            sent_message = await process_whatsapp_message(
                phone_number, message_id, response, buttons, add_rating
            )

            if sent_message and "messages" in sent_message:
                bot_message_id = sent_message["messages"][0]["id"]
                message_id_to_bot_message[bot_message_id] = response
        elif platform == "telegram":
            sent_message = await process_telegram_message(
                phone_number, message_id, response, buttons, add_rating
            )

            if (
                sent_message
                and "result" in sent_message
                and "message_id" in sent_message["result"]
            ):
                bot_message_id = str(sent_message["result"]["message_id"])
                message_id_to_bot_message[bot_message_id] = response
    except Exception as e:
        logger.error(f"Error sending message: {e}")
        raise
