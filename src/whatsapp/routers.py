"""Enhanced WhatsApp Cloud API integration with Factiverse fact-checking."""

import logging
import os
import time
import unicodedata
from typing import Dict, Optional, Tuple

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from fastapi.responses import PlainTextResponse

from src.config.prompts import get_prompt
from src.db.utils import connect, insert_feedback
from src.fact_checker.utils import (
    claim_search,
    clean_claim_search_results,
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
    handle_fact_check_intent,
    handle_general_intent,
)
from src.whatsapp.utils import send_whatsapp_message

VERIFY_TOKEN = os.getenv("VERIFY_TOKEN")

router = APIRouter()

logger = logging.getLogger(__name__)

message_context: Dict[str, list[str]] = {}
message_id_to_bot_message: Dict[str, str] = {}


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

                    if phone_number not in message_context:
                        message_context[phone_number] = []

                    if message_type == "text":
                        raw_text = message.get("text", {}).get("body", "")

                        message_text = (
                            unicodedata.normalize("NFKD", raw_text)
                            .replace('"', "'")
                            .strip()
                        )

                        replacements = {
                            "\xa0": " ",  # Non-breaking space
                            "\u2018": "'",  # Left single quote
                            "\u2019": "'",  # Right single quote
                            "\u201c": '"',  # Left double quote
                            "\u201d": '"',  # Right double quote
                            "\u2013": "-",  # En dash
                            "\u2014": "--",  # Em dash
                            "\u2026": "...",  # Ellipsis
                        }

                        for char, replacement in replacements.items():
                            message_text = message_text.replace(
                                char, replacement
                            )

                        logger.info(f"User: {message_text}")
                        context_info = message.get("context", {})

                        if context_info:
                            replied_to_id = context_info.get("id")
                            if replied_to_id in message_id_to_bot_message:
                                selected_claim = message_id_to_bot_message[
                                    replied_to_id
                                ].replace('"', "'")

                                context = "\n".join(
                                    message_context[phone_number]
                                )

                                logger.info(
                                    f"User replied to: {selected_claim} "
                                    f"with {message_text}"
                                )

                                background_tasks.add_task(
                                    handle_message_reply,
                                    phone_number,
                                    message_id,
                                    message_text,
                                    context,
                                    selected_claim,
                                )
                                continue

                        message_context[phone_number].append(
                            f"User: {message_text}\n"
                        )
                        context = "\n".join(message_context[phone_number][:-1])
                        background_tasks.add_task(
                            handle_message_with_intent,
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
                            original_text = message_id_to_bot_message.get(
                                id_reacted_to, ""
                            )
                            print(f"original_text: {original_text}")
                            background_tasks.add_task(
                                handle_reaction,
                                emoji,
                                original_text,
                            )

                    elif message_type == "image":
                        image_data = message.get("image", {})
                        image_id = image_data.get("id")
                        caption = image_data.get("caption")
                        if image_id:
                            background_tasks.add_task(
                                handle_image,
                                phone_number,
                                message_id,
                                image_id,
                                caption,
                            )
                        else:
                            error_msg = "No image ID found. Please try again."
                            sent_message = await send_whatsapp_message(
                                phone_number,
                                error_msg,
                                message_id,
                            )
                            message_context[phone_number].append(
                                f"Bot: {error_msg}\n"
                            )
                            if sent_message and "messages" in sent_message:
                                bot_message_id = sent_message["messages"][0][
                                    "id"
                                ]
                                message_id_to_bot_message[bot_message_id] = (
                                    error_msg
                                )

                    else:
                        error_msg = (
                            "Sorry, I can only process text and image messages."
                        )
                        sent_message = await send_whatsapp_message(
                            phone_number,
                            error_msg,
                            message_id,
                        )
                        message_context[phone_number].append(
                            f"Bot: {error_msg}\n"
                        )
                        if sent_message and "messages" in sent_message:
                            bot_message_id = sent_message["messages"][0]["id"]
                            message_id_to_bot_message[bot_message_id] = (
                                error_msg
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
        intent_data = await detect_intent(message_text, context)
        logger.info(f"Intent data: {intent_data}")

        intent_type = intent_data.get("intent_type", "fact_check")
        short_message = intent_data.get("short_message", False)
        split_claims = intent_data.get(
            "split_claims"
        )  # New field for compound statements

        if intent_type == "fact_check" and short_message is True:
            try:
                claims = split_claims if split_claims else [message_text]
                fact_check_result: Tuple[str, str, bool] = (
                    await handle_fact_check_intent(
                        message_text, context, claims
                    )
                )
                prompt, evidence_data, has_evidence = fact_check_result

                if not has_evidence:
                    response = await handle_claim_suggestions(
                        message_id, phone_number, message_text, context
                    )
                    return
                else:
                    response = await generate(prompt, evidence_data)
            except Exception as e:
                logger.warning(f"Failed to handle fact check intent: {e}")
                response = "⚠️ Temporary service issue. Please try again!"
        elif intent_type == "fact_check" and short_message is False:
            claims = await detect_claims(message_text)
            print(f"claims: {claims}")
            if not claims:
                await handle_claim_suggestions(
                    message_id, phone_number, message_text, context
                )
                return
            else:
                try:
                    # Use a different variable name to avoid conflict
                    fact_check_result2: Tuple[str, str, bool] = (
                        await handle_fact_check_intent(
                            message_text, context, [message_text]
                        )
                    )
                    prompt, evidence_data, has_evidence = fact_check_result2
                    if not has_evidence:
                        response = await handle_claim_suggestions(
                            message_id, phone_number, message_text, context
                        )
                        return
                    else:
                        response = await generate(prompt, evidence_data)
                except Exception as e:
                    logger.warning(
                        f"Failed to handle fact check intent with claims: {e}"
                    )
                    response = "⚠️ Temporary service issue. Please try again!"
        elif intent_type == "general":
            try:
                response = await handle_general_intent(message_text, context)
            except Exception as e:
                logger.warning(f"Failed to handle general intent: {e}")
                response = "⚠️ Temporary service issue. Please try again!"
        else:
            try:
                await handle_claim_suggestions(
                    message_id, phone_number, message_text, context
                )
                return
            except Exception as e:
                logger.warning(f"Failed to handle claim suggestions: {e}")
                response = "⚠️ Temporary service issue. Please try again!"

        sent_message = await send_whatsapp_message(
            phone_number=phone_number,
            message=response,
            reply_to=message_id,
        )

        message_context[phone_number].append(f"Bot: {response}\n")

        if sent_message and "messages" in sent_message:
            bot_message_id = sent_message["messages"][0]["id"]
            message_id_to_bot_message[bot_message_id] = response

    except Exception:
        logger.error("Intent processing failed")
        error_msg = "⚠️ Temporary service issue. Please try again!"
        sent_message = await send_whatsapp_message(
            phone_number, error_msg, message_id
        )
        message_context[phone_number].append(f"Bot: {error_msg}\n")

        if sent_message and "messages" in sent_message:
            bot_message_id = sent_message["messages"][0]["id"]
            message_id_to_bot_message[bot_message_id] = error_msg


async def handle_message_reply(
    phone_number: str,
    message_id: str,
    message_text: str,
    context: str,
    claim: str,
):
    """Process messages using intent detection."""
    try:
        try:
            logger.log(logging.INFO, f"Handling message reply: {message_text}")
            fact_check_result: Tuple[str, str, bool] = (
                await handle_fact_check_intent(
                    message_text, context, [claim], is_reply=True
                )
            )
            prompt, evidence_data, has_evidence = fact_check_result

            if not has_evidence:
                response = await handle_claim_suggestions(
                    message_id, phone_number, message_text, context, claim
                )
                return
            else:
                response = await generate(prompt, evidence_data)
        except Exception as e:
            logger.warning(f"Failed to handle fact check intent: {e}")
            response = "Sorry, fact-checking failed. Please try again later."

        sent_message = await send_whatsapp_message(
            phone_number=phone_number,
            message=response,
            reply_to=message_id,
        )

        message_context[phone_number].append(f"Bot: {response}\n")

        if sent_message and "messages" in sent_message:
            bot_message_id = sent_message["messages"][0]["id"]
            message_id_to_bot_message[bot_message_id] = response

    except Exception:
        logger.error("Intent processing failed")
        error_msg = "⚠️ Temporary service issue. Please try again!"
        sent_message = await send_whatsapp_message(
            phone_number, error_msg, message_id
        )
        message_context[phone_number].append(f"Bot: {error_msg}\n")

        if sent_message and "messages" in sent_message:
            bot_message_id = sent_message["messages"][0]["id"]
            message_id_to_bot_message[bot_message_id] = error_msg


async def handle_reaction(emoji, claim_text):
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


async def handle_image(
    phone_number: str, message_id: str, image_id: str, caption: str = ""
):
    """Process image messages by extracting text using OCR and fact-checking."""
    try:
        image_url = await get_image_url(image_id)
        image_bytes = await download_image(image_url)
        full_text = "Image text:"

        full_text += extract_text_from_image(image_bytes)

        if caption:
            full_text += f"\nCaption: {caption}" if caption else ""

        if not full_text.strip():
            error_msg = """I can only understand text in images...\n
            No text was found in this one."""
            sent_message = await send_whatsapp_message(
                phone_number,
                error_msg,
                message_id,
            )

            if sent_message and "messages" in sent_message:
                bot_message_id = sent_message["messages"][0]["id"]
                message_id_to_bot_message[bot_message_id] = error_msg

            return

        message_context[phone_number].append(
            f"User uploaded an image containing this text: {full_text}\n"
        )
        context = "\n".join(message_context[phone_number][:-1])

        await handle_message_with_intent(
            phone_number,
            message_id,
            full_text,
            context,
        )

    except Exception as e:
        logger.error(f"Image processing failed: {str(e)}")
        error_msg = "Failed to process the image. Please try again."
        sent_message = await send_whatsapp_message(
            phone_number,
            error_msg,
            message_id,
        )
        message_context[phone_number].append(f"Bot: {error_msg}\n")

        if sent_message and "messages" in sent_message:
            bot_message_id = sent_message["messages"][0]["id"]
            message_id_to_bot_message[bot_message_id] = error_msg


async def handle_claim_suggestions(
    message_id: str,
    phone_number: str,
    message_text: str,
    context: str,
    claim: Optional[str] = None,
):
    """Handle claim suggestions when no direct claims are detected.

    Args:
        phone_number: The recipient's phone number
        message_id: The ID of the message being replied to
        message_text: The original message text
        context: The conversation context
        claim: The claim to suggest evidence for
    """
    claim_suggestions = await claim_search()
    cleaned_claim_suggestions = clean_claim_search_results(claim_suggestions)

    logger.info(f"I'M IN CLAIM SUGGESTIONS: {cleaned_claim_suggestions}")

    top_suggestions = []
    for result in cleaned_claim_suggestions:
        top_suggestions.append(result["claim"].replace('"', "'"))

    if claim:
        suggestion_prompt = get_prompt(
            "claim_suggestion_reply",
            message_text=message_text,
            claim=claim,
            context=context,
        )
    else:
        suggestion_prompt = get_prompt(
            "claim_suggestion",
            message_text=message_text,
            claim=claim,
            context=context,
        )

    tailored_response = await generate(suggestion_prompt)

    sent_message = await send_whatsapp_message(
        phone_number,
        tailored_response,
        message_id,
    )
    message_context[phone_number].append(f"Bot: {tailored_response}\n")

    if sent_message and "messages" in sent_message:
        bot_message_id = sent_message["messages"][0]["id"]
        message_id_to_bot_message[bot_message_id] = tailored_response

    for idx, suggestion in enumerate(top_suggestions, 1):
        number_emoji = ["1️⃣", "2️⃣", "3️⃣"][idx - 1]
        sent_message = await send_whatsapp_message(
            phone_number,
            f"{number_emoji} {suggestion}",
            message_id,
        )
        message_context[phone_number].append(
            f"Bot: {number_emoji} {suggestion}\n"
        )

        if sent_message and "messages" in sent_message:
            bot_message_id = sent_message["messages"][0]["id"]
            message_id_to_bot_message[bot_message_id] = (
                f"{number_emoji} {suggestion}"
            )
