"""Utility functions for WhatsApp API integration."""

import logging
import os

import httpx
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
        async with httpx.AsyncClient() as client:
            response = await client.post(
                url, json=payload, headers=headers, timeout=10
            )
            response.raise_for_status()
            return response.json()

    except httpx.HTTPStatusError as e:
        logger.error(f"WhatsApp API error: {e.response.text}")
        raise HTTPException(
            status_code=e.response.status_code,
            detail="Failed to send WhatsApp message",
        )
