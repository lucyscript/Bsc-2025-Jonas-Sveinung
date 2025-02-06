"""FastAPI application for WhatsApp webhook integration and fact-checking.

This module sets up a FastAPI application that handles webhook verification and
message processing for WhatsApp Cloud API integration.
"""

from fastapi import FastAPI
from src.whatsapp.routers import router as whatsapp_router
from src.fact_checker.routers import router as fact_checker_router


app = FastAPI(
    title="WhatsApp Fact-Checking API",
    description="A mock implementation for WhatsApp and Factiverse integration",
    version="0.1.0",
)

# Mount the WhatsApp routes
app.include_router(whatsapp_router, prefix="/whatsapp", tags=["WhatsApp"])

# Mount the Fact-Checker routes
app.include_router(
    fact_checker_router, prefix="/fact-checker", tags=["Fact Checker"]
)


@app.get("/")
async def root():
    """Root endpoint for API health check.

    Returns:
        dict: A simple hello world message
    """
    return {"message": "Hello World"}
