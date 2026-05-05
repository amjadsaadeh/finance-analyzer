# Firefly III LLM Tools Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create `tools.py` — a single module of 10 OpenAI function-calling tools wrapping the Firefly III API, with a `FireflyClient` config wrapper, JSON schemas, handlers, and a `dispatch()` router.

**Architecture:** Flat module with module-level API imports for clean mocking. `FireflyClient` holds configuration. Each `_handler_*` function instantiates the relevant API class, calls it, serializes the response via `.to_dict()`, and catches `ApiException`. `dispatch()` routes by tool name via a `_HANDLERS` dict. `TOOLS` is a plain list of OpenAI-format dicts. Tests mock at the API class level using `unittest.mock.patch`.

**Tech Stack:** Python 3.12, `firefly-iii-api-client 6.2.21`, `openai>=2.34.0`, `pytest`

---

## File Structure

| File | Status | Responsibility |
|------|--------|----------------|
| `tools.py` | Create | `FireflyClient`, `TOOLS`, all 10 `_handler_*` functions, `_HANDLERS`, `dispatch`, `get_tools` |
| `tests/__init__.py` | Create | Empty package marker |
| `tests/test_tools.py` | Create | All unit tests with mocked Firefly API clients |

---

### Task 1: Setup pytest

**Files:**
- Modify: `pyproject.toml`
- Create: `tests/__init__.py`

- [ ] **Step 1: Add pytest as a dev dependency**

Edit `pyproject.toml`:

```toml
[project]
name = "finance-analyzer"
version = "0.1.0"
description = "Add your description here"
readme = "README.md"
requires-python = ">=3.12"
dependencies = [
    "firefly-iii-api-client>=6.2.21.0",
    "openai>=2.34.0",
]

[tool.pytest.ini_options]
testpaths = ["tests"]

[dependency-groups]
dev = [
    "pytest>=8.0.0",
]
```

- [ ] **Step 2: Install dev dependencies**

```bash
uv sync --dev
```

Expected: pytest installed into `.venv`

- [ ] **Step 3: Create test package marker**

Create `tests/__init__.py` as an empty file.

- [ ] **Step 4: Verify pytest discovers tests**

```bash
uv run pytest --collect-only
```

Expected: `no tests ran` with no errors

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml uv.lock tests/__init__.py
git commit -m "chore: add pytest dev dependency"
```

---

### Task 2: FireflyClient class

**Files:**
- Create: `tools.py`
- Create: `tests/test_tools.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_tools.py`:

```python
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
```

- [ ] **Step 2: Run to verify failure**

```bash
uv run pytest tests/test_tools.py -v
```

Expected: `ImportError: No module named 'tools'`

- [ ] **Step 3: Implement FireflyClient and module skeleton**

Create `tools.py`:

```python
import os
import datetime

from firefly_iii_client import Configuration, ApiClient
from firefly_iii_client.api import (
    TransactionsApi,
    AccountsApi,
    CategoriesApi,
    TagsApi,
    SearchApi,
    InsightApi,
)
from firefly_iii_client.models import TransactionUpdate, TransactionSplitUpdate
from firefly_iii_client.exceptions import ApiException


class FireflyClient:
    def __init__(self, base_url: str = None, api_token: str = None):
        self.base_url = base_url or os.environ.get("FIREFLY_BASE_URL")
        self.api_token = api_token or os.environ.get("FIREFLY_API_TOKEN")
        if not self.base_url:
            raise ValueError("FIREFLY_BASE_URL must be set via env var or constructor argument")
        if not self.api_token:
            raise ValueError("FIREFLY_API_TOKEN must be set via env var or constructor argument")
        config = Configuration(host=self.base_url, access_token=self.api_token)
        self.api_client = ApiClient(configuration=config)


# Handlers and TOOLS defined in subsequent tasks.
_HANDLERS: dict = {}
TOOLS: list = []


def dispatch(client: FireflyClient, tool_name: str, args: dict) -> dict:
    handler = _HANDLERS.get(tool_name)
    if handler is None:
        return {"error": f"Unknown tool: {tool_name}"}
    return handler(client, args)


def get_tools() -> list:
    return TOOLS
