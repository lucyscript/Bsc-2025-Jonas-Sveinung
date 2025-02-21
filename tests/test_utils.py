"""Test suite for utility functions and models in the fact_checker module."""

import importlib

from fastapi import FastAPI
from fastapi.testclient import TestClient

# # --- Tests for Factiverse Fact-Checking Utilities ---


# # --- Tests for WhatsApp Webhook (Basic GET verification) ---

app = FastAPI()


def include_whatsapp_router():
    """Import and include the WhatsApp router.

    We import it after setting the VERIFY_TOKEN so that the module-level
    variable gets updated.
    """
    from src.whatsapp.routers import router as whatsapp_router

    app.include_router(whatsapp_router)


def test_verify_webhook_success(monkeypatch):
    """Test GET request with correct query parameters returns the challenge.

    We override the module-level VERIFY_TOKEN after monkeypatching.
    """
    test_token = "test_verify_token"
    monkeypatch.setenv("VERIFY_TOKEN", test_token)

    # Import and reload the routes module so that VERIFY_TOKEN is read again.
    import src.whatsapp.routers as routes

    importlib.reload(routes)
    routes.VERIFY_TOKEN = test_token  
    app.router.routes = []
    app.include_router(routes.router)

    client = TestClient(app)
    params = {
        "hub.mode": "subscribe",
        "hub.verify_token": test_token,
        "hub.challenge": "challenge_test",
    }
    response = client.get("/webhook", params=params)
    assert response.status_code == 200
    assert response.text == "challenge_test"


def test_verify_webhook_failure(monkeypatch):
    """Test that a GET request with an incorrect token fails verification."""
    test_token = "test_verify_token"
    monkeypatch.setenv("VERIFY_TOKEN", test_token)

    import src.whatsapp.routers as routes

    importlib.reload(routes)
    routes.VERIFY_TOKEN = test_token

    app.router.routes = []
    app.include_router(routes.router)

    client = TestClient(app)
    params = {
        "hub.mode": "subscribe",
        "hub.verify_token": "wrong_token",
        "hub.challenge": "challenge_test",
    }
    response = client.get("/webhook", params=params)
    assert response.status_code == 403
