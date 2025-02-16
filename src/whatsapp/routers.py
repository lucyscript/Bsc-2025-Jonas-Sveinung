"""Enhanced WhatsApp Cloud API integration with Factiverse fact-checking."""

import logging
import os
import re  # Add regex module
import asyncio
from langdetect import detect

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import PlainTextResponse

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
    """Process incoming WhatsApp messages with enhanced fact-checking flow."""

    try:
        payload = await request.json()

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

                try:
                    message = messages[0]
                    contact = contacts[0]
                    message_text = message.get("text", {}).get("body", "")
                    phone_number = contact.get("wa_id", "")
                    message_id = message.get("id", "")
                except (KeyError, IndexError) as e:
                    continue

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
                            claims = await detect_claims(
                                message_text, threshold=0.7
                            )
                            retry_count += 1
                            continue

                        if not claims:
                            lang = detect(message_text)

                            # New improved prompt for claim suggestions
                            prompt = """🔍 **Claim Improvement Assistant** 🔍
                            The user submitted: "{user_input}"

                            Your task: Generate exactly 3 specific claims following this format:
                            1. [Specific subject] + [Measurable action/effect] + [Timeframe/context]
                            2. [Alternative angle] + [Quantifiable impact] + [Geographic scope]
                            3. [Different aspect] + [Comparable metric] + [Relevant authority]

                            Rules:
                            - Each claim must be standalone and copy-paste ready
                            - Use exact numbers and specific timeframes
                            - Maintain original intent but add concrete details
                            - Never invent information, articles or statistics

                            Language Rules:
                                🌍 Always respond in the original language of the claim, which is represented by this language code: {lang}
                                💬 Maintain colloquial expressions from the user's language
                                🚫 Never mix languages in response, purely respond in the language of this language code: {lang}

                            Example for "Vaccines bad":
                            1. mRNA vaccines show 0.3% myocarditis risk in males 18-24 within 14 days
                            2. Pfizer COVID vaccine demonstrates 95% efficacy against hospitalization for 6 months
                            3. Moderna booster increases antibody levels by 4x for Omicron variants (CDC 2023)

                            Now create 3 improved claims for:
                            "{user_input}"
                            """

                            print(
                                f"Language for vague claim detected: {detect(message_text)}"
                            )

                            tailored_response = await generate(
                                text=message_text,
                                prompt=prompt.format(user_input=message_text),
                                lang=lang,
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
                            for idx, suggestion in enumerate(
                                suggestions[:3], 1
                            ):
                                # Remove numbering and extra spaces
                                clean_suggestion = re.sub(
                                    r"^\d+\.\s*", "", suggestion
                                ).strip()
                                await send_whatsapp_message(
                                    phone_number,
                                    f"{idx}. {clean_suggestion}",
                                    message_id,
                                )
                                await asyncio.sleep(
                                    1
                                )  # Brief pause between messages

                            success = True
                            continue

                        # Step 4-6: Fact check with proper URL handling
                        fact_results = await fact_check(
                            claims=claims, text="", url=url
                        )

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
                            await asyncio.sleep(
                                2**retry_count
                            )  # Exponential backoff

        return {"status": "processed"}

    except Exception as e:
        raise HTTPException(500, detail="Message processing error")
