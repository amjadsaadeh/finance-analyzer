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


# ── Transaction write helpers ──────────────────────────────────────────────────

def _mock_existing_transaction(
    description="Groceries",
    amount=45.0,
    category_name="Food",
    tags=None,
):
    split = MagicMock()
    split.description = description
    split.date = datetime.date(2024, 3, 15)
    split.amount = amount
    split.type = "withdrawal"
    split.category_name = category_name
    split.tags = tags or []
    split.source_id = 1
    split.destination_id = 2

    existing = MagicMock()
    existing.data.attributes.transactions = [split]
    return existing


# ── update_transaction_tags ────────────────────────────────────────────────────

@patch("tools.TransactionsApi")
def test_update_transaction_tags_calls_get_then_update(mock_api_class):
    mock_api = MagicMock()
    mock_api_class.return_value = mock_api
    mock_api.get_transaction.return_value = _mock_existing_transaction()
    mock_api.update_transaction.return_value.data.to_dict.return_value = {
        "id": "5", "attributes": {"tags": ["food", "weekly"]}
    }

    from tools import dispatch
    result = dispatch(_make_client(), "update_transaction_tags", {
        "transaction_id": "5",
        "tags": ["food", "weekly"],
    })

    assert "id" in result
    mock_api.get_transaction.assert_called_once_with("5")
    assert mock_api.update_transaction.called
    call_id = mock_api.update_transaction.call_args[0][0]
    assert call_id == "5"


@patch("tools.TransactionsApi")
def test_update_transaction_tags_api_error(mock_api_class):
    mock_api = MagicMock()
    mock_api_class.return_value = mock_api
    mock_api.get_transaction.side_effect = ApiException(status=404, reason="Not Found")

    from tools import dispatch
    result = dispatch(_make_client(), "update_transaction_tags", {
        "transaction_id": "99",
        "tags": ["x"],
    })

    assert "error" in result


# ── update_transaction_category ────────────────────────────────────────────────

@patch("tools.TransactionsApi")
def test_update_transaction_category(mock_api_class):
    mock_api = MagicMock()
    mock_api_class.return_value = mock_api
    mock_api.get_transaction.return_value = _mock_existing_transaction(tags=["existing-tag"])
    mock_api.update_transaction.return_value.data.to_dict.return_value = {
        "id": "8", "attributes": {"category_name": "Transport"}
    }

    from tools import dispatch
    result = dispatch(_make_client(), "update_transaction_category", {
        "transaction_id": "8",
        "category_name": "Transport",
    })

    assert "id" in result
    mock_api.get_transaction.assert_called_once_with("8")
    assert mock_api.update_transaction.called


# ── list_accounts ──────────────────────────────────────────────────────────────

@patch("tools.AccountsApi")
def test_list_accounts_returns_accounts(mock_api_class):
    mock_api = MagicMock()
    mock_api_class.return_value = mock_api
    mock_account = MagicMock()
    mock_account.to_dict.return_value = {
        "id": "1",
        "attributes": {"name": "Checking", "current_balance": "1500.00", "type": "asset"},
    }
    mock_api.list_account.return_value.data = [mock_account]

    from tools import dispatch
    result = dispatch(_make_client(), "list_accounts", {})

    assert "accounts" in result
    assert result["accounts"][0]["attributes"]["name"] == "Checking"
    mock_api.list_account.assert_called_once_with(limit=50, page=1, type=None)


@patch("tools.AccountsApi")
def test_list_accounts_with_type_filter(mock_api_class):
    mock_api = MagicMock()
    mock_api_class.return_value = mock_api
    mock_api.list_account.return_value.data = []

    from tools import dispatch
    dispatch(_make_client(), "list_accounts", {"account_type": "asset"})

    mock_api.list_account.assert_called_once_with(limit=50, page=1, type="asset")


# ── get_expense_insights ───────────────────────────────────────────────────────

@patch("tools.InsightApi")
def test_get_expense_insights(mock_api_class):
    mock_api = MagicMock()
    mock_api_class.return_value = mock_api
    mock_entry = MagicMock()
    mock_entry.to_dict.return_value = {
        "id": "3", "name": "Groceries", "difference": "-450.00", "currency_code": "EUR"
    }
    mock_api.insight_expense_category.return_value = [mock_entry]

    from tools import dispatch
    result = dispatch(_make_client(), "get_expense_insights", {
        "start_date": "2024-01-01",
        "end_date": "2024-01-31",
    })

    assert "insights" in result
    assert result["insights"][0]["name"] == "Groceries"
    mock_api.insight_expense_category.assert_called_once_with(
        start=datetime.date(2024, 1, 1),
        end=datetime.date(2024, 1, 31),
        accounts=None,
    )


@patch("tools.InsightApi")
def test_get_expense_insights_with_account_filter(mock_api_class):
    mock_api = MagicMock()
    mock_api_class.return_value = mock_api
    mock_api.insight_expense_category.return_value = []

    from tools import dispatch
    dispatch(_make_client(), "get_expense_insights", {
        "start_date": "2024-01-01",
        "end_date": "2024-01-31",
        "account_ids": [1, 2],
    })

    mock_api.insight_expense_category.assert_called_once_with(
        start=datetime.date(2024, 1, 1),
        end=datetime.date(2024, 1, 31),
        accounts=[1, 2],
    )


# ── get_income_insights ────────────────────────────────────────────────────────

@patch("tools.InsightApi")
def test_get_income_insights(mock_api_class):
    mock_api = MagicMock()
    mock_api_class.return_value = mock_api
    mock_entry = MagicMock()
    mock_entry.to_dict.return_value = {
        "id": "1", "name": "Salary", "difference": "3000.00", "currency_code": "EUR"
    }
    mock_api.insight_income_category.return_value = [mock_entry]

    from tools import dispatch
    result = dispatch(_make_client(), "get_income_insights", {
        "start_date": "2024-01-01",
        "end_date": "2024-01-31",
    })

    assert "insights" in result
    assert result["insights"][0]["name"] == "Salary"
    mock_api.insight_income_category.assert_called_once_with(
        start=datetime.date(2024, 1, 1),
        end=datetime.date(2024, 1, 31),
        accounts=None,
    )


# ── list_categories ────────────────────────────────────────────────────────────

@patch("tools.CategoriesApi")
def test_list_categories(mock_api_class):
    mock_api = MagicMock()
    mock_api_class.return_value = mock_api
    mock_cat = MagicMock()
    mock_cat.to_dict.return_value = {"id": "1", "attributes": {"name": "Groceries"}}
    mock_api.list_category.return_value.data = [mock_cat]

    from tools import dispatch
    result = dispatch(_make_client(), "list_categories", {})

    assert "categories" in result
    assert result["categories"][0]["attributes"]["name"] == "Groceries"
    mock_api.list_category.assert_called_once_with(limit=50, page=1)


# ── list_tags ──────────────────────────────────────────────────────────────────

@patch("tools.TagsApi")
def test_list_tags(mock_api_class):
    mock_api = MagicMock()
    mock_api_class.return_value = mock_api
    mock_tag = MagicMock()
    mock_tag.to_dict.return_value = {"id": "2", "attributes": {"tag": "weekly"}}
    mock_api.list_tag.return_value.data = [mock_tag]

    from tools import dispatch
    result = dispatch(_make_client(), "list_tags", {})

    assert "tags" in result
    assert result["tags"][0]["attributes"]["tag"] == "weekly"
    mock_api.list_tag.assert_called_once_with(limit=50, page=1)
