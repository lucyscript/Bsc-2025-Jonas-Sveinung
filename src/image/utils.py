"""Image utility for extracting image data."""

import logging
import os
from io import BytesIO

import httpx
import pytesseract
from PIL import Image

logger = logging.getLogger(__name__)


async def get_image_url(image_id: str) -> str:
    """Retrieve the image URL from WhatsApp API."""
    whatsapp_api_url = f"https://graph.facebook.com/v22.0/{image_id}"
    headers = {
        "Authorization": f"Bearer {os.getenv('WHATSAPP_TOKEN')}",
    }
    async with httpx.AsyncClient() as client:
        response = await client.get(whatsapp_api_url, headers=headers)
        response.raise_for_status()
        return response.json().get("url")


async def download_image(image_url: str) -> bytes:
    """Download the image from the provided URL."""
    headers = {
        "Authorization": f"Bearer {os.getenv('WHATSAPP_TOKEN')}",
    }
    async with httpx.AsyncClient() as client:
        response = await client.get(image_url, headers=headers)
        response.raise_for_status()
        return response.content


def extract_text_from_image(image_bytes: bytes) -> str:
    """Extract text from image using OCR."""
    try:
        image = Image.open(BytesIO(image_bytes))
        text = pytesseract.image_to_string(image)
        return text
    except Exception as e:
        logger.error(f"OCR failed: {str(e)}")
        return ""
