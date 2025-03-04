"""Enhanced WhatsApp Cloud API integration with Factiverse fact-checking."""

import asyncio
import json
import logging
import os
import re
import time

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from fastapi.responses import PlainTextResponse

from src.config.prompts import get_prompt
from src.db.utils import connect, insert_feedback
from src.fact_checker.utils import (
    detect_claims,
    generate,
    claim_search, 
    clean_claim_search_results,
)
from src.image.utils import (
    download_image,
    extract_text_from_image,
    get_image_url,
)
from src.intent.utils import (
    detect_intent,
    handle_bot_help_intent,
    handle_fact_check_intent,
    handle_general_intent,
)
from src.whatsapp.utils import send_whatsapp_message

VERIFY_TOKEN = os.getenv("VERIFY_TOKEN")

router = APIRouter()

logger = logging.getLogger(__name__)

message_context: dict[str, list[str]] = {}
message_to_feedback: dict[str, str] = {}


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
                        context_info = message.get("context", {})

                        if context_info:
                            replied_to_id = context_info.get("id")
                            if replied_to_id in message_to_feedback:
                                selected_claim = message_to_feedback[
                                    replied_to_id
                                ]

                                message_context[phone_number].append(
                                    f"User replied to '{selected_claim}' "
                                    f"with '{message_text}'\n"
                                )
                                context = "\n".join(
                                    message_context[phone_number]
                                )

                                background_tasks.add_task(
                                    handle_fact_check_intent,
                                    phone_number,
                                    message_id,
                                    selected_claim,
                                    context,
                                )
                                continue

                        if phone_number not in message_context:
                            message_context[phone_number] = []
                        message_context[phone_number].append(
                            f"User: {message_text}\n"
                        )
                        context = "\n".join(message_context[phone_number][:-1])
                        print(f"User: {message_text}")
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
                            original_text = message_to_feedback.get(
                                id_reacted_to, ""
                            )
                            print(f"original_text: {original_text}")
                            background_tasks.add_task(
                                process_reaction,
                                emoji,
                                original_text,
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
                            error_msg = "No image ID found. Please try again."
                            await send_whatsapp_message(
                                phone_number,
                                error_msg,
                                message_id,
                            )
                            message_context[phone_number].append(
                                f"Bot: {error_msg}\n"
                            )
                    else:
                        error_msg = (
                            "Sorry, I can only process text and image messages."
                        )
                        await send_whatsapp_message(
                            phone_number,
                            error_msg,
                            message_id,
                        )
                        message_context[phone_number].append(
                            f"Bot: {error_msg}\n"
                        )

                except (KeyError, IndexError):
                    continue

        return {"status": "received"}
    except Exception:
        raise HTTPException(500, detail="Message processing error")


async def handle_message_with_intent(
    phone_number: str, message_id: str, message_text: str, context: str
):
    """Process messages using intent detection."""
    try:
        raw_response = await detect_intent(message_text, context)
        clean_response = str(raw_response)
        intent_data = {}

        try:
            if isinstance(raw_response, dict):
                intent_data = raw_response
            else:
                intent_data = json.loads(raw_response)

        except (json.JSONDecodeError, TypeError) as e:
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
                    "intent_type": "fact_check",
                    "short_message": "true",
                }

        intent_type = intent_data.get("intent_type", "fact_check")
        short_message = intent_data.get("short_message", False)

        if intent_type == "fact_check" and short_message is True:
            response = await handle_fact_check_intent(
                message_text, context, [message_text]
            )

        if intent_type == "fact_check" and short_message is False:
            claims = await detect_claims(message_text)
            print(f"claims: {claims}")
            if not claims:
                claim_suggestions = await claim_search(message_text)
                cleaned_claim_suggestions = clean_claim_search_results(claim_suggestions)

                top_suggestions = []
                for result in cleaned_claim_suggestions[:3]:
                    if "claim" in result:
                        top_suggestions.append(result["claim"])
                
                suggestions_text = json.dumps(top_suggestions)
                suggestion_prompt = get_prompt("claim_suggestion", message_text=message_text, context=context, claim_suggestions=suggestions_text)
                tailored_response = await generate(suggestion_prompt, suggestions_text)

                sent_message = await send_whatsapp_message(
                    phone_number,
                    tailored_response,
                    message_id,
                )
                if phone_number not in message_context:
                    message_context[phone_number] = []
                message_context[phone_number].append(
                    f"Bot: {tailored_response}\n"
                )

                if sent_message and "messages" in sent_message:
                    bot_message_id = sent_message["messages"][0]["id"]
                    message_to_feedback[bot_message_id] = top_suggestions[0]

                for idx, suggestion in enumerate(top_suggestions, 1):
                    sent_message = await send_whatsapp_message(
                        phone_number,
                        f"{idx}. {suggestion}",
                        message_id,
                    )
                    if phone_number not in message_context:
                        message_context[phone_number] = []
                    message_context[phone_number].append(
                        f"Bot: {idx}. {suggestion}\n"
                    )

                    if sent_message and "messages" in sent_message:
                        bot_message_id = sent_message["messages"][0]["id"]
                        message_to_feedback[bot_message_id] = suggestion
                return
            else:
                response = await handle_fact_check_intent(
                message_text, context, claims
            )

        if intent_type == "bot_help":
            response = await handle_bot_help_intent(
                message_text, context
            )

        if intent_type == "general":
            response = await handle_general_intent(
                message_text, context
            )

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
            message_to_feedback[bot_message_id] = message_text

    except Exception as e:
        logger.error(f"Intent processing failed: {str(e)}")
        error_msg = "⚠️ Temporary service issue. Please try again!"
        sent_message = await send_whatsapp_message(
            phone_number, error_msg, message_id
        )
        message_context[phone_number].append(f"Bot: {error_msg}\n")

        if sent_message and "messages" in sent_message:
            bot_message_id = sent_message["messages"][0]["id"]
            message_to_feedback[bot_message_id] = message_text


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
                    error_msg = "⚠️ We're experiencing high demand. "
                    "Please try again in a minute!"
                    await send_whatsapp_message(
                        phone_number,
                        error_msg,
                        message_id,
                    )
                    if phone_number not in message_context:
                        message_context[phone_number] = []
                    message_context[phone_number].append(f"Bot: {error_msg}\n")
                    logger.error(f"Final attempt failed: {str(e)}")
                else:
                    logger.warning(
                        f"Retry {retry_count}/{max_retries} failed: {str(e)}"
                    )
                    await asyncio.sleep(2**retry_count)

    except Exception as e:
        error_msg = "⚠️ We're experiencing high demand. Please try again later!"
        await send_whatsapp_message(
            phone_number,
            error_msg,
            message_id,
        )
        if phone_number not in message_context:
            message_context[phone_number] = []
        message_context[phone_number].append(f"Bot: {error_msg}\n")
        logger.error(f"Background task failed: {str(e)}")


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
