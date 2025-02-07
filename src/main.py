"""FastAPI application for WhatsApp webhook integration and fact-checking.

This module sets up a FastAPI application that handles webhook verification and
message processing for WhatsApp Cloud API integration.
"""

from fastapi import FastAPI
import logging
import sys

from whatsapp.routers import router as whatsapp_router

app = FastAPI(
    title="WhatsApp Fact-Checking API",
    description="Implementation for WhatsApp and Factiverse integration",
    version="0.1.0",
)

# Mount the WhatsApp routes
app.include_router(whatsapp_router, tags=["WhatsApp"])

logging.basicConfig(
    level=logging.DEBUG,  # Adjust level as needed (e.g., DEBUG, INFO)
    handlers=[logging.StreamHandler(sys.stdout)],
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

logger = logging.getLogger(__name__)
logger.debug("Debug logging is now configured to stdout")


@app.get("/")
async def root():
    """Root endpoint for API health check.

    Returns:
        dict: A simple hello world message
    """
    return {"message": "Hello World"}
