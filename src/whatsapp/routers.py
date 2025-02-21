"""Enhanced WhatsApp Cloud API integration with Factiverse fact-checking."""

import asyncio
import logging
import os
import re
import time

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from fastapi.responses import PlainTextResponse

from src.db.utils import connect, insert_feedback
from src.fact_checker.utils import (
    clean_facts,
    detect_claims,
    fact_check,
    generate_response,
    stance_detection,
)
from src.image.utils import (
    download_image,
    extract_text_from_image,
    get_image_url,
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

                    # Handle different message types
                    if message_type == "text":
                        message_text = message.get("text", {}).get("body", "")
                        if phone_number not in message_context:
                            message_context[phone_number] = []
                        message_context[phone_number].append(message_text)
                        context = "\n".join(message_context[phone_number][:-1])
                        background_tasks.add_task(
                            process_message,
                            phone_number,
                            message_id,
                            message_text,
                            context,
                        )

                    elif message_type == "reaction":
                        # Handle reactions
                        reaction = message.get("reaction")
                        emoji = reaction.get("emoji")
                        id_reacted_to = reaction.get("message_id")

                        message_context[phone_number].append(
                            f"Reaction: {emoji} on message {id_reacted_to}"
                        )
                        print(
                            f"Reaction context: {message_context[phone_number]}"
                        )

                        if emoji == "👍" or emoji == "👎":
                            background_tasks.add_task(
                                process_reaction,
                                emoji,
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


async def process_message(
    phone_number: str, message_id: str, message_text: str, context: str
):
    """Updated processing with context handling."""
    try:
        # Extract URL from message text using regex
        url_match = re.search(r"https?://\S+", message_text)
        url = url_match.group(0) if url_match else ""

        # Processing flow with retry logic
        max_retries = 3
        retry_count = 0
        success = False

        while not success and retry_count < max_retries:
            try:
                # Detect claims with improved retry
                claims = await detect_claims(message_text)

                print(claims)

                if not claims:
                    tailored_response = await generate_response(
                        claims, message_text, context
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

                tailored_response = await generate_response(
                    relevant_results, message_text, context
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

    except Exception as e:
        logger.error(f"Background task failed: {str(e)}")
        await send_whatsapp_message(
            phone_number,
            "⚠️ We're experiencing high demand. Please try again later!",
            message_id,
        )


async def process_reaction(
    emoji,
):
    """Handles reaction processing asynchronously."""
    conn = None
    print(f"Received reaction: {emoji}")
    try:
        conn = connect()
        timestamp = int(time.time())
        insert_feedback(conn, emoji, timestamp)
        print(f"Received reaction: {emoji}")
    except Exception as e:
        logger.error(f"Error processing reaction: {e}")
    finally:
        if conn:
            conn.close()


async def process_image(phone_number: str, message_id: str, image_id: str):
    """Process image messages by extracting text using OCR and fact-checking."""
    try:
        # Get image URL and download it
        image_url = await get_image_url(image_id)
        image_bytes = await download_image(image_url)

        # Extract text using OCR
        extracted_text = extract_text_from_image(image_bytes)

        if not extracted_text.strip():
            await send_whatsapp_message(
                phone_number,
                "I can only understand text in images...\n "
                "No text was found in this one.",
                message_id,
            )
            return

        # Process the extracted text
        if phone_number not in message_context:
            message_context[phone_number] = []
        message_context[phone_number].append(extracted_text)
        context = "\n".join(message_context[phone_number][:-1])

        # Process the text like a normal message
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

        # Bot suggesting claims for the user:

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