```

- [ ] **Step 4: Run to verify pass**

```bash
uv run pytest tests/test_tools.py -v
```

Expected: 4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add tools.py tests/test_tools.py
git commit -m "feat: add FireflyClient and module skeleton"
```

---

### Task 3: list_transactions and get_transactions_by_date_range

**Files:**
- Modify: `tools.py`
- Modify: `tests/test_tools.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_tools.py`:

```python
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
```

- [ ] **Step 2: Run to verify failure**

```bash
uv run pytest tests/test_tools.py::test_list_transactions_returns_list tests/test_tools.py::test_get_transactions_by_date_range -v
```

Expected: FAIL — `dispatch` returns `{"error": "Unknown tool: list_transactions"}`

- [ ] **Step 3: Implement handlers and register them**

Add to `tools.py`, replacing the `_HANDLERS: dict = {}` line and above `TOOLS`:

```python
def _handler_list_transactions(client: FireflyClient, args: dict) -> dict:
    api = TransactionsApi(client.api_client)
    try:
        resp = api.list_transaction(
            limit=args.get("limit", 50),
            page=args.get("page", 1),
        )
        return {"transactions": [t.to_dict() for t in resp.data]}
    except ApiException as e:
        return {"error": str(e)}


def _handler_get_transactions_by_date_range(client: FireflyClient, args: dict) -> dict:
    api = TransactionsApi(client.api_client)
    try:
        start = datetime.date.fromisoformat(args["start_date"])
        end = datetime.date.fromisoformat(args["end_date"])
        resp = api.list_transaction(
            start=start,
            end=end,
            limit=args.get("limit", 50),
            page=args.get("page", 1),
        )
        return {"transactions": [t.to_dict() for t in resp.data]}
    except ApiException as e:
        return {"error": str(e)}


_HANDLERS: dict = {
    "list_transactions": _handler_list_transactions,
    "get_transactions_by_date_range": _handler_get_transactions_by_date_range,
}
```

- [ ] **Step 4: Run to verify pass**

```bash
uv run pytest tests/test_tools.py -v
```

Expected: all tests PASS

- [ ] **Step 5: Commit**

```bash
git add tools.py tests/test_tools.py
git commit -m "feat: add list_transactions and get_transactions_by_date_range tools"
```

---

### Task 4: search_transactions

**Files:**
- Modify: `tools.py`
- Modify: `tests/test_tools.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_tools.py`:

```python
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
```

- [ ] **Step 2: Run to verify failure**

```bash
uv run pytest tests/test_tools.py::test_search_transactions -v
```

Expected: FAIL — unknown tool

- [ ] **Step 3: Implement handler and register it**

Add to `tools.py` before `_HANDLERS`:

```python
def _handler_search_transactions(client: FireflyClient, args: dict) -> dict:
    api = SearchApi(client.api_client)
    try:
        resp = api.search_transactions(
            query=args["query"],
            limit=args.get("limit", 50),
            page=args.get("page", 1),
        )
        return {"transactions": [t.to_dict() for t in resp.data]}
    except ApiException as e:
        return {"error": str(e)}
```

Add to `_HANDLERS`:

```python
"search_transactions": _handler_search_transactions,
```

- [ ] **Step 4: Run to verify pass**

```bash
uv run pytest tests/test_tools.py -v
```

Expected: all tests PASS

- [ ] **Step 5: Commit**

```bash
git add tools.py tests/test_tools.py
git commit -m "feat: add search_transactions tool"
```

---

### Task 5: update_transaction_tags and update_transaction_category

**Files:**
- Modify: `tools.py`
- Modify: `tests/test_tools.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_tools.py`:

```python
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
```

- [ ] **Step 2: Run to verify failure**

```bash
uv run pytest tests/test_tools.py::test_update_transaction_tags_calls_get_then_update tests/test_tools.py::test_update_transaction_category -v
```

Expected: FAIL — unknown tools

- [ ] **Step 3: Implement handlers and register them**

Add to `tools.py` before `_HANDLERS`:

