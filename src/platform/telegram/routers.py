"""Telegram router."""

import logging
import unicodedata
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request

from src.core.processors.processors import (
    button_id_to_claim,
    message_context,
    process_fact_check_response,
    process_message_response,
)
from src.platform.telegram.utils import (
    delete_webhook,
    extract_message_data,
    process_telegram_message,
    set_webhook,
)

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/tgwebhook")
async def telegram_webhook(request: Request, background_tasks: BackgroundTasks):
    """Handle incoming webhook events from Telegram."""
    try:
        update = await request.json()
        data = extract_message_data(update)

        if not data["chat_id"]:
            return {"status": "Error", "message": "Unsupported message type"}

        if data["message_type"] == "callback_query":
            callback_data = data["callback_data"]
            if callback_data in button_id_to_claim:
                claim = button_id_to_claim[callback_data]
                user_id = data["chat_id"]

                if user_id in message_context:
                    context = "\n".join(message_context[user_id])
                else:
                    context = ""

                background_tasks.add_task(
                    process_fact_check_response,
                    user_id,
                    data["chat_id"],
                    data["message_id"],
                    claim,
                    context,
                    claim,
                    "telegram",
                )

                return {"status": "processing"}

        elif data["message_type"] == "message" and data["text"]:
            user_id = data["chat_id"]
            message_text = data["text"]
            message_id = data["message_id"]

            message_text = (
                unicodedata.normalize("NFKD", message_text)
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
                message_text = message_text.replace(char, replacement)

            if user_id not in message_context:
                message_context[user_id] = []

            logger.info(f"User: {message_text}")

            message_context[user_id].append(f"User: {message_text}\n")
            context = "\n".join(message_context[user_id][:-1])

            background_tasks.add_task(
                process_message_response,
                user_id,
                data["chat_id"],
                message_id,
                message_text,
                context,
                "telegram",
            )

            return {"status": "processing"}

        return {"status": "success"}

    except Exception as e:
        logger.error(f"Error processing webhook: {str(e)}")
        return {"status": "error", "message": str(e)}


@router.post("/setup-webhook")
async def setup_webhook(webhook_url: str):
    """Set up the Telegram webhook."""
    try:
        result = await set_webhook(webhook_url)
        return {"status": "success", "result": result}
    except Exception as e:
        logger.error(f"Error setting up webhook: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/remove-webhook")
async def remove_webhook():
    """Remove the Telegram webhook."""
    try:
        result = await delete_webhook()
        return {"status": "success", "result": result}
    except Exception as e:
        logger.error(f"Error removing webhook: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/send-message")
async def send_message(
    chat_id: str, message: str, reply_to_message_id: Optional[str] = None
):
    """Manual endpoint to send a message to a Telegram chat."""
    try:
        result = await process_telegram_message(
            chat_id, reply_to_message_id, message
        )
        return {"status": "success", "result": result}
    except Exception as e:
        logger.error(f"Error sending message: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
