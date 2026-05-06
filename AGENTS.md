# finance-analyzer — Agent Notes

## Commands

```bash
uv sync --dev         # install deps (python 3.12, managed by uv)
uv run pytest         # run all 31 tests (must pass)
uv run pytest -k "test_name"   # run a single test or substring match
```

No lint, typecheck, or formatting commands are configured — only pytest.

## Architecture

Single-module design: **`tools.py`** is the entire API surface. `main.py` is a stub entry point.

### Adding a tool

1. Create a Pydantic `BaseModel` subclass for the parameter schema
2. Write a `_handler_*` function with signature `(client: FireflyClient, args: dict) -> dict`
3. Register the schema in `TOOLS` via `pydantic_function_tool(Model, name="tool_name")`
4. Register the handler in `_HANDLERS` dict

### Critical patterns

- **Error handling:** Handlers return `{"error": "..."}` — never raise. Use separate try/except blocks: one for arg extraction (`KeyError`/`ValueError`), one for API calls (`ApiException`).
- **Write handlers** (tags, category) use GET-then-PUT: fetch all splits first to preserve required fields before updating.
- **Import quirk:** Always `from firefly_iii_client.configuration import Configuration`. The `Configuration` in `firefly_iii_client.__init__` is a Pydantic response model, not the HTTP client config.

## Testing

- Mock at the API class level: `@patch("tools.TransactionsApi")` etc. — never make real HTTP calls.
- `FireflyClient` tests use `_make_client()` helper with explicit `base_url`/`api_token` to avoid needing env vars.
- To isolate from env: `patch.dict(os.environ, {...}, clear=True)` removes `FIREFLY_BASE_URL`/`FIREFLY_API_TOKEN`.

## Env

`FireflyClient` requires `FIREFLY_BASE_URL` and `FIREFLY_API_TOKEN` set via env vars or constructor args.