```python
def _build_split_update(split, *, tags=None, category_name=None) -> TransactionSplitUpdate:
    return TransactionSplitUpdate(
        description=split.description,
        date=split.date,
        amount=str(split.amount),
        type=split.type,
        tags=tags if tags is not None else split.tags,
        category_name=category_name if category_name is not None else split.category_name,
        source_id=str(split.source_id) if split.source_id else None,
        destination_id=str(split.destination_id) if split.destination_id else None,
    )


def _handler_update_transaction_tags(client: FireflyClient, args: dict) -> dict:
    api = TransactionsApi(client.api_client)
    tx_id = str(args["transaction_id"])
    try:
        existing = api.get_transaction(tx_id)
        splits = existing.data.attributes.transactions
        updated = [_build_split_update(s, tags=args["tags"]) for s in splits]
        result = api.update_transaction(tx_id, TransactionUpdate(transactions=updated))
        return result.data.to_dict()
    except ApiException as e:
        return {"error": str(e)}


def _handler_update_transaction_category(client: FireflyClient, args: dict) -> dict:
    api = TransactionsApi(client.api_client)
    tx_id = str(args["transaction_id"])
    try:
        existing = api.get_transaction(tx_id)
        splits = existing.data.attributes.transactions
        updated = [_build_split_update(s, category_name=args["category_name"]) for s in splits]
        result = api.update_transaction(tx_id, TransactionUpdate(transactions=updated))
        return result.data.to_dict()
    except ApiException as e:
        return {"error": str(e)}
```

Add to `_HANDLERS`:

```python
"update_transaction_tags": _handler_update_transaction_tags,
"update_transaction_category": _handler_update_transaction_category,
```

- [ ] **Step 4: Run to verify pass**

```bash
uv run pytest tests/test_tools.py -v
```

Expected: all tests PASS

- [ ] **Step 5: Commit**

```bash
git add tools.py tests/test_tools.py
git commit -m "feat: add update_transaction_tags and update_transaction_category tools"
```

---

### Task 6: list_accounts

**Files:**
- Modify: `tools.py`
- Modify: `tests/test_tools.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_tools.py`:

```python
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
```

- [ ] **Step 2: Run to verify failure**

```bash
uv run pytest tests/test_tools.py::test_list_accounts_returns_accounts -v
```

Expected: FAIL — unknown tool

- [ ] **Step 3: Implement handler and register it**

Add to `tools.py` before `_HANDLERS`:

```python
def _handler_list_accounts(client: FireflyClient, args: dict) -> dict:
    api = AccountsApi(client.api_client)
    try:
        resp = api.list_account(
            limit=args.get("limit", 50),
            page=args.get("page", 1),
            type=args.get("account_type"),
        )
        return {"accounts": [a.to_dict() for a in resp.data]}
    except ApiException as e:
        return {"error": str(e)}
```

Add to `_HANDLERS`:

```python
"list_accounts": _handler_list_accounts,
```

- [ ] **Step 4: Run to verify pass**

```bash
uv run pytest tests/test_tools.py -v
```

Expected: all tests PASS

- [ ] **Step 5: Commit**

```bash
git add tools.py tests/test_tools.py
git commit -m "feat: add list_accounts tool"
```

---

### Task 7: get_expense_insights and get_income_insights

**Files:**
- Modify: `tools.py`
- Modify: `tests/test_tools.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_tools.py`:

```python
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
```

- [ ] **Step 2: Run to verify failure**

```bash
uv run pytest tests/test_tools.py::test_get_expense_insights tests/test_tools.py::test_get_income_insights -v
```

Expected: FAIL — unknown tools

- [ ] **Step 3: Implement handlers and register them**

Add to `tools.py` before `_HANDLERS`:

```python
def _handler_get_expense_insights(client: FireflyClient, args: dict) -> dict:
    api = InsightApi(client.api_client)
    try:
        start = datetime.date.fromisoformat(args["start_date"])
        end = datetime.date.fromisoformat(args["end_date"])
        entries = api.insight_expense_category(
            start=start,
            end=end,
            accounts=args.get("account_ids"),
        )
        return {"insights": [e.to_dict() for e in entries]}
    except ApiException as e:
        return {"error": str(e)}


def _handler_get_income_insights(client: FireflyClient, args: dict) -> dict:
    api = InsightApi(client.api_client)
    try:
        start = datetime.date.fromisoformat(args["start_date"])
        end = datetime.date.fromisoformat(args["end_date"])
        entries = api.insight_income_category(
            start=start,
            end=end,
            accounts=args.get("account_ids"),
        )
        return {"insights": [e.to_dict() for e in entries]}
    except ApiException as e:
        return {"error": str(e)}
```

