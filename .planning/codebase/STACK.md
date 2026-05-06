# Technology Stack

**Analysis Date:** 2026-05-06

## Languages

**Primary:**
- Python 3.12 - Entire codebase (specified in `.python-version` and `pyproject.toml` `requires-python = ">=3.12"`)

**Secondary:**
- None

## Runtime

**Environment:**
- CPython 3.12.3 (installed in `.venv/`)
- Managed by uv via `.python-version` file (pins to `3.12`)

**Package Manager:**
- uv 0.11.7
- Lockfile: `uv.lock` (present, 441 lines, deterministic builds)
- Virtual environment: `.venv/` (gitignored)

## Frameworks

**Core:**
- None (no web framework — this is a library/tool module, not a server)
- Pydantic 2.13.3 — Schema definition for tool parameters (via `BaseModel`, `Field`)
- OpenAI SDK 2.34.0 — Tool schema generation via `pydantic_function_tool()`

**Testing:**
- pytest 9.0.3 — All tests (configured in `pyproject.toml` `[tool.pytest.ini_options]`)

**Build/Dev:**
- uv — Dependency resolution, virtualenv management, script running
- No linter, formatter, or type checker configured

## Key Dependencies

**Critical:**
- `firefly-iii-api-client` 6.2.21.0 — Auto-generated OpenAPI client for Firefly III REST API. Provides `ApiClient`, `Configuration`, API classes (`TransactionsApi`, `AccountsApi`, `CategoriesApi`, `TagsApi`, `SearchApi`, `InsightApi`), models (`TransactionUpdate`, `TransactionSplitUpdate`), and `ApiException`
- `openai` 2.34.0 — OpenAI Python SDK. Used exclusively for `pydantic_function_tool()` helper that converts Pydantic models into OpenAI function-calling JSON schemas. No direct LLM API calls in current code

**Infrastructure (transitive):**
- `pydantic` 2.13.3 — Data validation and schema generation (shared dep of both `openai` and `firefly-iii-api-client`)
- `pydantic-core` 2.46.3 — Rust-based Pydantic validation engine
- `httpx` 0.28.1 — HTTP client used by OpenAI SDK
- `urllib3` 2.6.3 — HTTP client used by Firefly III API client
- `python-dateutil` 2.9.0.post0 — Date parsing (Firefly III client dep)

## Configuration

**Environment:**
- `FIREFLY_BASE_URL` — Required. Base URL of the Firefly III instance (e.g., `https://firefly.example.com/api`)
- `FIREFLY_API_TOKEN` — Required. Personal access token for Firefly III API authentication
- No `.env` file present; env vars must be set externally or passed to `FireflyClient()` constructor

**Build:**
- `pyproject.toml` — Project metadata, dependencies, and pytest config
- `.python-version` — Pins Python to 3.12
- `uv.lock` — Lockfile for reproducible installs

**Test:**
- `pyproject.toml` `[tool.pytest.ini_options]` — `testpaths = ["tests"]`

## Platform Requirements

**Development:**
- Python 3.12+
- uv package manager
- Access to a Firefly III instance (or mocked in tests)

**Production:**
- Python 3.12+ runtime
- Network access to a Firefly III host
- Environment variables for Firefly III connection
- No containerization or deployment config present

---

*Stack analysis: 2026-05-06*
