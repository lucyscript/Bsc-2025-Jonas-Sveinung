"""Enhanced WhatsApp Cloud API integration with Factiverse fact-checking."""

import logging
import os

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from fastapi.responses import PlainTextResponse

from src.fact_checker.utils import (
    fact_check,
    format_human_readable_result,
    generate,
)
from src.whatsapp.utils import send_whatsapp_message

VERIFY_TOKEN = os.getenv("VERIFY_TOKEN")

router = APIRouter()

logger = logging.getLogger(__name__)


message_context: dict[str, list[str]] = {}


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
    """Process incoming WhatsApp messages with safe list handling."""
    try:
        payload = await request.json()
        logger.debug(f"Incoming payload: {payload}")

        # Validate WhatsApp webhook structure
        if not all(key in payload for key in ["object", "entry"]):
            raise HTTPException(
                status_code=400, detail="Invalid webhook format"
            )

        # Process each entry in the webhook
        for entry in payload.get("entry", []):
            for change in entry.get("changes", []):
                message_data = change.get("value", {})

                # Safely access messages and contacts
                messages = message_data.get("messages", [])
                contacts = message_data.get("contacts", [])

                if not messages or not contacts:
                    logger.debug(
                        "Skipping entry with missing messages/contacts"
                    )
                    continue

                try:
                    message = messages[0]
                    contact = contacts[0]
                    message_text = message.get("text", {}).get("body", "")
                    phone_number = contact.get("wa_id", "")
                    message_id = message.get("id", "")

                    if phone_number not in message_context:
                        message_context[phone_number] = []
                    message_context[phone_number].append(message_text)
                    print(f"Message context: {message_context[phone_number]}")

                except (KeyError, IndexError) as e:
                    logger.warning(f"Missing message data: {str(e)}")
                    continue

                if not message_text:
                    logger.debug("Skipping non-text message")
                    continue

                background_tasks.add_task(
                    process_message, phone_number, message_text, message_id
                )

        return {"status": "received"}

    except Exception as e:
        logger.error(f"Processing failed: {str(e)}", exc_info=True)
        raise HTTPException(500, detail="Message processing error")


async def process_message(phone_number, message_text, message_id):
    """Handles fact-checking asynchronously."""
    generate_text = await generate(message_text)
    fact_response = await fact_check(message_text, generate_text)
    response_text = format_human_readable_result(fact_response)
    print(f"This is the generated text: {generate_text}")

    await send_whatsapp_message(
        phone_number=phone_number,
        message=response_text,
        reply_to=message_id,
    )
