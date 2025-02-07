"""Enhanced WhatsApp Cloud API integration with Factiverse fact-checking."""

import logging
import os
from enum import Enum
from pydantic import HttpUrl
from typing import Optional
import json

import httpx
from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field

WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN")
PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID")
FACTIVERSE_API_TOKEN = os.getenv("FACTIVERSE_API_TOKEN")
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN")

router = APIRouter()

logger = logging.getLogger(__name__)


class WhatsAppMessage(BaseModel):
    messaging_product: str
    contacts: list[dict]
    messages: list[dict]


class LanguageCode(str, Enum):
    """Supported ISO-639-1 language codes for fact-checking."""

    EN = "en"


class SearchDomain(str, Enum):
    NEWS = "news"
    ENCYCLOPEDIA = "encyclopedia"
    RESEARCH = "research"
    SOCIAL_MEDIA = "social_media"


class FactCheckRequest(BaseModel):
    text: str
    lang: LanguageCode = Field(
        default=LanguageCode.EN,
        description="ISO-639-1 language code for fact-checking",
    )
    collection: str = Field(
        "test", description="Name of the collection to use for fact-checking"
    )
    domainsToSearch: list[SearchDomain] = Field(
        default=[
            SearchDomain.NEWS,
            SearchDomain.ENCYCLOPEDIA,
            SearchDomain.RESEARCH,
            SearchDomain.SOCIAL_MEDIA,
        ],
        min_length=1,
        alias="domainsToSearch",
    )
    logging: bool = Field(False, description="Enable/disable result logging")
    url: Optional[HttpUrl] = Field(
        None, description="URL of content to fact-check"
    )


class FactCheckResult(BaseModel):
    claims: list[dict]
    claim: str
    rating: str
    confidence: float
    sources: list[str]
    evidence: list[dict]
    explanation: str


@router.get("/webhook")
async def verify_webhook(
    hub_mode: str, hub_verify_token: str, hub_challenge: str
):
    """Webhook verification as per WhatsApp Cloud API requirements."""
    if hub_verify_token != VERIFY_TOKEN:
        logger.error("Verification token mismatch")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Verification token mismatch",
        )
    logger.info("Webhook verified successfully")
    return int(hub_challenge)


@router.post("/webhook")
async def receive_message(request: Request):
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
                except (KeyError, IndexError) as e:
                    logger.warning(f"Missing message data: {str(e)}")
                    continue

                if not message_text:
                    logger.debug("Skipping non-text message")
                    continue

                # Fact-check and respond
                fact_response = await fact_check_message(message_text)
                response_text = format_factcheck_response(fact_response)

                await send_whatsapp_message(
                    phone_number=phone_number,
                    message=response_text,
                    reply_to=message_id,
                )

        return {"status": "processed"}

    except Exception as e:
        logger.error(f"Processing failed: {str(e)}", exc_info=True)
        raise HTTPException(500, detail="Message processing error")


async def fact_check_message(text: str) -> FactCheckResult:
    """Call Factiverse API for fact-checking."""
    logger.debug(f"Fact-checking text: {text}")

    fact_payload = FactCheckRequest(
        text=text,
        lang=LanguageCode.EN,
        collection="test",
        domainsToSearch=[
            SearchDomain.NEWS,
            SearchDomain.ENCYCLOPEDIA,
            SearchDomain.RESEARCH,
            SearchDomain.SOCIAL_MEDIA,
        ],
        logging=False,
    )

    json_data = {
        "logging": fact_payload.logging,
        "lang": fact_payload.lang,
        "collection": fact_payload.collection,
        "text": fact_payload.text,
        "claims": [fact_payload.text],
        "url": fact_payload.url.unicode_string() if fact_payload.url else "",
        "domainsToSearch": [
            domain.value for domain in fact_payload.domainsToSearch
        ],
    }

    logger.debug(f"Sending payload to Factiverse: {json_data}")

    headers = {
        "Authorization": f"Bearer {FACTIVERSE_API_TOKEN}",
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://dev.factiverse.ai/v1/fact_check",
                content=json.dumps(json_data),
                headers=headers,
                timeout=10,
            )
            response.raise_for_status()

            raw_response = response.json()
            logger.debug(f"Raw Factiverse response: {raw_response}")

            return parse_factiverse_response(raw_response)

    except httpx.HTTPStatusError as e:
        logger.error(f"Factiverse API error: {e.response.text}")
        raise HTTPException(
            status_code=e.response.status_code,
            detail="Fact check service unavailable",
        )


