# Architecture

**Analysis Date:** 2026-05-06

## Pattern Overview

**Overall:** Single-module dispatch pattern (tool registry)

**Key Characteristics:**
- Entire API surface lives in one flat module (`tools.py`, 630 lines)
- Tool schema → handler mapping via parallel data structures (`TOOLS` list + `_HANDLERS` dict)
- OpenAI function-calling protocol: Pydantic schemas are converted to JSON tool definitions
- All errors returned as `{"error": "..."}` dicts — handlers never raise
- Firefly III API client is a thin wrapper; no domain model layer

## Layers

**Schema Layer (Pydantic Models):**
- Purpose: Define tool parameter contracts for OpenAI function calling
- Location: `tools.py` lines 44–158
- Contains: 13 `BaseModel` subclasses (one per tool)
- Depends on: `pydantic.BaseModel`, `pydantic.Field`, `openai.pydantic_function_tool`
- Used by: `TOOLS` list, which serializes them into OpenAI tool JSON schemas

**Client Layer (FireflyClient):**
- Purpose: Configure and hold a single `ApiClient` instance for Firefly III HTTP calls
- Location: `tools.py` lines 23–38
- Contains: `FireflyClient.__init__` — reads env vars or constructor args, builds `Configuration` + `ApiClient`
- Depends on: `firefly_iii_client.configuration.Configuration`, `firefly_iii_client.ApiClient`
- Used by: Every `_handler_*` function receives `client: FireflyClient` as first arg

**Handler Layer (_handler_* functions):**
- Purpose: Implement tool logic — call Firefly III API classes, extract/transform results
- Location: `tools.py` lines 180–588
- Contains: 13 private handler functions + 2 shared helpers (`_build_split_update`, `_fetch_net`, `_insight_total`)
- Depends on: Firefly III API classes (`TransactionsApi`, `AccountsApi`, `CategoriesApi`, `TagsApi`, `SearchApi`, `InsightApi`), `Decimal` for financial arithmetic
- Used by: `dispatch()` routes tool calls to these handlers

**Dispatch Layer:**
- Purpose: Route a `(tool_name, args)` call to the correct handler
- Location: `tools.py` lines 591–630
- Contains: `_HANDLERS` dict (name → handler fn), `dispatch()`, `get_tools()`
- Depends on: `_HANDLERS` dict, `TOOLS` list
- Used by: External caller (e.g., OpenAI agent loop)

## Data Flow

**Tool Call Execution:**

1. External code calls `dispatch(client, tool_name, args_dict)` — e.g., from an OpenAI agent loop parsing `tool_call.function.name` and `json.loads(tool_call.function.arguments)`
2. `dispatch()` looks up `tool_name` in `_HANDLERS` dict; returns `{"error": "Unknown tool: ..."}` if missing
3. Handler receives `(client: FireflyClient, args: dict)` — args are already parsed from JSON
4. Handler instantiates the needed Firefly III API class (e.g., `TransactionsApi(client.api_client)`)
5. For read handlers: call API method, unwrap `resp.data`, serialize each item via `.to_dict()`, return `{"transactions": [...]}` etc.
6. For write handlers: GET existing transaction first (to preserve all split fields), build `TransactionSplitUpdate` via `_build_split_update()`, then PUT via `api.update_transaction()`
7. For calc handlers (`sum_transactions`, `calculate_net`, `compare_periods`): aggregate data using `Decimal` arithmetic, return monetary values as strings
8. Errors at any stage: caught by try/except, returned as `{"error": "..."}`

**State Management:**
- No persistent state — each handler call is stateless
- `FireflyClient` holds a single `ApiClient` (HTTP connection config only)
- Pagination state managed by caller (pass `page` param)
- Financial arithmetic uses `Decimal` to avoid floating-point errors; all monetary outputs are strings

## Key Abstractions

**FireflyClient:**
- Purpose: Thin wrapper around `firefly_iii_client.ApiClient` with env-var-based configuration
- Examples: `tools.py` line 23
- Pattern: Constructor reads `FIREFLY_BASE_URL`/`FIREFLY_API_TOKEN` from env or explicit args; raises `ValueError` if missing

