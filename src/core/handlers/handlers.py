"""Message handling functions for the chatbot."""

import asyncio
import logging
import random
import re
import string
import time
from typing import Dict, List, Optional, Tuple, Union

from src.core.client.client import (
    detect_claims,
    fact_check,
    generate,
    stance_detection,
)
from src.core.config.prompts import get_prompt
from src.core.utils.cleaner import clean_facts
from src.core.utils.image import (
    download_image,
    extract_text_from_image,
    get_image_url,
)
from src.core.utils.intent import (
    detect_intent,
)
from src.db.utils import connect, insert_feedback

logger = logging.getLogger(__name__)


async def handle_message_with_intent(
    message_text: str,
    context: str,
) -> Union[str, Tuple[List[Dict[str, str]], Dict[str, str], str], None]:
    """Process messages using intent detection.

    Args:
        message_text: The user's message text
        context: Previous conversation context

    Returns:
        str: The response message to send to the user
    """
    urls = re.findall(r"https?://\S+", message_text)
    message_length = len(message_text.split())
    response = None

    if urls:
        try:
            fact_check_result1: Tuple[str, str] = (
                await handle_fact_check_intent(message_text, context, [], urls)
            )
            prompt, evidence_data = fact_check_result1

            if evidence_data.strip() == "[]":
                suggestion_data: Tuple[
                    List[Dict[str, str]], Dict[str, str], str
                ] = await handle_claim_suggestions(message_text, context)
                return suggestion_data

            response = await generate(prompt, evidence_data)
        except Exception as e:
            logger.warning(f"Failed to handle URL fact check: {e}")
            response = "⚠️ Temporary service issue. Please try again!"

    elif message_length >= 100:
        claims = await detect_claims(message_text)
        if not claims:
            response = await handle_general_intent(message_text, context)
        else:
            try:
                fact_check_result2: Tuple[str, str] = (
                    await handle_fact_check_intent(
                        message_text, context, claims
                    )
                )
                prompt, evidence_data = fact_check_result2
                if evidence_data.strip() == "[]":
                    suggestion_data2: Tuple[
                        List[Dict[str, str]], Dict[str, str], str
                    ] = await handle_claim_suggestions(message_text, context)
                    return suggestion_data2

                response = await generate(prompt, evidence_data)
            except Exception as e:
                logger.warning(
                    f"Failed to handle fact check intent with claims: {e}"
                )
                response = "⚠️ Temporary service issue. Please try again!"

    else:
        intent_data = await detect_intent(message_text, context)
        logger.info(f"Intent data: {intent_data}")

        intent_type = intent_data.get("intent_type")
        split_claims = intent_data.get("split_claims")
        if intent_type == "fact_check":
            try:
                claims = split_claims if split_claims else [message_text]
                # relevant_claims = await asyncio.gather(
                #     *[detect_claims(claim) for claim in claims]
                # )
                # claims_list = [
                #     claim for sublist in relevant_claims
                #     for claim in sublist
                # ]
                # if not claims_list:
                #     await handle_claim_suggestions(
                #         message_text, context
                #     )
                #     return
                fact_check_result: Tuple[str, str] = (
                    await handle_fact_check_intent(
                        message_text, context, claims
                    )
                )
                prompt, evidence_data = fact_check_result

                if evidence_data.strip() == "[]":
                    suggestion_data3: Tuple[
                        List[Dict[str, str]], Dict[str, str], str
                    ] = await handle_claim_suggestions(message_text, context)
                    return suggestion_data3

                response = await generate(prompt, evidence_data)
            except Exception as e:
                logger.warning(f"Failed to handle fact check intent: {e}")
                response = "⚠️ Temporary service issue. Please try again!"
        elif intent_type == "general":
            try:
                response = await handle_general_intent(message_text, context)
            except Exception as e:
                logger.warning(f"Failed to handle general intent: {e}")
                response = "⚠️ Temporary service issue. Please try again!"
        else:
            try:
                suggestion_data4: Tuple[
                    List[Dict[str, str]], Dict[str, str], str
                ] = await handle_claim_suggestions(message_text, context)
                return suggestion_data4
            except Exception as e:
                logger.warning(f"Failed to handle claim suggestions: {e}")
                response = "⚠️ Temporary service issue. Please try again!"

    return response


