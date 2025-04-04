"""Utility functions for Telegram API integration."""

import logging
import os
import re
from typing import Any, Dict, List, Optional

import aiohttp
from fastapi import HTTPException

from src.core.utils.utils import fetch_url

logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_API_URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"


def convert_markdown_to_html(text: str) -> str:
    """Convert basic Markdown formatting to HTML for Telegram."""
    text = re.sub(r"(?<!\\\*)(\*)(.+?)(?<!\\\*)(\*)", r"<b>\2</b>", text)
    return text


async def send_telegram_message(
    chat_id: str, message: str, reply_to_message_id: Optional[str] = None
) -> Dict:
    """Send message via Telegram Bot API with length validation."""
    MAX_TELEGRAM_LENGTH = 4096
    if len(message) > MAX_TELEGRAM_LENGTH:
        logger.warning(
            f"Message truncated from {len(message)} to {MAX_TELEGRAM_LENGTH} "
        )
        message = message[: MAX_TELEGRAM_LENGTH - 3] + "..."

    url = f"{TELEGRAM_API_URL}/sendMessage"

    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "HTML",
    }

    if reply_to_message_id:
        payload["reply_to_message_id"] = reply_to_message_id

    try:
        timeout = aiohttp.ClientTimeout(total=30)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, json=payload) as response:
                if response.status >= 400:
                    error_text = await response.text()
                    logger.error(f"Telegram API error: {error_text}")
                    raise HTTPException(
                        status_code=response.status,
                        detail="Failed to send Telegram message",
                    )
                return await response.json()

    except aiohttp.ClientError as e:
        logger.error(f"Telegram API error: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="Failed to send Telegram message",
        )


async def send_interactive_buttons(
    chat_id: str,
    message: str,
    buttons: List[Dict[str, str]],
    reply_to_message_id: Optional[str] = None,
) -> Dict:
    """Send interactive button message via Telegram Bot API.

    Args:
        chat_id: The chat ID to send the message to
        message: The message body text
        buttons: List of button objects with 'id' and 'title' fields
        reply_to_message_id: Optional message ID to reply to
    """
    url = f"{TELEGRAM_API_URL}/sendMessage"

    keyboard = []
    row = []

    for button in buttons[:3]:
        row.append({"text": button["title"], "callback_data": button["id"]})
        if len(row) == 3:
            keyboard.append(row)
            row = []

    if row:
        keyboard.append(row)

    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "HTML",
        "reply_markup": {"inline_keyboard": keyboard},
    }

    if reply_to_message_id:
        payload["reply_to_message_id"] = reply_to_message_id

    try:
        timeout = aiohttp.ClientTimeout(total=10)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, json=payload) as response:
                if response.status >= 400:
                    error_text = await response.text()
                    logger.error(f"Telegram API error: {error_text}")
                    raise HTTPException(
                        status_code=response.status,
                        detail="Failed to send interactive Telegram message",
                    )
                return await response.json()

    except aiohttp.ClientError as e:
        logger.error(f"Telegram API error: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="Failed to send interactive Telegram message",
        )


async def send_rating_keyboard(
    chat_id: str, message: str, reply_to_message_id: Optional[str] = None
) -> Dict:
    """Send a message with a rating keyboard (1-6) via Telegram Bot API.

    Args:
        chat_id: The chat ID to send the message to
        message: The message body text
        reply_to_message_id: Optional message ID to reply to
    """
    url = f"{TELEGRAM_API_URL}/sendMessage"

    keyboard = [
        [{"text": "1️⃣ Very poor"}, {"text": "2️⃣ Poor"}, {"text": "3️⃣ Fair"}],
        [{"text": "4️⃣ Good"}, {"text": "5️⃣ Very good"}, {"text": "6️⃣ Excellent"}],
    ]

    message_with_prompt = f"📊 Please rate this response (1-6)\n\n{message}"

    payload = {
        "chat_id": chat_id,
        "text": message_with_prompt,
        "parse_mode": "HTML",
        "reply_markup": {
            "keyboard": keyboard,
            "resize_keyboard": True,
            "one_time_keyboard": True,
        },
    }

    if reply_to_message_id:
        payload["reply_to_message_id"] = reply_to_message_id

    try:
        timeout = aiohttp.ClientTimeout(total=30)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, json=payload) as response:
                if response.status >= 400:
                    error_text = await response.text()
                    logger.error(f"Telegram API error: {error_text}")
                    raise HTTPException(
                        status_code=response.status,
                        detail="Failed to send TG message with rating keyboard",
                    )
                return await response.json()

    except aiohttp.ClientError as e:
        logger.error(f"Telegram API error: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="Failed to send Telegram message with rating keyboard",
        )


