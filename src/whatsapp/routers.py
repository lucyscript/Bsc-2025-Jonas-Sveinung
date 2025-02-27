"""Enhanced WhatsApp Cloud API integration with Factiverse fact-checking."""

import asyncio
import logging
import os
import re
import time
import json

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from fastapi.responses import PlainTextResponse

from src.db.utils import connect, insert_feedback
from src.fact_checker.utils import (
    clean_facts,
    generate_response,
    stance_detection,
    fact_check,
    detect_claims,
    generate,
)
from src.image.utils import (
    download_image,
    extract_text_from_image,
    get_image_url,
)
from src.intent.utils import (
    detect_intent,
    handle_greeting_intent,
    handle_help_intent,
    handle_clarification_intent,
    handle_source_intent,
    handle_feedback_intent,
    handle_off_topic_intent,
    handle_unknown_intent,
)

from src.config.prompts import get_prompt
from src.whatsapp.utils import send_whatsapp_message

VERIFY_TOKEN = os.getenv("VERIFY_TOKEN")

router = APIRouter()

logger = logging.getLogger(__name__)

message_context: dict[str, list[str]] = {}
message_id_to_claim: dict[str, str] = {}
message_id_to_original_claim: dict[str, str] = {}


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
    """Process incoming WhatsApp messages with context tracking."""
    try:
        payload = await request.json()

        if not all(key in payload for key in ["object", "entry"]):
            raise HTTPException(400, "Invalid webhook format")

        for entry in payload.get("entry", []):
            for change in entry.get("changes", []):
                message_data = change.get("value", {})
                messages = message_data.get("messages", [])
                contacts = message_data.get("contacts", [])

                if not messages or not contacts:
                    continue

                try:
                    message = messages[0]
                    contact = contacts[0]
                    message_type = message.get("type")
                    phone_number = contact.get("wa_id", "")
                    message_id = message.get("id", "")

                    if message_type == "text":
                        message_text = message.get("text", {}).get("body", "")

                        if phone_number not in message_context:
                            message_context[phone_number] = []
                        message_context[phone_number].append(
                            f"User: {message_text}\n"
                        )
                        context = "\n".join(message_context[phone_number][:-1])
                        background_tasks.add_task(
                            process_message,
                            phone_number,
                            message_id,
                            message_text,
                            context,
                        )

                    elif message_type == "reaction":
                        reaction = message.get("reaction")
                        emoji = reaction.get("emoji")
                        id_reacted_to = reaction.get("message_id")

                        message_context[phone_number].append(
                            f"User reacted with '{emoji}' "
                            f"on message '{id_reacted_to}'\n"
                        )
                        if emoji == "👍" or emoji == "👎":
                            claim_text = message_id_to_original_claim.get(
                                id_reacted_to,
                                message_id_to_claim.get(id_reacted_to, ""),
                            )
                            background_tasks.add_task(
                                process_reaction,
                                emoji,
                                claim_text,
                            )

                    elif message_type == "image":
                        image_data = message.get("image", {})
                        image_id = image_data.get("id")
                        if image_id:
                            background_tasks.add_task(
                                process_image,
                                phone_number,
                                message_id,
                                image_id,
                            )
                        else:
                            await send_whatsapp_message(
                                phone_number,
                                "No image ID found. Please try again.",
                                message_id,
                            )
                    else:
                        await send_whatsapp_message(
                            phone_number,
                            "Sorry, I can only process "
                            "text and image messages.",
                            message_id,
                        )

                except (KeyError, IndexError):
                    continue

        return {"status": "received"}
    except Exception:
        raise HTTPException(500, detail="Message processing error")


