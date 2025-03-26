"""Image utility for extracting image data."""

import logging
import os
from io import BytesIO

import aiohttp
import pytesseract
from PIL import Image

WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN")

logger = logging.getLogger(__name__)


async def get_image_url(image_id: str) -> str:
    """Retrieve the image URL from WhatsApp API."""
    whatsapp_api_url = f"https://graph.facebook.com/v22.0/{image_id}"
    headers = {
        "Authorization": f"Bearer {os.getenv('WHATSAPP_TOKEN')}",
    }
    async with aiohttp.ClientSession() as session:
        async with session.get(whatsapp_api_url, headers=headers) as response:
            if response.status != 200:
                error_text = await response.text()
                logger.error(f"WhatsApp API error: {error_text}")
                raise Exception(f"Failed to get image URL: {response.status}")
            data = await response.json()
            return data.get("url")


async def download_image(image_url: str) -> bytes:
    """Download the image from the provided URL."""
    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
    }
    async with aiohttp.ClientSession() as session:
        async with session.get(image_url, headers=headers) as response:
            if response.status != 200:
                error_text = await response.text()
                logger.error(f"WhatsApp API error: {error_text}")
                raise Exception(f"Failed to download image: {response.status}")
            return await response.read()


def extract_text_from_image(image_bytes: bytes) -> str:
    """Extract text from image using OCR."""
    try:
        image = Image.open(BytesIO(image_bytes))
        text = pytesseract.image_to_string(image)
        return text
    except Exception as e:
        logger.error(f"OCR failed: {str(e)}")
        return ""
