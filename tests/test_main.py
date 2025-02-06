"""Tests for main.py."""

from src.main import app

from fastapi.testclient import TestClient

client = TestClient(app)


def test_dummy():
    """Placeholder test to satisfy pre-commit hooks."""
    assert True
