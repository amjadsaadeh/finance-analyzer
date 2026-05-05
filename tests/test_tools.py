import os
import datetime
import pytest
from unittest.mock import patch, MagicMock
from firefly_iii_client.exceptions import ApiException


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


# ── Transaction read helpers ───────────────────────────────────────────────────

def _mock_tx(tx_id="42", description="Groceries", amount="45.00"):
    m = MagicMock()
    m.to_dict.return_value = {
        "id": tx_id,
        "attributes": {"description": description, "amount": amount},
    }
    return m


# ── list_transactions ──────────────────────────────────────────────────────────

@patch("tools.TransactionsApi")
def test_list_transactions_returns_list(mock_api_class):
    mock_api = MagicMock()
    mock_api_class.return_value = mock_api
    mock_api.list_transaction.return_value.data = [_mock_tx()]

    from tools import dispatch
    result = dispatch(_make_client(), "list_transactions", {"limit": 10})

    assert "transactions" in result
    assert len(result["transactions"]) == 1
    assert result["transactions"][0]["id"] == "42"
    mock_api.list_transaction.assert_called_once_with(limit=10, page=1)


@patch("tools.TransactionsApi")
def test_list_transactions_uses_default_params(mock_api_class):
    mock_api = MagicMock()
    mock_api_class.return_value = mock_api
    mock_api.list_transaction.return_value.data = []

    from tools import dispatch
    dispatch(_make_client(), "list_transactions", {})

    mock_api.list_transaction.assert_called_once_with(limit=50, page=1)


@patch("tools.TransactionsApi")
def test_list_transactions_api_error_returns_error_dict(mock_api_class):
    mock_api = MagicMock()
    mock_api_class.return_value = mock_api
    mock_api.list_transaction.side_effect = ApiException(status=401, reason="Unauthorized")

    from tools import dispatch
    result = dispatch(_make_client(), "list_transactions", {})

    assert "error" in result


# ── get_transactions_by_date_range ─────────────────────────────────────────────

@patch("tools.TransactionsApi")
def test_get_transactions_by_date_range(mock_api_class):
    mock_api = MagicMock()
    mock_api_class.return_value = mock_api
    mock_api.list_transaction.return_value.data = [_mock_tx("7", "Rent", "1200.00")]

    from tools import dispatch
    result = dispatch(_make_client(), "get_transactions_by_date_range", {
        "start_date": "2024-01-01",
        "end_date": "2024-01-31",
    })

    assert "transactions" in result
    assert result["transactions"][0]["id"] == "7"
    mock_api.list_transaction.assert_called_once_with(
        start=datetime.date(2024, 1, 1),
        end=datetime.date(2024, 1, 31),
        limit=50,
        page=1,
    )


# ── search_transactions ────────────────────────────────────────────────────────

@patch("tools.SearchApi")
def test_search_transactions(mock_api_class):
    mock_api = MagicMock()
    mock_api_class.return_value = mock_api
    mock_api.search_transactions.return_value.data = [_mock_tx("3", "Netflix subscription")]

    from tools import dispatch
    result = dispatch(_make_client(), "search_transactions", {"query": "netflix"})

    assert "transactions" in result
    assert result["transactions"][0]["attributes"]["description"] == "Netflix subscription"
    mock_api.search_transactions.assert_called_once_with(query="netflix", limit=50, page=1)


@patch("tools.SearchApi")
def test_search_transactions_passes_limit_and_page(mock_api_class):
    mock_api = MagicMock()
    mock_api_class.return_value = mock_api
    mock_api.search_transactions.return_value.data = []

    from tools import dispatch
    dispatch(_make_client(), "search_transactions", {"query": "q", "limit": 5, "page": 2})

    mock_api.search_transactions.assert_called_once_with(query="q", limit=5, page=2)
