import os
import datetime
import pytest
from unittest.mock import patch, MagicMock


# ── Shared test helpers ────────────────────────────────────────────────────────

def _make_client():
    from tools import FireflyClient
    return FireflyClient(base_url="https://test.host/api", api_token="tok")


# ── FireflyClient tests ────────────────────────────────────────────────────────

def test_firefly_client_reads_env_vars():
    with patch.dict(os.environ, {
        "FIREFLY_BASE_URL": "https://firefly.example.com/api",
        "FIREFLY_API_TOKEN": "test-token-123",
    }):
        from tools import FireflyClient
        client = FireflyClient()
        assert client.base_url == "https://firefly.example.com/api"
        assert client.api_token == "test-token-123"


def test_firefly_client_accepts_explicit_args():
    from tools import FireflyClient
    client = FireflyClient(base_url="https://custom.host/api", api_token="mytoken")
    assert client.base_url == "https://custom.host/api"
    assert client.api_token == "mytoken"


def test_firefly_client_raises_without_base_url():
    env = {k: v for k, v in os.environ.items()
           if k not in ("FIREFLY_BASE_URL", "FIREFLY_API_TOKEN")}
    with patch.dict(os.environ, env, clear=True):
        from tools import FireflyClient
        with pytest.raises(ValueError, match="FIREFLY_BASE_URL"):
            FireflyClient(api_token="tok")


def test_firefly_client_raises_without_api_token():
    env = {k: v for k, v in os.environ.items()
           if k not in ("FIREFLY_BASE_URL", "FIREFLY_API_TOKEN")}
    with patch.dict(os.environ, env, clear=True):
        from tools import FireflyClient
        with pytest.raises(ValueError, match="FIREFLY_API_TOKEN"):
            FireflyClient(base_url="https://host/api")
