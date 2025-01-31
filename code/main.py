"""FastAPI application for WhatsApp webhook integration and fact-checking.

This module sets up a FastAPI application that handles webhook verification and
message processing for WhatsApp Cloud API integration.
"""

from fastapi import FastAPI, Request, HTTPException
import os
from dotenv import load_dotenv
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field
from random import random
import httpx


class WhatsAppWebhook(BaseModel):
    """Pydantic model for WhatsApp webhook data."""

    object: str = Field(
        ..., description="Should be 'whatsapp_business_account'"
    )
    entry: list = Field(..., description="List of webhook entries")


class FactCheckRequest(BaseModel):
    """Pydantic model for fact-check request."""

    text: str = Field(..., description="Text to fact check")


class FactCheckResponse(BaseModel):
    """Pydantic model for fact-check response."""

    text: str
    is_factual: bool
    confidence: float


class WhatsAppMessageRequest(BaseModel):
    """Pydantic model for sending WhatsApp messages."""

    messaging_product: str = "whatsapp"
    recipient_type: str = "individual"
    to: str
    type: str = "text"
    text: dict


# Load environment variables first
load_dotenv()

# Create FastAPI app
app = FastAPI()


def verify_token():
    """Get the webhook verification token from environment variables."""
    return os.getenv("WEBHOOK_VERIFY_TOKEN")


def get_whatsapp_token():
    """Get the WhatsApp API token from environment variables."""
    return os.getenv("WHATSAPP_TOKEN")


@app.get("/")
async def root():
    """Root endpoint for API health check.

    Returns:
        dict: A simple hello world message
    """
    return {"message": "Hello World"}


# Define GET and POST methods for WhatsApp API
@app.get("/whatsapp")
async def whatsapp_get(request: Request):
    """Handle WhatsApp webhook verification requests.

    This endpoint processes GET requests from WhatsApp Cloud API for webhook
    verification. When setting up a webhook, WhatsApp sends a verification
    request with a challenge token to confirm the endpoint's authenticity.

    Args:
        request (Request): FastAPI Request object containing query parameters:
            - hub.mode: Should be "subscribe"
            - hub.verify_token: Token to match against our verification token
            - hub.challenge: Challenge string to return if verification succeeds

    Returns:
        PlainTextResponse: Challenge string if verification succeeds

    Raises:
        HTTPException: 403 error if verification fails due to token mismatch
            or incorrect mode
    """
    query_params = request.query_params
    mode = query_params.get("hub.mode")
    token = query_params.get("hub.verify_token")
    challenge = query_params.get("hub.challenge")

    if mode == "subscribe" and token == verify_token():
        return PlainTextResponse(content=challenge)
    else:
        raise HTTPException(status_code=403, detail="Verification failed")


@app.post("/whatsapp")
async def whatsapp_post(webhook: WhatsAppWebhook):
    """Handle POST requests from WhatsApp webhook.

    This endpoint receives messages and events from WhatsApp Cloud API.

    Args:
        webhook (WhatsAppWebhook): Validated webhook data
    Returns:
        dict: A confirmation message
    """
    print("Received webhook with data:")
    print(f"Object: {webhook.object}")
    print(f"Entry: {webhook.entry}")

    try:
        # Extract message from the webhook data
        entry = webhook.entry[0]
        changes = entry.get("changes", [])[0]
        value = changes.get("value", {})
        messages = value.get("messages", [])[0]

        # Get the text message
        if messages and messages.get("type") == "text":
            message_text = messages["text"]["body"]

            # Get sender's phone number and phone number ID for later use
            sender_phone = messages["from"]
            phone_number_id = value["metadata"]["phone_number_id"]

            # Call the fact-check endpoint
            fact_check_request = FactCheckRequest(text=message_text)
            fact_check_result = await fact_check(fact_check_request)

            print(f"Received message: {message_text}")
            print(f"From: {sender_phone}")
            print(f"Phone ID: {phone_number_id}")

            response_message = (
                f"Fact check results for: '{message_text}'\n"
                f"Factual: {fact_check_result.is_factual}\n"
                f"Confidence: {fact_check_result.confidence:.2%}"
            )

            send_result = await send_whatsapp_message(
                phone_number_id=phone_number_id,
                to=sender_phone,
                message_text=response_message,
            )

            return {
                "message": "Webhook processed",
                "fact_check_result": fact_check_result,
                "send_result": send_result,
            }

    except Exception as e:
        print(f"Error processing webhook: {str(e)}")
        print(f"Webhook data: {webhook}")
        return {"message": f"Error processing webhook: {str(e)}"}

    return {"message": "Webhook received"}


@app.post("/fact-check", response_model=FactCheckResponse)
async def fact_check(request: FactCheckRequest):
    """Mock fact-checking endpoint randomly returns if a statement is factual.

    Args:
        request (FactCheckRequest): The text to fact check

    Returns:
        FactCheckResponse: Contains the original text, random true/false result,
            and a mock confidence score
    """
    # Generate random boolean (True/False) and confidence score
    is_factual = random() > 0.5
    confidence = random()

    return FactCheckResponse(
        text=request.text, is_factual=is_factual, confidence=confidence
    )


@app.post("/whatsapp-send")
async def send_whatsapp_message(
    phone_number_id: str, to: str, message_text: str
):
    """Send a WhatsApp message using the Cloud API.

    Args:
        phone_number_id: The ID of the phone number sending the message
        to: The recipient's phone number
        message_text: The text message to send

    Returns:
        dict: The API response
    """
    url = f"https://graph.facebook.com/v22.0/{phone_number_id}/messages"

    token = get_whatsapp_token()
    if token is None:
        print("WARNING: WhatsApp token is not set!")
        return {"error": "WhatsApp token is not configured"}

    print(f"WhatsApp token found: {'Yes' if token else 'No'}")

    headers = {
        "Authorization": f"Bearer {get_whatsapp_token()}",
        "Content-Type": "application/json",
    }

    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to,
        "type": "text",
        "text": {"body": message_text},
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(url, json=payload, headers=headers)
        return response.json()
