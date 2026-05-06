# External Integrations

**Analysis Date:** 2026-05-06

## APIs & External Services

**Finance Management (Firefly III):**
- Firefly III — Self-hosted personal finance manager; the primary data source and write target
  - SDK/Client: `firefly-iii-api-client` 6.2.21.0 (auto-generated OpenAPI client)
  - Auth: Bearer token (`FIREFLY_API_TOKEN` env var) — personal access token issued by Firefly III
  - Base URL: `FIREFLY_BASE_URL` env var (e.g., `https://firefly.example.com/api`)
  - Client setup: `FireflyClient` class in `tools.py` lines 23–38 — wraps `ApiClient` with `Configuration(host=..., access_token=...)`
  - **Critical import quirk:** Always import `from firefly_iii_client.configuration import Configuration`. The `Configuration` in `firefly_iii_client.__init__` is a Pydantic response model, not the HTTP client config class.

**API Classes Used (from `firefly_iii_client.api`):**
- `TransactionsApi` — Read/write transactions (`tools.py` lines 11–12)
  - `list_transaction(limit, page, start, end)` — Paginated listing, optionally filtered by date range
  - `get_transaction(tx_id)` — Fetch single transaction (used in write handlers to preserve existing fields)
  - `update_transaction(tx_id, TransactionUpdate)` — Replace transaction (PUT semantics)
- `AccountsApi` — Read accounts (`tools.py` line 13)
  - `list_account(limit, page, type)` — Paginated listing with optional type filter
- `CategoriesApi` — Read categories (`tools.py` line 14)
  - `list_category(limit, page)` — Paginated category listing
- `TagsApi` — Read tags (`tools.py` line 15)
  - `list_tag(limit, page)` — Paginated tag listing
- `SearchApi` — Full-text search (`tools.py` line 16)
  - `search_transactions(query, limit, page)` — Search across transaction descriptions
- `InsightApi` — Aggregated financial insights (`tools.py` line 17)
  - `insight_expense_category(start, end, accounts)` — Expense totals grouped by category
  - `insight_income_category(start, end, accounts)` — Income totals grouped by category

**Models Used (from `firefly_iii_client.models`):**
- `TransactionUpdate` — Wrapper for transaction update payload
- `TransactionSplitUpdate` — Individual split within a transaction update; requires `description`, `date`, `amount`, `type`, `source_id`, `destination_id` to be preserved during updates

**LLM / Tool Schema (OpenAI):**
- OpenAI API — Used for function-calling tool schema generation only
  - SDK: `openai` 2.34.0
  - Usage: `pydantic_function_tool(Model, name="tool_name")` generates OpenAI-compatible JSON schema from Pydantic models (`tools.py` line 7, lines 160–174)
  - No direct LLM completion calls exist in the current codebase — `main.py` is a stub
  - Intended usage pattern: `openai.chat.completions.create(tools=get_tools())` (documented in `tools.py` line 628 docstring)

## Data Storage

**Databases:**
- None directly — Firefly III is the sole data store. The application has no local database, ORM, or persistence layer.

**File Storage:**
- Local filesystem only (no cloud storage)

**Caching:**
- None

## Authentication & Identity

**Auth Provider:**
- Firefly III Personal Access Token (PAT)
  - Implementation: Bearer token passed via `Configuration(access_token=...)` in `tools.py` line 37
  - Config precedence: constructor arguments > environment variables (`FIREFLY_API_TOKEN`)
  - Token must have appropriate permissions for transaction read/write operations in Firefly III

## Monitoring & Observability

**Error Tracking:**
- None

**Logs:**
- No structured logging — errors are returned as `{"error": "..."}` dicts from handlers
- No log framework or instrumentation

## CI/CD & Deployment

**Hosting:**
- Not configured — no Dockerfile, docker-compose, or deployment manifests

**CI Pipeline:**
- None — no GitHub Actions, GitLab CI, or similar configuration files detected

## Environment Configuration

**Required env vars:**
- `FIREFLY_BASE_URL` — Base URL of Firefly III API endpoint (e.g., `https://firefly.example.com/api`)
- `FIREFLY_API_TOKEN` — Firefly III personal access token for API authentication

**Secrets location:**
- No `.env` file present in repository
- No secrets manager integration
- Tokens expected to be set via shell environment or passed to `FireflyClient()` constructor

## Webhooks & Callbacks

**Incoming:**
- None

**Outgoing:**
- None

---

*Integration audit: 2026-05-06*