async def handle_reaction(emoji: str, claim_text: str) -> bool:
    """Handles reaction processing asynchronously.

    Args:
        emoji: The emoji reaction
        claim_text: The text being reacted to
    """
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
    return True


async def handle_image(image_id: str, caption: str = "") -> Optional[str]:
    """Process image messages by extracting text using OCR.

    Args:
        image_id: The WhatsApp image ID
        caption: Optional caption text

    Returns:
        str: The extracted text from the image, or None if no text was found
    """
    try:
        image_url_task = get_image_url(image_id)
        image_url = await image_url_task

        image_bytes = await download_image(image_url)
        image_text = extract_text_from_image(image_bytes)

        full_text = ""

        if image_text:
            full_text += f"Image text: {image_text}"

        if caption:
            full_text += f"\nCaption: {caption}" if caption else ""

        return full_text
    except Exception as e:
        logger.error(f"Error processing image: {e}")
        return None


async def handle_claim_suggestions(
    message_text: str,
    context: str,
) -> Tuple[List[Dict[str, str]], Dict[str, str], str]:
    """Generate claim suggestions for the user.

    Args:
        message_text: The user's message text
        context: Previous conversation context

    Returns:
        A tuple containing (buttons, btn_id_to_claim, response)
    """
    try:
        suggestion_prompt = get_prompt(
            "claim_suggestion",
            message_text=message_text,
            context=context,
        )

        response = await generate(suggestion_prompt, message_text)

        claims = []
        for line in response.split("\n"):
            if line.startswith("Claim "):
                claim_match = re.search(r"Claim \d+: (.*)", line)
                if claim_match:
                    claims.append(claim_match.group(1).strip())

        buttons = []
        btn_id_to_claim = {}
        for idx, suggestion in enumerate(claims, 1):
            button_id = "".join(
                random.choices(string.ascii_letters + string.digits, k=5)
            )
            button_title = f"Claim {idx}"
            buttons.append({"id": button_id, "title": button_title})

            btn_id_to_claim[button_id] = suggestion

        return buttons, btn_id_to_claim, response
    except Exception as e:
        logger.error(f"Error generating claim suggestions: {e}")
        return [], {}, "⚠️ Temporary service issue. Please try again!"


async def handle_fact_check_intent(
    message_text: str, context: str, claims: list = [], urls: list = []
) -> Tuple[str, str]:
    """Generate response for fact check intent.

    Args:
        message_text: The user's message text
        context: Previous conversation context
        claims: List of claims to fact check
        urls: List of URLs to fact check

    Returns:
        A tuple containing (prompt, evidence_text)
    """
    final_evidence_text = ""

    if urls:
        for url in urls:
            fact_results = await fact_check(url)
            evidence = clean_facts(fact_results)

            final_evidence_text += f"{evidence}\n"

    if claims:
        try:
            claim_tasks = [stance_detection(claim) for claim in claims]
            logger.info(
                f"Created {len(claim_tasks)} tasks for claims processing"
            )
            fact_results_list = await asyncio.gather(
                *claim_tasks, return_exceptions=True
            )

            for i, result in enumerate(fact_results_list):
                if isinstance(result, Exception):
                    logger.error(
                        f"Error processing claim {claims[i]}: {str(result)}"
                    )
                    continue

                if not isinstance(result, BaseException):
                    evidence = clean_facts(result)
                    final_evidence_text += f"{evidence}\n"

        except Exception as e:
            logger.error(f"Error in concurrent claim processing: {str(e)}")
            raise

    fact_check_prompt = get_prompt(
        "fact_check",
        message_text=message_text,
        context=context,
    )

    return fact_check_prompt, final_evidence_text


async def handle_general_intent(message_text: str, context: str) -> str:
    """Generate response for general conversation intent."""
    general_prompt = get_prompt(
        "general",
        message_text=message_text,
        context=context,
    )
    return await generate(general_prompt, message_text)
