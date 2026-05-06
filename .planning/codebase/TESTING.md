# Testing Patterns

**Analysis Date:** 2026-05-06

## Test Framework

**Runner:**
- pytest >= 8.0.0
- Config: `pyproject.toml` → `[tool.pytest.ini_options] testpaths = ["tests"]`
- No pytest plugins configured

**Assertion Library:**
- Standard `assert` statements (no `assertEqual`, etc.)
- `pytest.raises` for exception testing

**Run Commands:**
```bash
uv run pytest                    # Run all 31 tests
uv run pytest -k "test_name"    # Run single test or substring match
uv run pytest tests/test_tools.py  # Run specific file
```

No coverage, lint, typecheck, or formatting commands are configured.

## Test File Organization

**Location:**
- Co-located in `tests/` directory (separate from source)
- Single test file: `tests/test_tools.py` (568 lines)
- `tests/__init__.py` present (empty)

**Naming:**
- Test file: `test_{module_name}.py` → `test_tools.py`
- Test functions: `test_{feature}_{behavior}` → e.g., `test_list_transactions_returns_list`, `test_list_transactions_api_error_returns_error_dict`

**Structure:**
```
tests/
├── __init__.py          # Empty
└── test_tools.py        # All tests for tools.py
```

## Test Structure

**Suite Organization:**
Tests are grouped by the handler they test, separated by section comment headers:

```python
# ── list_transactions ──────────────────────────────────────────────────────────

@patch("tools.TransactionsApi")
def test_list_transactions_returns_list(mock_api_class):
    ...

# ── get_transactions_by_date_range ─────────────────────────────────────────────

@patch("tools.TransactionsApi")
def test_get_transactions_by_date_range(mock_api_class):
    ...
```

**Section headers** use `# ── {handler_name} ──` format with em-dash separators.

**Test function naming convention:**
- Happy path: `test_{handler}_{what_it_returns_or_does}`
- Error path: `test_{handler}_{error_condition}_returns_error_dict`
- Default params: `test_{handler}_uses_default_params`
- Edge case: `test_{handler}_{specific_behavior}`

**Typical test structure:**
```python
@patch("tools.TransactionsApi")           # Mock the API class
def test_handler_name(mock_api_class):    # Receives mock class
    mock_api = MagicMock()                 # Create mock instance
    mock_api_class.return_value = mock_api # Wire: class() returns mock instance
    
    # Setup: configure mock return values
    mock_api.list_transaction.return_value.data = [_mock_tx()]
    
    # Import inside test (delayed import pattern)
    from tools import dispatch
    
    # Execute
    result = dispatch(_make_client(), "handler_name", {"key": "value"})
    
    # Assert result structure
    assert "transactions" in result
    assert result["transactions"][0]["id"] == "42"
    
    # Verify API call arguments
    mock_api.list_transaction.assert_called_once_with(limit=10, page=1)
```

## Mocking

**Framework:** `unittest.mock` (stdlib) — `@patch`, `MagicMock`, `patch.dict`

**Primary Pattern — Mock at the API class level:**
```python
@patch("tools.TransactionsApi")
def test_list_transactions_returns_list(mock_api_class):
    mock_api = MagicMock()
    mock_api_class.return_value = mock_api
    # Now TransactionsApi(client.api_client) inside handler returns mock_api
```

This patches the import in `tools.py`, so the handler's `TransactionsApi(...)` call returns the mock.

**Mocking API classes used per handler:**
| Handler | Patch target |
|---------|-------------|
| list_transactions, get_transactions_by_date_range | `@patch("tools.TransactionsApi")` |
| search_transactions | `@patch("tools.SearchApi")` |
| update_transaction_tags, update_transaction_category | `@patch("tools.TransactionsApi")` |
| list_accounts | `@patch("tools.AccountsApi")` |
| get_expense_insights, get_income_insights, calculate_net, compare_periods | `@patch("tools.InsightApi")` |
| list_categories | `@patch("tools.CategoriesApi")` |
| list_tags | `@patch("tools.TagsApi")` |

**What to Mock:**
- All external API classes — never make real HTTP calls
- `ApiException` from `firefly_iii_client.exceptions` for error tests

**What NOT to Mock:**
- The `dispatch` function — always use it to test the full routing path
- The `_make_client()` helper — use real `FireflyClient` with test args
- Pure computation handlers (`sum_transactions`) — no mocking needed, pass data directly

**Environment Isolation:**
For `FireflyClient` constructor tests, use `patch.dict` to control env vars:
```python
# Remove both env vars completely
env = {k: v for k, v in os.environ.items()
       if k not in ("FIREFLY_BASE_URL", "FIREFLY_API_TOKEN")}
with patch.dict(os.environ, env, clear=True):
    ...

# Set specific env vars
with patch.dict(os.environ, {
    "FIREFLY_BASE_URL": "https://firefly.example.com/api",
    "FIREFLY_API_TOKEN": "test-token-123",
}):
    ...
```

## Fixtures and Factories

**Test Data Helpers (defined in `tests/test_tools.py`):**