def parse_factiverse_response(response: dict) -> FactCheckResult:
    """Parse Factiverse API response into structured format."""
    # Safely extract first claim with nested fallbacks
    first_claim = response.get("claims", [{}])[0]

    return FactCheckResult(
        claims=response.get("claims", []),
        claim=first_claim.get("claim", "No claim text available"),
        rating=(first_claim.get("verdict", {}).get("rating", "unverified")),
        confidence=(first_claim.get("verdict", {}).get("confidence", 0.0)),
        sources=first_claim.get("sources", []),
        evidence=first_claim.get("evidence", []),
        explanation=(
            first_claim.get("verdict", {}).get(
                "explanation", "No explanation available"
            )
        ),
    )


async def send_whatsapp_message(phone_number: str, message: str, reply_to: str):
    """Send message via WhatsApp Cloud API with length validation."""
    MAX_WHATSAPP_LENGTH = 4096
    if len(message) > MAX_WHATSAPP_LENGTH:
        logger.warning(
            f"Message truncated from {len(message)} to {MAX_WHATSAPP_LENGTH} characters"
        )
        message = message[: MAX_WHATSAPP_LENGTH - 4] + "..."

    url = f"https://graph.facebook.com/v18.0/{PHONE_NUMBER_ID}/messages"

    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json",
    }

    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": phone_number,
        "context": {"message_id": reply_to},
        "text": {"body": message},
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                url, json=payload, headers=headers, timeout=10
            )
            response.raise_for_status()
            return response.json()

    except httpx.HTTPStatusError as e:
        logger.error(f"WhatsApp API error: {e.response.text}")
        raise HTTPException(
            status_code=e.response.status_code,
            detail="Failed to send WhatsApp message",
        )


async def handle_whatsapp_message(
    phone_number: str, message: str, reply_to: str
):
    """End-to-end message handling with improved error handling."""
    try:
        # Get fact check results
        fact_response = await get_fact_check(message)

        # Format response with proper null checks
        response_text = format_factcheck_response(fact_response)

        # Send response back via WhatsApp
        return await send_whatsapp_message(
            phone_number, response_text, reply_to
        )

    except Exception as e:
        logger.error(f"Message handling failed: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Message processing error")


def format_factcheck_response(result: FactCheckResult) -> str:
    """Robust response formatting with API structure fixes."""
    try:
        # Access first claim directly from result
        main_claim = result.claims[0] if result.claims else {}

        verdict = (
            "✅ Supported"
            if main_claim.get("finalPrediction") == 1
            else "❌ Refuted"
        )
        response = (
            f"🔍 *Fact Check Results:*\n\n"
            f"*Claim:* {main_claim.get('claim', 'Unknown claim')}\n"
            f"*Verdict:* {verdict}\n"
            f"*Confidence:* {main_claim.get('finalScore', 0)*100:.1f}%\n\n"
        )

        # Handle evidence from first claim
        if main_claim.get("evidence"):
            response += "*Top Evidence:*\n"
            for idx, evidence in enumerate(main_claim["evidence"][:2], 1):
                source = (
                    evidence.get("title")
                    or evidence.get("domainName")
                    or "Unknown source"
                )
                url = evidence.get("url", "#")
                snippet = (
                    (evidence.get("evidenceSnippet", "")[:200] + "...")
                    if evidence.get("evidenceSnippet")
                    else ""
                )

                response += f"{idx}. [{source}]({url})\n{snippet}\n\n"

        return response

    except Exception as e:
        logger.error(f"Formatting failed: {str(e)}", exc_info=True)
        return "⚠️ Error formatting results - please check claim validity"


async def get_fact_check(text: str) -> FactCheckResult:
    """Get fact check results from Factiverse API."""
    # Implementation from your previous working version
    fact_payload = FactCheckRequest(text=text)  # Your existing payload setup
    return await fact_check_message(
        fact_payload.text
    )  # Your existing API call logic
