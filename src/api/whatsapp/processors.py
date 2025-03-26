"""WhatsApp message processing functions."""

import logging
from typing import Dict, List, Optional, Tuple

from src.api.whatsapp.utils import (
    send_interactive_buttons,
    send_whatsapp_message,
)
from src.core.client.client import generate
from src.core.handlers.handlers import (
    handle_claim_suggestions,
    handle_fact_check_intent,
    handle_image,
    handle_message_with_intent,
    handle_reaction,
)

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


async def process_tracked_message(
    phone_number: str,
    message_id: str,
    response: str,
    buttons: Optional[List[Dict[str, str]]] = None,
) -> None:
    """Send a message and track it in the context.

    Args:
        phone_number: The user's phone number
        message_id: The original message ID
        response: The response text to send
        buttons: List of button objects if using interactive buttons
    """
    try:
        if buttons:
            sent_message = await send_interactive_buttons(
                phone_number, response, buttons, message_id
            )
        else:
            sent_message = await send_whatsapp_message(
                phone_number, response, message_id
            )

        message_context[phone_number].append(f"Bot: {response}\n")

        if sent_message and "messages" in sent_message:
            bot_message_id = sent_message["messages"][0]["id"]
            message_id_to_bot_message[bot_message_id] = response
    except Exception as e:
        logger.error(f"Error sending message: {e}")
        raise


async def process_message_response(
    phone_number: str,
    message_id: str,
    message_text: str,
    context: str,
):
    """Process a message and send the response via WhatsApp."""
    try:
        result = await handle_message_with_intent(message_text, context)

        if isinstance(result, tuple) and len(result) == 3:
            buttons, btn_id_to_claim, response = result

            for btn_id, claim in btn_id_to_claim.items():
                button_id_to_claim[btn_id] = claim

            await process_tracked_message(
                phone_number,
                message_id,
                response,
                buttons=buttons,
            )
        elif result:
            await process_tracked_message(phone_number, message_id, result)
        else:
            error_msg = (
                "Sorry, I couldn't process your request. "
                "Please try again or rephrase your message."
            )
            await process_tracked_message(phone_number, message_id, error_msg)
    except Exception as e:
        logger.error(f"Error processing message: {e}")
        error_msg = "Sorry, I encountered an error processing your request."
        await process_tracked_message(phone_number, message_id, error_msg)


async def process_fact_check_response(
    phone_number: str,
    message_id: str,
    message_text: str,
    context: str,
    claim: str,
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
                    phone_number,
                    message_id,
                    response,
                    buttons=buttons,
                )
            else:
                response = await generate(prompt, evidence_data)
                await process_tracked_message(
                    phone_number, message_id, response
                )
        else:
            error_msg = "Sorry, I couldn't process this fact check request."
            await process_tracked_message(phone_number, message_id, error_msg)
    except Exception as e:
        logger.error(f"Error processing fact check: {e}")
        error_msg = "Sorry, I encountered an error checking this claim."
        await process_tracked_message(phone_number, message_id, error_msg)


async def process_image_response(
    phone_number: str,
    message_id: str,
    image_id: str,
    caption: str,
):
    """Process an image message and send the response via WhatsApp."""
    try:
        text_from_image = await handle_image(image_id, caption)

        message_context[phone_number].append(
            f"User sent image with text: {text_from_image}\n"
        )

        if not text_from_image.strip():
            error_msg = """I can only understand text in images...\n
            No text was found in this one."""
            await process_tracked_message(phone_number, message_id, error_msg)
            return

        context = "\n".join(message_context[phone_number][:-1])
        await process_message_response(
            phone_number, message_id, text_from_image, context
        )

    except Exception as e:
        logger.error(f"Error processing image: {e}")
        error_msg = "Sorry, I encountered an error processing your image."
        await process_tracked_message(phone_number, message_id, error_msg)


async def process_reaction(
    emoji: str,
    claim_text: str,
    phone_number: str,
):
    """Process user reactions (emoji) to messages."""
    try:
        success = await handle_reaction(emoji, claim_text)
        if not success:
            logger.warning(
                "Failed to process reaction for user "
                f"{phone_number}: {emoji} on {claim_text}"
            )
    except Exception as e:
        logger.error(f"Error in reaction processing: {e}")
