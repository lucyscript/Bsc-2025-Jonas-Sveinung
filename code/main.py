"""FastAPI application for WhatsApp webhook integration and fact-checking.

This module sets up a FastAPI application that handles webhook verification and
message processing for WhatsApp Cloud API integration.
"""

import os

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field


class WhatsAppWebhook(BaseModel):
    """Pydantic model for WhatsApp webhook data."""

    object: str = Field(
        ..., description="Should be 'whatsapp_business_account'"
    )
    entry: list = Field(..., description="List of webhook entries")


# Load environment variables first
load_dotenv()

# Create FastAPI app
app = FastAPI()


def verify_token():
    """Get the webhook verification token from environment variables."""
    return os.getenv("WEBHOOK_VERIFY_TOKEN")


@app.get("/")
async def root():
    """Root endpoint for API health check.

    Returns:
        dict: A simple hello world message
    """
    return {"message": "Hello World"}


# Define GET and POST methods for WhatsApp API
@app.get("/webhook")
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


@app.post("/webhook")
async def whatsapp_post(webhook: WhatsAppWebhook):
    """Handle POST requests from WhatsApp webhook.

    This endpoint receives messages and events from WhatsApp Cloud API.

    Args:
        webhook (WhatsAppWebhook): Validated webhook data

    Returns:
        dict: A confirmation message
    """
    print(webhook)
    return {"message": "Webhook received"}
