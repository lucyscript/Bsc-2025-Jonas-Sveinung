"""Utility functions for WhatsApp API integration."""

import logging
import os

import aiohttp
from fastapi import HTTPException

logger = logging.getLogger(__name__)

WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN")
PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID")


async def send_whatsapp_message(phone_number: str, message: str, reply_to: str):
    """Send message via WhatsApp Cloud API with length validation."""
    MAX_WHATSAPP_LENGTH = 4096
    if len(message) > MAX_WHATSAPP_LENGTH:
        logger.warning(
            f"Message truncated from {len(message)} to {MAX_WHATSAPP_LENGTH} "
        )
        message = message[: MAX_WHATSAPP_LENGTH - 3] + "..."

    url = f"https://graph.facebook.com/v22.0/{PHONE_NUMBER_ID}/messages"

    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json",
    }

    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": phone_number,
        "context": {"message_id": reply_to},
        "text": {"body": message},
    }

    try:
        timeout = aiohttp.ClientTimeout(total=30)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(
                url, json=payload, headers=headers
            ) as response:
                if response.status >= 400:
                    error_text = await response.text()
                    logger.error(f"WhatsApp API error: {error_text}")
                    raise HTTPException(
                        status_code=response.status,
                        detail="Failed to send WhatsApp message",
                    )
                return await response.json()

    except aiohttp.ClientError as e:
        logger.error(f"WhatsApp API error: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="Failed to send WhatsApp message",
        )


async def send_interactive_buttons(
    phone_number: str, message: str, buttons: list, reply_to: str
):
    """Send interactive button message via WhatsApp Cloud API.

    Args:
        phone_number: The recipient's phone number
        message: The message body text
        buttons: List of button objects with 'id' and 'title' fields
        reply_to: Optional message ID to reply to
    """
    url = f"https://graph.facebook.com/v22.0/{PHONE_NUMBER_ID}/messages"

    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json",
    }

    formatted_buttons = []
    for button in buttons[:3]:
        formatted_buttons.append(
            {
                "type": "reply",
                "reply": {
                    "id": button["id"],
                    "title": button["title"],
                },
            }
        )

    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": phone_number,
        "type": "interactive",
        "context": {"message_id": reply_to},
        "interactive": {
            "type": "button",
            "body": {"text": message},
            "action": {"buttons": formatted_buttons},
        },
    }

    try:
        timeout = aiohttp.ClientTimeout(total=10)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(
                url, json=payload, headers=headers
            ) as response:
                if response.status >= 400:
                    error_text = await response.text()
                    logger.error(f"WhatsApp API error: {error_text}")
                    raise HTTPException(
                        status_code=response.status,
                        detail="Failed to send interactive WhatsApp message",
                    )
                return await response.json()

    except aiohttp.ClientError as e:
        logger.error(f"WhatsApp API error: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="Failed to send interactive WhatsApp message",
        )
