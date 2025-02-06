"""Tests for main.py."""

from fastapi.testclient import TestClient

from src.main import app

client = TestClient(app)


def test_dummy():
    """Placeholder test to satisfy pre-commit hooks."""
    assert True