async def handle_message_with_intent(
    phone_number: str, message_id: str, message_text: str, context: str
):
    """Process messages using intent detection to determine appropriate response."""
    try:
        # Get raw response from API
        raw_response = await detect_intent(message_text, context)
        logger.info(f"RAW RESPONSE: {raw_response}")

        # Initialize clean_response with raw value
        clean_response = str(raw_response)
        intent_data = {}

        try:
            # Handle different response types
            if isinstance(raw_response, dict):
                # Already parsed correctly
                intent_data = raw_response
            else:
                # Convert string response to dict
                intent_data = json.loads(raw_response)

        except (json.JSONDecodeError, TypeError) as e:
            # Fallback parsing for malformed JSON
            logger.warning(f"Primary parsing failed, attempting cleanup: {e}")
            try:
                clean_response = (
                    str(raw_response)
                    .replace("'", '"')
                    .replace("None", "null")
                    .replace("True", "true")
                    .replace("False", "false")
                )
                intent_data = json.loads(clean_response, strict=False)
            except json.JSONDecodeError:
                logger.error(f"Final parsing failed for: {clean_response}")
                intent_data = {
                    "intent_type": "fact_check_request",
                    "confidence": 0.8,
                }

        print(f"INTENT DATA: {intent_data}")
        # Validate and use intent_data
        intent_type = intent_data.get("intent_type", "fact_check_request")
        logger.info(f"PROCESSED INTENT: {intent_type}")

        # Extract URL if present
        url_match = re.search(r"https?://\S+", message_text)
        url = url_match.group(0) if url_match else ""

        # Process based on detected intent
        if intent_type == "greeting":
            response = await handle_greeting_intent(intent_data, context)

        elif intent_type == "help_request":
            response = await handle_help_intent(intent_data, context)

        elif intent_type == "clarification_request":
            response = await handle_clarification_intent(intent_data, context)

        elif intent_type == "source_request":
            response = await handle_source_intent(intent_data, context)

        elif intent_type == "feedback":
            response = await handle_feedback_intent(intent_data, context)

        elif intent_type == "off_topic":
            response = await handle_off_topic_intent(intent_data, context)

        elif intent_type == "fact_check_request":
            # This is the default flow from your existing code
            claims = await detect_claims(message_text)

            if not claims:
                response = await generate_response([], message_text, context)

            elif url:
                fact_results = await fact_check(claims, url, message_text)
                relevant_results = clean_facts(fact_results)
                response = await generate_response(
                    relevant_results, message_text, context
                )

            else:
                suggestion_prompt = get_prompt(
                    "claims_response",
                    message_text=message_text,
                    context=context,
                )
                response = await generate(suggestion_prompt)
                await send_whatsapp_message(
                    phone_number,
                    response,
                    message_id,
                )
                message_context[phone_number].append(f"Bot: {response}\n")

        else:
            response = await handle_unknown_intent(intent_data, context)

        sent_message = await send_whatsapp_message(
            phone_number=phone_number,
            message=response,
            reply_to=message_id,
        )

        if phone_number not in message_context:
            message_context[phone_number] = []
        message_context[phone_number].append(f"Bot: {response}\n")

        if sent_message and "messages" in sent_message:
            bot_message_id = sent_message["messages"][0]["id"]
            message_id_to_original_claim[bot_message_id] = message_text

    except Exception as e:
        logger.error(f"Intent processing failed: {str(e)}")
        await send_whatsapp_message(
            phone_number,
            "⚠️ Temporary service issue. Please try again!",
            message_id,
        )


async def process_message(
    phone_number: str, message_id: str, message_text: str, context: str
):
    """Process messages with intent detection for tailored responses."""
    try:
        max_retries = 3
        retry_count = 0
        success = False

        while not success and retry_count < max_retries:
            try:
                await handle_message_with_intent(
                    phone_number, message_id, message_text, context
                )
                success = True

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
                    await asyncio.sleep(2**retry_count)

    except Exception as e:
        logger.error(f"Background task failed: {str(e)}")
        await send_whatsapp_message(
            phone_number,
            "⚠️ We're experiencing high demand. Please try again later!",
            message_id,
        )


async def process_reaction(emoji, claim_text):
    """Handles reaction processing asynchronously."""
    conn = None
    try:
        conn = connect()
        timestamp = int(time.time())
        insert_feedback(conn, emoji, claim_text, timestamp)
    except Exception as e:
        logger.error(f"Error processing reaction: {e}")
    finally:
        if conn:
            conn.close()


async def process_image(phone_number: str, message_id: str, image_id: str):
    """Process image messages by extracting text using OCR and fact-checking."""
    try:
        image_url = await get_image_url(image_id)
        image_bytes = await download_image(image_url)

        extracted_text = extract_text_from_image(image_bytes)

        if not extracted_text.strip():
            await send_whatsapp_message(
                phone_number,
                "I can only understand text in images...\n "
                "No text was found in this one.",
                message_id,
            )
            if phone_number not in message_context:
                message_context[phone_number] = []
            message_context[phone_number].append(
                "Bot: I can only understand text in images...\n "
                "No text was found in this one.\n"
            )
            return

        if phone_number not in message_context:
            message_context[phone_number] = []
        message_context[phone_number].append(
            f"User uploaded an image containing this text: {extracted_text}\n"
        )
        context = "\n".join(message_context[phone_number][:-1])

        await process_message(
            phone_number,
            message_id,
            extracted_text,
            context,
        )

    except Exception as e:
        logger.error(f"Image processing failed: {str(e)}")
        await send_whatsapp_message(
            phone_number,
            "Failed to process the image. Please try again.",
            message_id,
        )
        if phone_number not in message_context:
            message_context[phone_number] = []
        message_context[phone_number].append(
            "Bot: Failed to process the image. Please try again.\n"
        )


async def process_selected_claim(
    phone_number: str, message_id: str, claim: str, context: str
):
    """Process a single user-selected claim."""
    try:
        fact_result = await stance_detection(claim)
        relevant_results = clean_facts(fact_result)

        tailored_response = await generate_response(
            relevant_results, claim, context
        )

        await send_whatsapp_message(
            phone_number,
            tailored_response,
            message_id,
        )
        if phone_number not in message_context:
            message_context[phone_number] = []
        message_context[phone_number].append(f"Bot: {tailored_response}\n")

    except Exception as e:
        logger.error(f"Claim processing failed: {str(e)}")
        error_msg = "⚠️ Error processing selected claim. Please try again."
        await send_whatsapp_message(phone_number, error_msg, message_id)

        if phone_number in message_context:
            message_context[phone_number].append(f"Bot: {error_msg}\n")
