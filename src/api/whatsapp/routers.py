"""Enhanced WhatsApp Cloud API integration with Factiverse fact-checking."""

import logging
import os
import unicodedata
from typing import Dict

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from fastapi.responses import PlainTextResponse

from src.core.processors.processors import (
    initialize_state,
    process_fact_check_response,
    process_image_response,
    process_message_response,
    process_reaction,
    process_tracked_message,
)

VERIFY_TOKEN = os.getenv("VERIFY_TOKEN")

router = APIRouter()

logger = logging.getLogger(__name__)

message_context: Dict[str, list[str]] = {}
message_id_to_bot_message: Dict[str, str] = {}
button_id_to_claim: Dict[str, str] = {}

initialize_state(message_context, message_id_to_bot_message, button_id_to_claim)


@router.get("/webhook")
async def verify_webhook(request: Request):
    """Handles GET requests for webhook verification for WhatsApp Cloud API."""
    query_params = request.query_params
    mode = query_params.get("hub.mode")
    token = query_params.get("hub.verify_token")
    challenge = query_params.get("hub.challenge")

    if mode == "subscribe" and token == VERIFY_TOKEN:
        return PlainTextResponse(content=challenge)
    else:
        raise HTTPException(status_code=403, detail="Verification failed")


@router.post("/webhook")
async def receive_message(request: Request, background_tasks: BackgroundTasks):
    """Process incoming WhatsApp messages with context tracking."""
    try:
        payload = await request.json()

        if not all(key in payload for key in ["object", "entry"]):
            raise HTTPException(400, "Invalid webhook format")

        for entry in payload.get("entry", []):
            user_id = entry.get("id", "")
            for change in entry.get("changes", []):
                message_data = change.get("value", {})
                messages = message_data.get("messages", [])
                contacts = message_data.get("contacts", [])

                if not messages or not contacts:
                    continue

                if user_id not in message_context:
                    message_context[user_id] = []

                try:
                    message = messages[0]
                    contact = contacts[0]
                    message_type = message.get("type")
                    phone_number = contact.get("wa_id", "")
                    message_id = message.get("id", "")

                    if message_type == "text":
                        raw_text = message.get("text", {}).get("body", "")

                        message_text = (
                            unicodedata.normalize("NFKD", raw_text)
                            .replace('"', "'")
                            .strip()
                        )

                        replacements = {
                            "\xa0": " ",  # Non-breaking space
                            "\u2018": "'",  # Left single quote
                            "\u2019": "'",  # Right single quote
                            "\u201c": '"',  # Left double quote
                            "\u201d": '"',  # Right double quote
                            "\u2013": "-",  # En dash
                            "\u2014": "--",  # Em dash
                            "\u2026": "...",  # Ellipsis
                        }

                        for char, replacement in replacements.items():
                            message_text = message_text.replace(
                                char, replacement
                            )

                        logger.info(f"User: {message_text}")
                        context_info = message.get("context", {})

                        if context_info:
                            replied_to_id = context_info.get("id")
                            if replied_to_id in message_id_to_bot_message:
                                replied_to = message_id_to_bot_message[
                                    replied_to_id
                                ].replace('"', "'")

                                context = "\n".join(message_context[user_id])

                                context += (
                                    "\n\nUser is currently replying to:"
                                    f" {replied_to}\n"
                                )

                                background_tasks.add_task(
                                    process_message_response,
                                    user_id,
                                    phone_number,
                                    message_id,
                                    message_text,
                                    context,
                                    "whatsapp",
                                )
                                continue

                        message_context[user_id].append(
                            f"User: {message_text}\n"
                        )
                        context = "\n".join(message_context[user_id][:-1])
                        background_tasks.add_task(
                            process_message_response,
                            user_id,
                            phone_number,
                            message_id,
                            message_text,
                            context,
                            "whatsapp",
                        )

                    elif message_type == "interactive":
                        interactive_data = message.get("interactive", {})
                        interactive_type = interactive_data.get("type")

                        if interactive_type == "button_reply":
                            button_reply = interactive_data.get(
                                "button_reply", {}
                            )
                            button_id = button_reply.get("id")
                            button_title = button_reply.get("title")

                            if button_id in button_id_to_claim:
                                claim = button_id_to_claim[button_id]
                                context = "\n".join(message_context[user_id])

                                message_context[user_id].append(
                                    f"User selected: {button_title}\n"
                                )

                                logger.info(
                                    "User selected claim: "
                                    f"{button_title}, {claim}"
                                )

                                background_tasks.add_task(
                                    process_fact_check_response,
                                    user_id,
                                    phone_number,
                                    message_id,
                                    button_title,
                                    context,
                                    claim,
                                    "whatsapp",
                                )

                    elif message_type == "reaction":
                        reaction = message.get("reaction")
                        emoji = reaction.get("emoji")
                        id_reacted_to = reaction.get("message_id")

                        message_context[user_id].append(
                            f"User reacted with '{emoji}' "
                            f"on message '{id_reacted_to}'\n"
                        )
                        if emoji == "👍" or emoji == "👎":
                            original_text = message_id_to_bot_message.get(
                                id_reacted_to, ""
                            )
                            background_tasks.add_task(
                                process_reaction,
                                emoji,
                                original_text,
                            )

                    elif message_type == "image":
                        image_data = message.get("image", {})
                        image_id = image_data.get("id")
                        caption = image_data.get("caption", "")
                        if image_id:
                            background_tasks.add_task(
                                process_image_response,
                                user_id,
                                phone_number,
                                message_id,
                                image_id,
                                caption,
                                "whatsapp",
                            )
                        else:
                            error_msg = "No image ID found. Please try again."
                            background_tasks.add_task(
                                process_tracked_message,
                                user_id,
                                phone_number,
                                message_id,
                                error_msg,
                                None,
                                "whatsapp",
                            )

                    else:
                        error_msg = (
                            "Sorry, I can only process text and image messages."
                        )
                        background_tasks.add_task(
                            process_tracked_message,
                            user_id,
                            phone_number,
                            message_id,
                            error_msg,
                            None,
                            "whatsapp",
                        )

                except (KeyError, IndexError):
                    continue

        return {"status": "received"}
    except Exception:
        raise HTTPException(500, detail="Message processing error")
