"""Enhanced WhatsApp Cloud API integration with Factiverse fact-checking."""

import logging
import os
import re  # Add regex module
import asyncio
from contextlib import suppress

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import PlainTextResponse
from typing import Set

from src.fact_checker.utils import (
    fact_check,
    clean_facts,
    detect_claims,
    generate_tailored_response,
    generate,
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
                    # Main processing logic here
                    await process_message(message_data)
                finally:
                    with suppress(KeyError):
                        processed_ids.remove(message_id)

        return {"status": "processed"}
    except Exception as e:
        raise HTTPException(500, detail="Message processing error")


async def process_message(message_data: dict):
    """Separated message processing logic."""
    try:
        # Safely access messages and contacts
        messages = message_data.get("messages", [])
        contacts = message_data.get("contacts", [])

        try:
            message = messages[0]
            contact = contacts[0]
            message_text = message.get("text", {}).get("body", "")
            phone_number = contact.get("wa_id", "")
            message_id = message.get("id", "")
        except (KeyError, IndexError) as e:
            return

        # Extract URL from message text using regex
        url_match = re.search(r"https?://\S+", message_text)
        url = url_match.group(0) if url_match else ""

        # Enhanced processing flow with retry logic
        max_retries = 3
        retry_count = 0
        success = False

        while not success and retry_count < max_retries:
            try:
                # Step 3: Detect claims with improved retry
                claims = await detect_claims(message_text)

                # If no claims found, try lower threshold once
                if not claims and retry_count == 0:
                    claims = await detect_claims(message_text, threshold=0.7)
                    retry_count += 1
                    continue

                if not claims:
                    # New improved prompt for claim suggestions
                    prompt = """🔍 **Claim Improvement Assistant** 🔍
                    The user submitted: "{user_input}"

                    Generate exactly 3 claims following this format, avoiding statistics, specific institutions, or named regions:
                        [General subject] + [Non-numerical effect/action] + [Vague timeframe/context]
                        [Alternative angle] + [Qualitative impact] + [Broad geographic scope]
                        [Distinct aspect] + [Relative comparison] + [Generalized authority]

                    Rules:
                    - Each claim must be standalone and copy-paste ready
                    - Use exact numbers and specific timeframes
                    - Maintain original intent but add concrete details
                    - Never invent information, articles or statistics
                    - 

                    Language Rules:
                        🌍 Always respond in the original language of the claim
                        💬 Maintain colloquial expressions from the user's language
                        🚫 Never mix languages in response

                    Example for "Vaccines bad":
                        Some reports suggest that certain vaccines might be associated with heart-related issues in younger individuals.
                        Certain vaccines are reported to offer strong protection against severe illness for a limited duration.
                        Booster doses for some vaccines could improve immune defenses against newer strains, per health officials.

                    Now create 3 improved claims for:
                    "{user_input}"
                    """

                    tailored_response = await generate(
                        text=message_text,
                        prompt=prompt.format(user_input=message_text),
                    )

                    # Split the response into individual claims
                    suggestions = [
                        line.strip()
                        for line in tailored_response.split("\n")
                        if line.strip().startswith(("1.", "2.", "3."))
                    ]

                    # Send initial message
                    await send_whatsapp_message(
                        phone_number,
                        "🔍 Let's clarify! Which of these specific versions matches your claim?",
                        message_id,
                    )

                    # Send each suggestion as separate message
                    for idx, suggestion in enumerate(suggestions[:3], 1):
                        # Remove numbering and extra spaces
                        clean_suggestion = re.sub(
                            r"^\d+\.\s*", "", suggestion
                        ).strip()
                        await send_whatsapp_message(
                            phone_number,
                            f"{idx}. {clean_suggestion}",
                            message_id,
                        )
                        await asyncio.sleep(1)  # Brief pause between messages

                    success = True
                    continue

                # Step 4-6: Fact check with proper URL handling
                fact_results = await fact_check(claims=claims, text="", url=url)

                relevant_results = clean_facts(fact_results)

                # Step 7: Generate tailored response
                tailored_response = await generate_tailored_response(
                    relevant_results
                )

                # Step 8: Send comprehensive response
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
                        "⚠️ We're experiencing high demand. Please try again in a minute!",
                        message_id,
                    )
                    logger.error(f"Final attempt failed: {str(e)}")
                else:
                    logger.warning(
                        f"Retry {retry_count}/{max_retries} failed: {str(e)}"
                    )
                    await asyncio.sleep(2**retry_count)  # Exponential backoff

    except Exception as e:
        raise HTTPException(500, detail="Message processing error")
