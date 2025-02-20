"""Enhanced WhatsApp Cloud API integration with Factiverse fact-checking."""

import asyncio
import logging
import os
import re
from contextlib import suppress
from typing import Set

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import PlainTextResponse

from src.fact_checker.utils import (
    clean_facts,
    detect_claims,
    fact_check,
    generate_response,
    stance_detection,
)
from src.whatsapp.utils import send_whatsapp_message

VERIFY_TOKEN = os.getenv("VERIFY_TOKEN")

router = APIRouter()

logger = logging.getLogger(__name__)

# Track processed message IDs (use Redis in production)
processed_ids: Set[str] = set()


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
async def receive_message(request: Request):
    """Process incoming WhatsApp messages with deduplication."""
    try:
        payload = await request.json()

        if not all(key in payload for key in ["object", "entry"]):
            raise HTTPException(400, "Invalid webhook format")

        for entry in payload.get("entry", []):
            for change in entry.get("changes", []):
                message_data = change.get("value", {})
                messages = message_data.get("messages", [])

                if not messages:
                    continue

                message = messages[0]
                message_id = message.get("id", "")

                # Deduplication check
                if message_id in processed_ids:
                    logger.info(f"Duplicate message {message_id} received")
                    return {"status": "duplicate_ignored"}

                processed_ids.add(message_id)
                try:
                    await process_message(message_data)
                finally:
                    with suppress(KeyError):
                        processed_ids.remove(message_id)

        return {"status": "processed"}
    except Exception:
        raise HTTPException(500, detail="Message processing error")


async def process_message(message_data: dict):
    """Separated message processing logic."""
    try:
        messages = message_data.get("messages", [])
        contacts = message_data.get("contacts", [])

        try:
            message = messages[0]
            contact = contacts[0]
            message_text = message.get("text", {}).get("body", "")
            phone_number = contact.get("wa_id", "")
            message_id = message.get("id", "")
        except (KeyError, IndexError):
            return

        # When context is added, run this on first contact:

        #     if user sent its first message:
        #     prompt = get_prompt(
        #         'claim_suggestion',
        #         message_text=message_text,
        #         lang=detect(message_text)
        #         )

        #     tailored_response = await generate(prompt)

        #     # Split the response into individual claims
        #     suggestions = [
        #         line.strip()
        #         for line in tailored_response.split("\n")
        #         if line.strip().startswith(("1.", "2.", "3."))
        #     ]

        #     # Send initial message
        #     await send_whatsapp_message(
        #         phone_number,
        #         '🔍 Let\'s clarify! Which of these specific versions '
        #         'matches your claim?',
        #         message_id,
        #     )

        #     # Send each suggestion as separate message
        #     for idx, suggestion in enumerate(suggestions[:3], 1):
        #         # Remove numbering and extra spaces
        #         clean_suggestion = re.sub(
        #             r"^\d+\.\s*", "", suggestion
        #         ).strip()
        #         await send_whatsapp_message(
        #             phone_number,
        #             f"{idx}. {clean_suggestion}",
        #             message_id,
        #         )
        #         await asyncio.sleep(1)  # Brief pause between messages

        #     success = True
        #     continue

        # Extract URL from message text using regex
        url_match = re.search(r"https?://\S+", message_text)
        url = url_match.group(0) if url_match else ""

        # Enhanced processing flow with retry logic
        max_retries = 3
        retry_count = 0
        success = False

        while not success and retry_count < max_retries:
            try:
                # Detect claims with improved retry
                claims = await detect_claims(message_text)

                if not claims:
                    tailored_response = await generate_response(
                        claims, message_text
                    )

                    await send_whatsapp_message(
                        phone_number=phone_number,
                        message=tailored_response,
                        reply_to=message_id,
                    )

                    success = True  # Mark success if we get through
                    continue

                # Fact check with proper URL handling
                if url:
                    fact_results = await fact_check(claims, url)
                    relevant_results = clean_facts(fact_results)
                else:
                    # For stance detection, process one claim at a time
                    relevant_results = []
                    for claim in claims:
                        fact_result = await stance_detection(claim)
                        result = clean_facts(fact_result)
                        relevant_results.extend(result)

                print(relevant_results)

                tailored_response = await generate_response(
                    relevant_results, message_text
                )

                await send_whatsapp_message(
                    phone_number=phone_number,
                    message=tailored_response,
                    reply_to=message_id,
                )

                success = True  # Mark success if we get through

            except Exception as e:
                retry_count += 1
                if retry_count == max_retries:
                    await send_whatsapp_message(
                        phone_number,
                        "⚠️ We're experiencing high demand. Please try again "
                        "in a minute!",
                        message_id,
                    )
                    logger.error(f"Final attempt failed: {str(e)}")
                else:
                    logger.warning(
                        f"Retry {retry_count}/{max_retries} failed: {str(e)}"
                    )
                    await asyncio.sleep(2**retry_count)  # Exponential backoff

    except Exception:
        raise HTTPException(500, detail="Message processing error")