```python
def _make_client():
    """Create a FireflyClient with hardcoded test credentials — avoids env var dependency."""
    from tools import FireflyClient
    return FireflyClient(base_url="https://test.host/api", api_token="tok")

def _mock_tx(tx_id="42", description="Groceries", amount="45.00"):
    """Create a MagicMock that simulates a Firefly III transaction object with .to_dict()."""
    m = MagicMock()
    m.to_dict.return_value = {
        "id": tx_id,
        "attributes": {"description": description, "amount": amount},
    }
    return m

def _mock_existing_transaction(description="Groceries", amount=45.0,
                                category_name="Food", tags=None):
    """Create a MagicMock simulating an existing transaction's splits (for write handlers)."""
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

def _make_tx_dict(tx_type: str, amount: str, description: str = "tx") -> dict:
    """Create a plain dict simulating a transaction dict (for sum_transactions)."""
    return {
        "id": "1",
        "attributes": {
            "transactions": [
                {"type": tx_type, "amount": amount, "description": description}
            ]
        },
    }

def _mock_insight_entry(name: str, difference_float: float) -> MagicMock:
    """Create a MagicMock simulating an insight category entry."""
    entry = MagicMock()
    entry.to_dict.return_value = {"name": name, "difference_float": difference_float}
    return entry
```

**Location:** All helpers are defined inline in `tests/test_tools.py` — no conftest.py or shared fixtures file.

**Naming:** Helper functions use `_` prefix (module-private convention).

## Coverage

**Requirements:** None enforced (no coverage tool configured)

**Current State:** 31 tests covering:
- `FireflyClient` constructor (2 positive, 2 negative)
- All 13 tool handlers via `dispatch`
- Error paths for arg extraction (`KeyError`, `ValueError`)
- Error paths for API failures (`ApiException`)
- Default pagination parameters
- Decimal arithmetic (net, sum, compare)
- Unknown tool dispatch

**Not covered:**
- `main.py` (trivial stub)
- Edge cases in `_build_split_update` (null `source_id`/`destination_id` paths)
- Percentage calculation when divisor is zero in `compare_periods`
- `sum_transactions` with malformed amounts

## Test Types

**Unit Tests:**
- All 31 tests are unit tests
- Every API interaction is mocked via `@patch`
- No network calls, no file I/O, no database
- Pure computation handlers (`sum_transactions`) test with plain dict data

**Integration Tests:**
- Not present — all tests mock API classes
- The `dispatch` function acts as a lightweight integration point, but handlers tested through it still use mocks

**E2E Tests:**
- Not used

## Common Patterns

**Testing Error Returns:**
```python
@patch("tools.TransactionsApi")
def test_list_transactions_api_error_returns_error_dict(mock_api_class):
    mock_api = MagicMock()
    mock_api_class.return_value = mock_api
    mock_api.list_transaction.side_effect = ApiException(status=401, reason="Unauthorized")

    from tools import dispatch
    result = dispatch(_make_client(), "list_transactions", {})

    assert "error" in result
```

**Testing Missing Required Arguments:**
```python
def test_calculate_net_missing_dates_returns_error(mock_api_class):
    from tools import dispatch
    result = dispatch(_make_client(), "calculate_net", {})
    assert "error" in result
```

**Testing Default Parameter Values:**
```python
@patch("tools.TransactionsApi")
def test_list_transactions_uses_default_params(mock_api_class):
    mock_api = MagicMock()
    mock_api_class.return_value = mock_api
    mock_api.list_transaction.return_value.data = []

    from tools import dispatch
    dispatch(_make_client(), "list_transactions", {})

    mock_api.list_transaction.assert_called_once_with(limit=50, page=1)
```

**Testing Write Handlers (GET-then-PUT pattern):**
```python
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
```

**Testing Pure Computation (No Mocking):**
```python
def test_sum_transactions_deposits_and_withdrawals():
    from tools import dispatch
    transactions = [
        _make_tx_dict("deposit", "3000.00", "Salary"),
        _make_tx_dict("withdrawal", "450.50", "Groceries"),
        _make_tx_dict("withdrawal", "100.00", "Transport"),
    ]
    result = dispatch(_make_client(), "sum_transactions", {"transactions": transactions})

    assert result["total_income"] == "3000.00"
    assert result["total_expenses"] == "550.50"
    assert result["net"] == "2449.50"
    assert result["split_count"] == 3
```

**Delayed Import Pattern:**
All tests import from `tools` inside the test function body:
```python
def test_something():
    from tools import dispatch, get_tools, FireflyClient  # import inside test
```
This ensures patches are applied before the module's top-level code runs (important for API class patching).

**Side-effect Mocking for Multiple Calls:**
For handlers that make multiple API calls (e.g., `compare_periods`), use `side_effect` lists:
```python
mock_api.insight_expense_category.side_effect = [
    [_mock_insight_entry("Food", -500.0)],   # period A expenses
    [_mock_insight_entry("Food", -600.0)],   # period B expenses
]
mock_api.insight_income_category.side_effect = [
    [_mock_insight_entry("Salary", 3000.0)],  # period A income
    [_mock_insight_entry("Salary", 3200.0)],  # period B income
]
```

---
*Testing analysis: 2026-05-06*