Add to `_HANDLERS`:

```python
"get_expense_insights": _handler_get_expense_insights,
"get_income_insights": _handler_get_income_insights,
```

- [ ] **Step 4: Run to verify pass**

```bash
uv run pytest tests/test_tools.py -v
```

Expected: all tests PASS

- [ ] **Step 5: Commit**

```bash
git add tools.py tests/test_tools.py
git commit -m "feat: add get_expense_insights and get_income_insights tools"
```

---

### Task 8: list_categories and list_tags

**Files:**
- Modify: `tools.py`
- Modify: `tests/test_tools.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_tools.py`:

```python
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
```

- [ ] **Step 2: Run to verify failure**

```bash
uv run pytest tests/test_tools.py::test_list_categories tests/test_tools.py::test_list_tags -v
```

Expected: FAIL — unknown tools

- [ ] **Step 3: Implement handlers and register them**

Add to `tools.py` before `_HANDLERS`:

```python
def _handler_list_categories(client: FireflyClient, args: dict) -> dict:
    api = CategoriesApi(client.api_client)
    try:
        resp = api.list_category(
            limit=args.get("limit", 50),
            page=args.get("page", 1),
        )
        return {"categories": [c.to_dict() for c in resp.data]}
    except ApiException as e:
        return {"error": str(e)}


def _handler_list_tags(client: FireflyClient, args: dict) -> dict:
    api = TagsApi(client.api_client)
    try:
        resp = api.list_tag(
            limit=args.get("limit", 50),
            page=args.get("page", 1),
        )
        return {"tags": [t.to_dict() for t in resp.data]}
    except ApiException as e:
        return {"error": str(e)}
```

Add to `_HANDLERS`:

```python
"list_categories": _handler_list_categories,
"list_tags": _handler_list_tags,
```

- [ ] **Step 4: Run to verify pass**

```bash
uv run pytest tests/test_tools.py -v
```

Expected: all tests PASS

- [ ] **Step 5: Commit**

```bash
git add tools.py tests/test_tools.py
git commit -m "feat: add list_categories and list_tags tools"
```

---

### Task 9: TOOLS schemas, dispatch completeness, get_tools

**Files:**
- Modify: `tools.py`
- Modify: `tests/test_tools.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_tools.py`:

```python
# ── TOOLS / dispatch / get_tools ───────────────────────────────────────────────

def test_get_tools_returns_10_tools():
    from tools import get_tools
    assert len(get_tools()) == 10


def test_get_tools_names_match_handlers():
    from tools import get_tools
    names = {t["function"]["name"] for t in get_tools()}
    assert names == {
        "list_transactions",
        "get_transactions_by_date_range",
        "search_transactions",
        "update_transaction_tags",
        "update_transaction_category",
        "list_accounts",
        "get_expense_insights",
        "get_income_insights",
        "list_categories",
        "list_tags",
    }


def test_get_tools_each_has_valid_openai_schema():
    from tools import get_tools
    for tool in get_tools():
        assert tool["type"] == "function"
        fn = tool["function"]
        assert "name" in fn
        assert "description" in fn
        params = fn["parameters"]
        assert params["type"] == "object"
        assert "properties" in params
        assert "required" in params


def test_dispatch_unknown_tool():
    from tools import dispatch
    result = dispatch(_make_client(), "no_such_tool", {})
    assert result == {"error": "Unknown tool: no_such_tool"}
```

- [ ] **Step 2: Run to verify failure**

```bash
uv run pytest tests/test_tools.py::test_get_tools_returns_10_tools tests/test_tools.py::test_get_tools_names_match_handlers -v
```

Expected: FAIL — `TOOLS` is empty

- [ ] **Step 3: Replace TOOLS placeholder with full schemas**

Replace `TOOLS: list = []` in `tools.py` with:

```python
TOOLS: list = [
    {
        "type": "function",
        "function": {
            "name": "list_transactions",
            "description": "List transactions from Firefly III with optional filters.",
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "description": "Max results per page (default 50)"},
                    "page": {"type": "integer", "description": "Page number (default 1)"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_transactions_by_date_range",
            "description": "List transactions between start_date and end_date (YYYY-MM-DD format).",
            "parameters": {
                "type": "object",
                "properties": {
                    "start_date": {"type": "string", "description": "Start date in YYYY-MM-DD format"},
                    "end_date": {"type": "string", "description": "End date in YYYY-MM-DD format"},
                    "limit": {"type": "integer", "description": "Max results per page (default 50)"},
                    "page": {"type": "integer", "description": "Page number (default 1)"},
                },
                "required": ["start_date", "end_date"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_transactions",
            "description": "Full-text search across transaction descriptions.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query string"},
                    "limit": {"type": "integer", "description": "Max results per page (default 50)"},
                    "page": {"type": "integer", "description": "Page number (default 1)"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_transaction_tags",
            "description": "Replace all tags on a transaction with a new list of tags.",
            "parameters": {
                "type": "object",
                "properties": {
                    "transaction_id": {"type": "string", "description": "ID of the transaction"},
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "New list of tags (replaces existing tags)",
                    },
                },
                "required": ["transaction_id", "tags"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_transaction_category",
            "description": "Set the category on a transaction.",
            "parameters": {
                "type": "object",
                "properties": {
                    "transaction_id": {"type": "string", "description": "ID of the transaction"},
                    "category_name": {"type": "string", "description": "Category name to assign"},
                },
                "required": ["transaction_id", "category_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_accounts",
            "description": "List all accounts with their current balances.",
            "parameters": {
                "type": "object",
                "properties": {
                    "account_type": {
                        "type": "string",
                        "description": "Filter by type: asset, expense, revenue, liability (optional)",
                    },
                    "limit": {"type": "integer", "description": "Max results per page (default 50)"},
                    "page": {"type": "integer", "description": "Page number (default 1)"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_expense_insights",
            "description": "Get expense totals grouped by category for a date range.",
            "parameters": {
                "type": "object",
                "properties": {
                    "start_date": {"type": "string", "description": "Start date in YYYY-MM-DD format"},
                    "end_date": {"type": "string", "description": "End date in YYYY-MM-DD format"},
                    "account_ids": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "Filter by account IDs (optional)",
                    },
                },
                "required": ["start_date", "end_date"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_income_insights",
            "description": "Get income totals grouped by category for a date range.",
            "parameters": {
                "type": "object",
                "properties": {
                    "start_date": {"type": "string", "description": "Start date in YYYY-MM-DD format"},
                    "end_date": {"type": "string", "description": "End date in YYYY-MM-DD format"},
                    "account_ids": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "Filter by account IDs (optional)",
                    },
                },
                "required": ["start_date", "end_date"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_categories",
            "description": "List all transaction categories.",
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "description": "Max results per page (default 50)"},
                    "page": {"type": "integer", "description": "Page number (default 1)"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_tags",
            "description": "List all transaction tags.",
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "description": "Max results per page (default 50)"},
                    "page": {"type": "integer", "description": "Page number (default 1)"},
                },
                "required": [],
            },
        },
    },
]
```

- [ ] **Step 4: Run full test suite**

```bash
uv run pytest tests/test_tools.py -v
```

Expected: all tests PASS

- [ ] **Step 5: Commit**

```bash
git add tools.py tests/test_tools.py
git commit -m "feat: add TOOLS schemas and complete Firefly III LLM tools module"
```

---

## Self-Review

**Spec coverage:**
- ✓ `FireflyClient` with env var + explicit constructor config
- ✓ All 10 tools implemented with handlers
- ✓ `TOOLS` list with valid OpenAI function-calling schemas
- ✓ `dispatch(client, tool_name, args)` router
- ✓ `get_tools()` helper
- ✓ `ApiException` caught in every handler → `{"error": ...}` returned
- ✓ `get_transactions_by_date_range` as dedicated date-range tool (user request)
- ✓ Tests for every tool including error cases

**Placeholder scan:** No TBD, TODO, vague steps, or missing code blocks found.

**Type consistency:**
- All handlers take `(client: FireflyClient, args: dict) -> dict` — consistent across all 9 tasks
- `_HANDLERS` keys match `TOOLS[*]["function"]["name"]` values exactly
- `_build_split_update` defined in Task 5, only used in Task 5 handlers — no cross-task drift
- `dispatch(client, tool_name, args)` signature unchanged from Task 2 skeleton through Task 9
