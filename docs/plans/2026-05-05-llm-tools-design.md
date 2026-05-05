# LLM Tools for Firefly III — Design

**Date:** 2026-05-05
**Scope:** OpenAI function-calling tools that fetch and mutate data via the Firefly III API

---

## Goal

Provide an LLM (via OpenAI tool calling) with a set of tools to query Firefly III transaction data, accounts, budgets, and analytics, and to update tags/categories on transactions. Tools are used by a finance analyzer that answers questions about personal/family accounts.

---

## Architecture

Single file: `tools.py`

```
tools.py
├── FireflyClient          — wraps Configuration + ApiClient init (env vars or explicit args)
├── TOOLS                  — list of OpenAI JSON tool schemas
├── _handler_*             — one private function per tool
├── dispatch(client, name, args)  — routes tool_name → handler
└── get_tools()            — returns TOOLS list
```

Config sourced from env vars: `FIREFLY_BASE_URL`, `FIREFLY_API_TOKEN`.

---

## Tools

| # | Name | Domain | Read/Write |
|---|------|--------|------------|
| 1 | `list_transactions` | Transactions | Read |
| 2 | `get_transactions_by_date_range` | Transactions | Read |
| 3 | `search_transactions` | Transactions | Read |
| 4 | `update_transaction_tags` | Transactions | Write |
| 5 | `update_transaction_category` | Transactions | Write |
| 6 | `list_accounts` | Accounts | Read |
| 7 | `get_expense_insights` | Insights | Read |
| 8 | `get_income_insights` | Insights | Read |
| 9 | `list_categories` | Categories | Read |
| 10 | `list_tags` | Tags | Read |

---

## Data Flow

1. `FireflyClient` initializes `Configuration(host, access_token)` and `ApiClient`
2. Each handler instantiates the relevant API class (e.g., `TransactionsApi(client.api_client)`)
3. API response objects are unwrapped (`.data`) and serialized via `.to_dict()`
4. Handlers return plain JSON-serializable dicts
5. `ApiException` is caught and returned as `{"error": str(e)}`

---

## Error Handling

- All handlers wrapped in try/except for `ApiException`
- Returns `{"error": "..."}` — LLM can surface or retry gracefully
- No crashes on 401/404/500

---

## Usage Pattern

```python
from tools import FireflyClient, get_tools, dispatch

client = FireflyClient()  # reads FIREFLY_BASE_URL, FIREFLY_API_TOKEN from env

# Pass to OpenAI
response = openai.chat.completions.create(
    model="gpt-4o",
    messages=[...],
    tools=get_tools(),
)

# Execute tool calls
for tool_call in response.choices[0].message.tool_calls:
    result = dispatch(client, tool_call.function.name, json.loads(tool_call.function.arguments))
```

---

## Out of Scope

- Bills, piggy banks, rules, webhooks, recurrences — not needed for analysis
- Budgets as a domain — deferred (insights cover spending-vs-budget indirectly)
- Creating/deleting transactions or accounts
