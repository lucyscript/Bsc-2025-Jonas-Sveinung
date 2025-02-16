"""Enhanced WhatsApp Cloud API integration with Factiverse fact-checking."""

import logging
import os
import re  # Add regex module

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

                # Enhanced processing flow
                try:
                    # Step 3: Detect individual claims with retry logic
                    try:
                        # First attempt with standard threshold
                        claims = await detect_claims(message_text)

                        # Second attempt with lower threshold if no claims found
                        if not claims:
                            claims = await detect_claims(
                                message_text, threshold=0.7
                            )
                            logger.info(
                                f"Low-confidence claims detected: {claims}"
                            )

                        if not claims:
                            # Generate friendly explanation
                            prompt = """📝 Hmm, I'm having trouble identifying clear claims. Could you help me by:
                                1. Being more specific about the factual statement
                                2. Providing different views and context to encourage better claims, and give examples of such claims to help the user with ideas
                                3. Breaking complex ideas into single statements

                                Example improvements:
                                "Vaccines bad" → "COVID-19 vaccines cause permanent heart damage in some of recipients"
                                "Weather changing" → "Global temperatures have increased over a few decades due to human activities"

                                You are a a helper bot for WhatsApp users that focuses on improving the quality of claims
                                Rephrase this message into claims in a friendly way:"""

                            tailored_response = await generate(
                                text=message_text, prompt=prompt
                            )

                            await send_whatsapp_message(
                                phone_number,
                                f"{tailored_response}",
                                message_id,
                            )
                            continue

                    except Exception as e:
                        logger.error(f"Claim detection failed: {str(e)}")
                        await send_whatsapp_message(
                            phone_number,
                            "⚠️ Our fact-checking engine is feeling under the weather 🌧️. Please try again!",
                            message_id,
                        )
                        continue

                    # Step 4-6: Fact check with proper URL handling
                    fact_results = await fact_check(
                        claims=claims, text="", url=url
                    )

                    relevant_results = clean_facts(fact_results)

                    print(relevant_results)

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

                except Exception as e:
                    await send_whatsapp_message(
                        phone_number=phone_number,
                        message="⚠️ Error processing your request. Please try again.",
                        reply_to=message_id,
                    )

        return {"status": "processed"}

    except Exception as e:
        raise HTTPException(500, detail="Message processing error")
