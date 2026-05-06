# finance-analyzer

Personal finance analyzer that queries Firefly III, tags/categorizes transactions, and answers questions about spending and income.

## Project layout

```
tools.py          — all Firefly III tools (see below)
main.py           — entry point (stub)
tests/            — pytest unit tests (mock all API calls)
docs/plans/       — design docs
```

## Development

```bash
uv sync --dev     # install deps including pytest
uv run pytest     # run tests (31 tests, all must pass)
```

## tools.py

Single flat module. All Firefly III interaction lives here.

**Key exports:**
- `FireflyClient` — wraps `ApiClient`; reads `FIREFLY_BASE_URL` and `FIREFLY_API_TOKEN` from env
- `get_tools()` — returns 13 OpenAI function-calling tool schemas (via `pydantic_function_tool`)
- `dispatch(client, tool_name, args)` — routes tool calls to handlers

**Tool schemas** are Pydantic `BaseModel` subclasses passed to `pydantic_function_tool`. Add new tools by: creating a model class, writing a `_handler_*` function, registering both in `TOOLS` and `_HANDLERS`.

**Known import quirk:** `firefly_iii_client.Configuration` in `__init__` is a Pydantic response model, not the HTTP config. Always import from `firefly_iii_client.configuration` directly.

**Error handling pattern:** handlers return `{"error": "..."}` on failure — never raise. Split try/except blocks: one for required-arg extraction (`KeyError`/`ValueError`), one for API calls (`ApiException`).

**Write handlers** (tags, category) use GET-then-PUT: fetch all splits first to preserve required fields before updating.

## Tools reference

| Name | Type | Description |
|------|------|-------------|
| `list_transactions` | Read | Paginated transaction list |
| `get_transactions_by_date_range` | Read | Transactions between two dates |
| `search_transactions` | Read | Full-text search |
| `update_transaction_tags` | Write | Replace all tags on a transaction |
| `update_transaction_category` | Write | Set category on a transaction |
| `list_accounts` | Read | Accounts with balances |
| `get_expense_insights` | Read | Expense totals by category for a date range |
| `get_income_insights` | Read | Income totals by category for a date range |
| `list_categories` | Read | All categories |
| `list_tags` | Read | All tags |
| `sum_transactions` | Calc | Sum already-fetched transaction dicts (Decimal arithmetic) |
| `calculate_net` | Calc | Income − expenses for a date range |
| `compare_periods` | Calc | Income/expense/net delta between two date ranges |

## Testing

Mock at the API class level: `@patch("tools.TransactionsApi")` etc. Tests must not make real HTTP calls.