**Pydantic Tool Schema:**
- Purpose: Define OpenAI function-calling parameter contracts with type safety and auto-generated descriptions
- Examples: `tools.py` lines 44–158 (`ListTransactions`, `GetTransactionsByDateRange`, etc.)
- Pattern: `BaseModel` subclass → `pydantic_function_tool(Model, name="snake_case")` → JSON schema in `TOOLS` list

**Handler Function:**
- Purpose: Execute a single tool's business logic
- Examples: `tools.py` lines 180–588 (`_handler_list_transactions`, `_handler_update_transaction_tags`, etc.)
- Pattern: Private function `_handler_{tool_name}(client: FireflyClient, args: dict) -> dict`; returns data dict or `{"error": "..."}`

**GET-then-PUT (write handlers):**
- Purpose: Preserve all required transaction split fields when updating tags or category
- Examples: `_handler_update_transaction_tags` (line 274), `_handler_update_transaction_category` (line 301)
- Pattern: Fetch existing transaction → iterate splits → build `TransactionSplitUpdate` via `_build_split_update()` with overrides → PUT full update

**Insight Aggregation (calc handlers):**
- Purpose: Derive financial summaries (net, period comparison) from category-level insight data
- Examples: `_fetch_net` (line 456), `_insight_total` (line 448), `_handler_compare_periods` (line 540)
- Pattern: Call expense/income insight handlers → sum `difference_float` via `Decimal` → compute net/delta

## Entry Points

**dispatch(client, tool_name, args):**
- Location: `tools.py` line 608
- Triggers: External agent loop (e.g., OpenAI chat completion tool call handler)
- Responsibilities: Look up handler by name, invoke with client and args, return result dict

**get_tools():**
- Location: `tools.py` line 625
- Triggers: External code preparing OpenAI API call
- Responsibilities: Return list of 13 OpenAI function-calling tool JSON schemas

**FireflyClient(base_url, api_token):**
- Location: `tools.py` line 23
- Triggers: External code initializing the client
- Responsibilities: Validate config, create `Configuration` + `ApiClient`

**main.py:**
- Location: `main.py` line 1
- Triggers: `python main.py` or `uv run main.py`
- Responsibilities: Stub — prints "Hello from finance-analyzer!"

## Error Handling

**Strategy:** Error-as-return-value (never raise from handlers)

**Patterns:**
- **Missing required args:** `try/except KeyError` → `{"error": f"Missing required argument: {e}"}`
- **Invalid date format:** `try/except ValueError` → `{"error": f"Invalid date format: {e}"}`
- **Firefly III API errors:** `try/except ApiException` → `{"error": str(e)}`
- **Unknown tool:** `dispatch()` returns `{"error": f"Unknown tool: {tool_name}"}`
- **Critical separation:** Arg-extraction errors and API-call errors use separate try/except blocks so arg errors don't mask API errors
- **Client init errors:** `FireflyClient.__init__` raises `ValueError` (these are not handler errors — they indicate misconfiguration)

## Cross-Cutting Concerns

**Logging:** No logging framework — all handlers are silent on success. Errors are returned to caller, not logged.

**Validation:** Pydantic schemas validate tool parameters at the OpenAI layer. Handler-level validation is limited to required-arg extraction and date parsing.

**Authentication:** Bearer token via `FIREFLY_API_TOKEN` env var or constructor arg, applied to all Firefly III API calls through `Configuration(access_token=...)`.

**Pagination:** All list endpoints support `limit` (default 50) and `page` (default 1). Caller is responsible for iterating pages.

**Monetary Precision:** `Decimal` arithmetic throughout calc handlers. All monetary values in return dicts are strings (never float) to preserve precision.

**Serialization:** Firefly III SDK response objects are serialized via `.to_dict()` before returning. No raw SDK objects leak out of handlers.

---

*Architecture analysis: 2026-05-06*
