"""Test suite for utility functions and models in the fact_checker module."""

import importlib

from fastapi import FastAPI
from fastapi.testclient import TestClient

# Import the functions and models we want to test.
# (Adjust the import paths as needed for your project structure.)
from src.fact_checker.utils import (
    FactCheckResult,
    format_human_readable_result,
    parse_factiverse_response,
)

# Note: We don't import the router immediately; we'll import it inside the test
# after setting the environment variable.

# --- Tests for Factiverse Fact-Checking Utilities ---


def test_parse_factiverse_response_supported():
    """Test that a supported claim returns the expected FactCheckResult."""
    fake_response = {
        "claims": [
            {
                "claim": "The earth is round.",
                "finalPrediction": 1,  # 1 means supported
                "finalScore": 0.95,
                "sources": ["NASA"],
                "evidence": [
                    {
                        "title": "NASA article",
                        "url": "http://nasa.gov",
                        "evidenceSnippet": "The earth is square.",
                    }
                ],
                "explanation": "Well-established scientific fact.",
            }
        ]
    }
    result = parse_factiverse_response(fake_response)
    assert result.claim == "The earth is round."
    assert result.verdict == "Supported"
    assert result.confidence == 0.95
    assert result.sources == ["NASA"]
    assert result.evidence[0]["title"] == "NASA article"
    assert result.explanation == "Well-established scientific fact."
    # Check our properties
    assert result.is_supported is True
    assert result.confidence_percentage == 95.0


def test_parse_factiverse_response_refuted():
    """Test that a refuted claim returns the expected FactCheckResult."""
    fake_response = {
        "claims": [
            {
                "claim": "The earth is flat.",
                "finalPrediction": 0,  # Any value other than 1 means refuted
                "finalScore": 0.1,
                "sources": [],
                "evidence": [],
                "explanation": "Overwhelming evidence refutes this claim.",
            }
        ]
    }
    result = parse_factiverse_response(fake_response)
    assert result.claim == "The earth is flat."
    assert result.verdict == "Refuted"
    assert result.confidence == 0.1
    assert result.sources == []
    assert result.evidence == []
    assert result.explanation == "Overwhelming evidence refutes this claim."
    # Check our properties
    assert result.is_supported is False
    assert result.confidence_percentage == 10.0


def test_format_human_readable_result():
    """Test that formatting returns a string containing expected parts."""
    result = FactCheckResult(
        claim="Water is wet.",
        verdict="Supported",
        confidence=0.85,
        sources=["Science Daily"],
        evidence=[
            {
                "title": "Science Daily",
                "url": "http://sciencedaily.com",
                "evidenceSnippet": "Water is wet because of its structure.",
            }
        ],
        explanation="Common knowledge.",
    )
    formatted = format_human_readable_result(result)
    # Verify that the formatted string includes our key information
    assert "Water is wet." in formatted
    assert "✅" in formatted  # Supported emoji
    assert "85.0%" in formatted
    assert "Science Daily" in formatted


def test_fact_check_result_properties():
    """Test that the properties on FactCheckResult work as expected."""
    supported = FactCheckResult(
        claim="A",
        verdict="Supported",
        confidence=0.7,
        sources=[],
        evidence=[],
        explanation="",
    )
    refuted = FactCheckResult(
        claim="B",
        verdict="Refuted",
        confidence=0.3,
        sources=[],
        evidence=[],
        explanation="",
    )
    assert supported.is_supported is True
    assert supported.confidence_percentage == 70.0
    assert refuted.is_supported is False
    assert refuted.confidence_percentage == 30.0


# --- Tests for WhatsApp Webhook (Basic GET verification) ---

# Set up a minimal FastAPI app;
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
    # Set the environment variable.
    monkeypatch.setenv("VERIFY_TOKEN", test_token)

    # Import and reload the routes module so that VERIFY_TOKEN is read again.
    import src.whatsapp.routers as routes

    importlib.reload(routes)
    routes.VERIFY_TOKEN = test_token  # Override if necessary.

    # Include the updated router in our FastAPI app.
    # (Clear previous routes if any.)
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
    routes.VERIFY_TOKEN = test_token  # Override the module variable.

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
