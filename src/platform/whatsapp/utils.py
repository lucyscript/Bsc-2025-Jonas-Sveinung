"""Utility functions for WhatsApp API integration."""

import logging
import os
from typing import Dict, List, Optional

import aiohttp
from fastapi import HTTPException

from src.core.utils.utils import fetch_url

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


async def send_list_message(
    phone_number: str,
    message: str,
    title: str,
    button_text: str,
    section_title: str,
    list_items: List[Dict[str, str]],
    reply_to: str,
):
    """Send an interactive list message via WhatsApp Cloud API.

    Args:
        phone_number: The recipient's phone number
        message: The message body text
        title: The header title
        button_text: Text for the button to reveal the list
        section_title: Title for the section
        list_items: List of items with 'id', 'title', and 'description' fields
        reply_to: Optional message ID to reply to
    """
    url = f"https://graph.facebook.com/v22.0/{PHONE_NUMBER_ID}/messages"

    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json",
    }

    rows = []
    for item in list_items:
        rows.append(
            {
                "id": item["id"],
                "title": item["title"],
                "description": item.get("description", ""),
            }
        )

    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": phone_number,
        "type": "interactive",
        "context": {"message_id": reply_to},
        "interactive": {
            "type": "list",
            "header": {"type": "text", "text": title},
            "body": {"text": message},
            "action": {
                "button": button_text,
                "sections": [{"title": section_title, "rows": rows}],
            },
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
                        detail="Failed to send list message",
                    )
                return await response.json()

    except aiohttp.ClientError as e:
        logger.error(f"WhatsApp API error: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="Failed to send list message",
        )


async def send_rating_message(
    phone_number: str, message_id: str, response: str
) -> Dict:
    """Send a message with rating options from 1-6.

    Args:
        phone_number: The user's phone number
        message_id: The original message ID
        response: The response text to send
    """
    title = "Rate this response"
    button_text = "Rate"
    section_title = "Rating"

    MAX_LIST_MESSAGE_LENGTH = 1000

    if len(response) > MAX_LIST_MESSAGE_LENGTH:
        await send_whatsapp_message(phone_number, response, message_id)

        rating_prompt = "Please rate the above response 😊"

        rating_items = []
        for i in range(1, 7):
            rating_items.append(
                {
                    "id": f"rating_{i}",
                    "title": f"{i} star{'s' if i > 1 else ''}",
                    "description": [
                        "Very poor",
                        "Poor",
                        "Fair",
                        "Good",
                        "Very good",
                        "Excellent",
                    ][i - 1],
                }
            )

        try:
            return await send_list_message(
                phone_number,
                rating_prompt,
                title,
                button_text,
                section_title,
                rating_items,
                message_id,
            )
        except Exception as e:
            logger.error(f"Error sending rating message: {e}")
            raise
    else:
        rating_items = []
        for i in range(1, 7):
            rating_items.append(
                {
                    "id": f"rating_{i}",
                    "title": f"{i} star{'s' if i > 1 else ''}",
                    "description": [
                        "Very poor",
                        "Poor",
                        "Fair",
                        "Good",
                        "Very good",
                        "Excellent",
                    ][i - 1],
                }
            )

        try:
            return await send_list_message(
                phone_number,
                response,
                title,
                button_text,
                section_title,
                rating_items,
                message_id,
            )
        except Exception as e:
            logger.error(f"Error sending rating message: {e}")
            logger.info("Falling back to regular message without ratings")
            return await send_whatsapp_message(
                phone_number, response, message_id
            )


async def process_whatsapp_message(
    phone_number: str,
    message_id: str,
    response: str,
    buttons: Optional[List[Dict[str, str]]] = None,
    add_rating: bool = True,
) -> Dict:
    """Send a message and track it in the context.

    Args:
        phone_number: The user's phone number
        message_id: The original message ID
        response: The response text to send
        buttons: List of button objects if using interactive buttons
        add_rating: Whether to add rating options
    """
    try:
        if buttons:
            return await send_interactive_buttons(
                phone_number, response, buttons, message_id
            )
        elif add_rating:
            return await send_rating_message(phone_number, message_id, response)
        else:
            return await send_whatsapp_message(
                phone_number, response, message_id
            )

    except Exception as e:
        logger.error(f"Error sending message: {e}")
        raise


async def get_whatsapp_image_url(image_id: str) -> str:
    """Retrieve the image URL from WhatsApp API.

    Args:
        image_id: The ID of the image to retrieve

    Returns:
        The URL of the image
    """
    url = f"https://graph.facebook.com/v22.0/{image_id}"
    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
    }

    try:
        data = await fetch_url(url, "GET", headers)
        if "url" in data:
            return data["url"]
        else:
            logger.error(f"No URL in response: {data}")
            raise HTTPException(
                status_code=500,
                detail="Failed to get image URL: No URL in response",
            )
    except Exception as e:
        logger.error(f"Error getting WhatsApp image URL: {e}")
        raise
