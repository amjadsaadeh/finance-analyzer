# Coding Conventions

**Analysis Date:** 2026-05-06

## Naming Patterns

**Files:**
- Single-word lowercase Python modules: `tools.py`, `main.py`
- Test files mirror source: `tests/test_tools.py`
- Module names are singular nouns or noun phrases

**Classes:**
- PascalCase: `FireflyClient`, `ListTransactions`, `GetTransactionsByDateRange`, `UpdateTransactionTags`
- Schema classes (Pydantic `BaseModel` subclasses) use descriptive verb-noun or noun-phrase names
- Private helpers prefixed with underscore: `_build_split_update`

**Functions:**
- Handler functions use `_handler_` prefix + snake_case tool name: `_handler_list_transactions`, `_handler_get_expense_insights`
- Public functions are snake_case: `dispatch`, `get_tools`
- Private helpers use `_` prefix: `_insight_total`, `_fetch_net`, `_build_split_update`

**Variables:**
- snake_case throughout: `total_income`, `split_count`, `mock_api_class`
- Result dicts use short keys: `"transactions"`, `"insights"`, `"error"`
- Monetary amounts are `Decimal` internally, converted to `str` for output

**Constants:**
- Uppercase module-level: `TOOLS`, `_HANDLERS`

## Code Style

**Formatting:**
- No formatter configured (no black, ruff format, etc.)
- 4-space indentation
- 120-char line width observed in `tools.py`
- Blank lines between logical sections with comment headers

**Linting:**
- No linter configured (no ruff, flake8, pylint, etc.)
- Only `pytest >= 8.0.0` in dev dependencies

**Section Headers:**
- Comment separators with dashes: `# --- Tool parameter schemas ---------------------------------------------------`
- Consistent section structure: schemas → TOOLS list → handlers → _HANDLERS dict → dispatch/get_tools

## Import Organization

**Order (observed in `tools.py`):**
1. Standard library: `os`, `datetime`, `decimal`, `typing`
2. Third-party (Pydantic/OpenAI): `pydantic`, `openai`
3. Firefly III client: `firefly_iii_client.configuration`, `firefly_iii_client.ApiClient`, `firefly_iii_client.api`, `firefly_iii_client.models`, `firefly_iii_client.exceptions`

**Path Aliases:**
- None configured — all imports use full module paths

**Critical Import Quirk:**
- Always `from firefly_iii_client.configuration import Configuration`
- Never `from firefly_iii_client import Configuration` — that imports the Pydantic response model, not the HTTP config

## Error Handling

**Primary Pattern — Error dicts, never exceptions:**
All handlers return `{"error": "..."}` on failure. They never raise exceptions.

```python
# CORRECT pattern
def _handler_example(client: FireflyClient, args: dict) -> dict:
    api = TransactionsApi(client.api_client)
    try:
        tx_id = args["transaction_id"]
    except KeyError as e:
        return {"error": f"Missing required argument: {e}"}
    try:
        resp = api.list_transaction(limit=args.get("limit", 50))
        return {"transactions": [t.to_dict() for t in resp.data]}
    except ApiException as e:
        return {"error": str(e)}
```

**Two-block try/except pattern:**
1. First block: arg extraction — catches `KeyError` (missing args) and `ValueError` (bad date format)
2. Second block: API calls — catches `ApiException`

Handlers that only use optional args (with `.get()`) skip the first block.

**Validation errors use descriptive messages:**
- `f"Missing required argument: {e}"` for `KeyError`
- `f"Invalid date format: {e}"` for `ValueError` on date parsing

**Error propagation in composite handlers:**
When a handler calls other handlers (e.g., `_fetch_net` calls `_handler_get_expense_insights`), it checks for `"error"` in the result dict and returns early:

```python
expense_result = _handler_get_expense_insights(client, args)
if "error" in expense_result:
    return expense_result
```

**FireflyClient raises ValueError:**
The only exception raised (not returned as dict): `FireflyClient.__init__` raises `ValueError` if `FIREFLY_BASE_URL` or `FIREFLY_API_TOKEN` is missing.

## Logging

**Framework:** No logging framework — console only (print in `main.py`)

**Patterns:**
- Handlers do not log; they return data or error dicts
- The `dispatch()` function does not log; it routes and returns
- Logging is the caller's responsibility (presumably the OpenAI agent loop)

## Comments

**When to Comment:**
- Module section dividers with dashed separators
- Docstrings on every class, handler function, and public function
- Inline comments for non-obvious logic (e.g., Decimal arithmetic rationale)

**Docstrings:**
- All handler functions have docstrings following this pattern:
  ```
  """One-line summary.

  Args:
      args: Required keys: ...; Optional keys: ...

  Returns:
      Dict with ... or ``{"error": "..."}`` on ...
  """
  ```
- Pydantic model classes use one-line docstrings as tool descriptions
- Private helpers (`_build_split_update`, `_insight_total`, `_fetch_net`) also have docstrings

## Function Design

**Size:** Handlers are typically 10-25 lines (excluding docstrings). The `dispatch` function is 6 lines.

**Parameters:**
- Handler signature is always `(client: FireflyClient, args: dict) -> dict`
- Args are extracted from the dict using `args["key"]` (required) or `args.get("key", default)` (optional)
- `str()` wrapping on IDs: `tx_id = str(args["transaction_id"])` in write handlers

**Return Values:**
- Success: dict with a single top-level key matching the resource (`"transactions"`, `"accounts"`, `"insights"`, `"categories"`, `"tags"`)
- Failure: `{"error": "descriptive message"}`
- Monetary values are always `str` (not `float`) to preserve Decimal precision
- API response objects are converted via `.to_dict()` before returning

**Default Values:**
- Pagination defaults: `limit=50, page=1` — consistent across all handlers
- These are specified both in Pydantic `Field()` defaults and in handler `.get()` calls

## Module Design

**Exports:**
- `FireflyClient` — client class
- `TOOLS` — tool schema list (also via `get_tools()`)
- `_HANDLERS` — handler dispatch dict
- `dispatch(client, tool_name, args)` — routing function
- `get_tools()` — public accessor for tool schemas

**No Barrel Files:**
- Single-module design — `tools.py` is the entire API surface
- Tests import directly: `from tools import dispatch, FireflyClient, get_tools`

**Adding a New Tool:**
1. Create a Pydantic `BaseModel` subclass in `tools.py` (e.g., `class MyNewTool(BaseModel)`)
2. Write a `_handler_*` function with signature `(client: FireflyClient, args: dict) -> dict`
3. Register the schema in the `TOOLS` list via `pydantic_function_tool(MyNewTool, name="my_new_tool")`
4. Register the handler in `_HANDLERS` dict: `"my_new_tool": _handler_my_new_tool`
5. Add corresponding test(s) in `tests/test_tools.py`

**Pydantic Model Conventions:**
- Use `Field(...)` for required fields (with `description`)
- Use `Field(default, description=...)` for optional fields
- Use `str | None = Field(None, description=...)` for truly optional fields
- Use `list[str]` for list types, `list[dict[str, Any]]` for dict lists

## Monetary Precision

**Critical Rule:** Always use `Decimal` for monetary calculations, never `float`.

```python
from decimal import Decimal

# Converting from string to Decimal
amount = Decimal(str(split.get("amount", "0")))

# Summing with Decimal
total = sum(Decimal(str(abs(e.get("difference_float", 0)))) for e in insights)

# Returning as string
return {"net": str(total)}
```

The `sum_transactions` handler and `_insight_total`/`_fetch_net`/`compare_periods` logic all use `Decimal` with string I/O.

---
*Convention analysis: 2026-05-06*