async def process_telegram_message(
    chat_id: str,
    message_id: Optional[str] = None,
    response: str = "",
    buttons: Optional[List[Dict[str, str]]] = None,
    add_rating: bool = True,
) -> Dict:
    """Send a message and track it in the context.

    Args:
        chat_id: The Telegram chat ID
        message_id: The original message ID to reply to (optional)
        response: The response text to send
        buttons: List of button objects if using interactive buttons
        add_rating: Whether to add rating keyboard
    """
    try:
        response = convert_markdown_to_html(response)

        if buttons:
            return await send_interactive_buttons(
                chat_id, response, buttons, message_id
            )
        elif add_rating:
            return await send_rating_keyboard(chat_id, response, message_id)
        else:
            return await send_telegram_message(chat_id, response, message_id)

    except Exception as e:
        logger.error(f"Error sending message: {e}")
        raise


async def set_webhook(webhook_url: str) -> Dict:
    """Set the webhook URL for the Telegram bot.

    Args:
        webhook_url: The full URL to set as webhook
    """
    url = f"{TELEGRAM_API_URL}/setWebhook"

    payload = {
        "url": webhook_url,
        "allowed_updates": ["message", "callback_query"],
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload) as response:
                if response.status >= 400:
                    error_text = await response.text()
                    logger.error(f"Telegram webhook setup error: {error_text}")
                    raise HTTPException(
                        status_code=response.status,
                        detail="Failed to set Telegram webhook",
                    )
                return await response.json()
    except aiohttp.ClientError as e:
        logger.error(f"Telegram API error: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="Failed to set Telegram webhook",
        )


async def delete_webhook() -> Dict:
    """Remove the webhook for the Telegram bot."""
    url = f"{TELEGRAM_API_URL}/deleteWebhook"

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url) as response:
                if response.status >= 400:
                    error_text = await response.text()
                    logger.error(f"TG webhook deletion error: {error_text}")
                    raise HTTPException(
                        status_code=response.status,
                        detail="Failed to delete Telegram webhook",
                    )
                return await response.json()
    except aiohttp.ClientError as e:
        logger.error(f"Telegram API error: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="Failed to delete Telegram webhook",
        )


async def get_telegram_image_url(file_id: str) -> str:
    """Retrieve the image URL from Telegram API.

    Args:
        file_id: The ID of the image to retrieve

    Returns:
        The URL of the image
    """
    url = f"{TELEGRAM_API_URL}/getFile"

    payload = {"file_id": file_id}

    try:
        result = await fetch_url(url, "POST", json_data=payload)
        if result.get("ok") and "result" in result:
            file_path = result["result"]["file_path"]
            return (
                f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{file_path}"
            )
        else:
            logger.error(f"Invalid Telegram response: {result}")
            raise HTTPException(
                status_code=500, detail="Invalid response from Telegram API"
            )
    except Exception as e:
        logger.error(f"Error getting Telegram image URL: {e}")
        raise


def extract_message_data(update: Dict[str, Any]) -> Dict[str, str]:
    """Extract relevant data from a Telegram update.

    Args:
        update: The Telegram update object

    Returns:
        Dict containing extracted message data with empty strings when missing
    """
    result: Dict[str, str] = {
        "message_type": "",
        "chat_id": "",
        "message_id": "",
        "text": "",
        "callback_data": "",
        "image_id": "",
        "caption": "",
    }

    if "message" in update:
        message = update["message"]
        result["chat_id"] = str(message["chat"]["id"])
        result["message_id"] = str(message["message_id"])

        if "text" in message:
            result["message_type"] = "message"
            result["text"] = message["text"]
        elif "photo" in message:
            result["message_type"] = "image"
            if message["photo"]:
                result["image_id"] = message["photo"][-1]["file_id"]

            if "caption" in message:
                result["caption"] = message["caption"]

    elif "callback_query" in update:
        callback = update["callback_query"]
        result["message_type"] = "callback_query"
        result["chat_id"] = str(callback["message"]["chat"]["id"])
        result["message_id"] = str(callback["message"]["message_id"])
        result["callback_data"] = callback["data"]

    return result
