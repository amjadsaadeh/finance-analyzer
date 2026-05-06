# Codebase Concerns

**Analysis Date:** 2026-05-06

## Tech Debt

**Single-file monolith (`tools.py`):**
- Issue: All 13 tool schemas, 12 handler functions, 3 helper functions, `FireflyClient`, `dispatch`, `get_tools`, and the `TOOLS`/`_HANDLERS` registries live in a single 630-line module. Readability and merge conflicts increase as tools are added.
- Files: `tools.py`
- Impact: Hard to navigate; PRs touching different tools will conflict; no clear module boundaries.
- Fix approach: Split into `client.py`, `schemas.py`, `handlers/` (one module per domain: transactions, accounts, insights, calculations), and `registry.py`. Keep `tools.py` as a re-export barrel if needed for backward compatibility.

**Manual handler/schema registration (dual registry):**
- Issue: Adding a tool requires creating a schema class, a handler function, and then registering both in `TOOLS` (line 160-174) and `_HANDLERS` (line 591-605). Forgetting one registration silently creates a partial or broken tool.
- Files: `tools.py` lines 160-174 and 591-605
- Impact: Easy to introduce bugs when adding tools; schema and handler can drift out of sync.
- Fix approach: Use a decorator like `@register_tool(name="list_transactions", schema=ListTransactions)` that appends to both `TOOLS` and `_HANDLERS` atomically. Or use a `_TOOL_DEFS` list of `(SchemaClass, handler, name)` tuples and build both dicts from it.

**No static analysis tooling:**
- Issue: `pyproject.toml` has no `[tool.mypy]`, `[tool.ruff]`, `[tool.black]`, or `[tool.isort]` sections. AGENTS.md explicitly states "No lint, typecheck, or formatting commands are configured — only pytest."
- Files: `pyproject.toml`
- Impact: No automated enforcement of code quality; type errors, unused imports, and style drift go undetected.
- Fix approach: Add `ruff` for linting+formatting and `mypy` for type checking. Configure `pyproject.toml` with `[tool.ruff]` and `[tool.mypy]` sections. Add CI step or pre-commit hook.

**Stub entry point (`main.py`):**
- Issue: `main.py` is a 6-line stub that prints `"Hello from finance-analyzer!"`. There is no integration code connecting `FireflyClient`, `dispatch`, or `get_tools` to any runtime — not even a CLI or API server.
- Files: `main.py`
- Impact: The tools module is a library with no runnable consumer. Developers must write ad-hoc scripts to test manually.
- Fix approach: Implement a CLI entry point (e.g., via `click` or `argparse`) or a minimal FastAPI/HTTP server that wires `FireflyClient` → `dispatch`. Update `pyproject.toml` `[project.scripts]` to expose it.

**Empty README:**
- Issue: `README.md` is 0 bytes. No onboarding documentation.
- Files: `README.md`
- Impact: New contributors have no quick-start guide.
- Fix approach: Add project description, setup instructions, env var requirements, and tool reference table (the content already exists in `CLAUDE.md` and `AGENTS.md` — consolidate into README).

## Known Bugs

**Silent error swallowing in `_handler_sum_transactions`:**
- Symptoms: Transactions with unparseable amounts are silently skipped via `except Exception: continue` at line 500-501. If many transactions have bad data, the sum will be wrong with no indication.
- Files: `tools.py` lines 496-501
- Trigger: Pass transactions where `split.get("amount", "0")` produces a non-numeric value that `Decimal(str(...))` cannot parse.
- Workaround: None. The function returns a result that looks correct but may be incomplete.
- Fix approach: Replace broad `except Exception: continue` with `except InvalidOperation: continue` (from `decimal.InvalidOperation`), and add a `skipped` count to the return dict. Alternatively, log the skip.

**Inconsistent date validation across handlers:**
- Symptoms: `_handler_get_transactions_by_date_range`, `_handler_get_expense_insights`, and `_handler_get_income_insights` validate date strings via `datetime.date.fromisoformat()`, but `_handler_calculate_net` and `_handler_compare_periods` extract dates as raw strings and pass them to `_fetch_net` without validation. Invalid dates only surface as errors from nested handlers, producing confusing error messages like `"Missing required argument: ..."` instead of `"Invalid date format: ..."`.
- Files: `tools.py` lines 519-537 (`_handler_calculate_net`), lines 540-560 (`_handler_compare_periods`), lines 456-472 (`_fetch_net`)
- Trigger: Pass `"2024-13-01"` or `"not-a-date"` as `start_date` to `calculate_net`.
- Workaround: Only call with validated date strings.
- Fix approach: Validate dates in `_handler_calculate_net` and `_handler_compare_periods` before calling `_fetch_net`, same pattern as the date-range handler (separate try/except for `KeyError` and `ValueError`).

## Security Considerations

**Credentials stored as plain instance attributes:**
- Risk: `FireflyClient.base_url` and `FireflyClient.api_token` are stored as plain string attributes, accessible via `repr()` or accidental logging/printing.
- Files: `tools.py` lines 31-37 (`FireflyClient.__init__`)
- Current mitigation: None. The `__repr__` method is inherited from `object` and includes attribute values.
- Recommendations: Override `__repr__` to redact `api_token`. Add a `__str__` method that omits the token. Consider using `@property` with a private `_api_token` attribute.

**No `.env.example` file:**
- Risk: `FireflyClient` requires `FIREFLY_BASE_URL` and `FIREFLY_API_TOKEN` env vars (lines 31-36), but no `.env.example` or `.env.schema` documents what's needed. The only documentation is in `AGENTS.md` and `CLAUDE.md`.
- Files: Project root (missing file)
- Current mitigation: `AGENTS.md` and `CLAUDE.md` document the requirement.
- Recommendations: Add `.env.example` with `FIREFLY_BASE_URL=https://your-firefly-instance.example.com/api` and `FIREFLY_API_TOKEN=your-token-here` (placeholder values only). Ensure `.env` is in `.gitignore`.

**No HTTPS enforcement on base URL:**
- Risk: `FireflyClient` accepts any `base_url` including `http://` URLs, which would transmit the API token in plaintext.
- Files: `tools.py` line 31-37
- Current mitigation: None.
- Recommendations: Validate that `base_url` starts with `https://` (or `http://localhost`/`http://127.0.0.1` for development) in `FireflyClient.__init__`. Raise `ValueError` if not.

## Performance Bottlenecks

**No pagination automation:**
- Problem: All list handlers (`list_transactions`, `list_accounts`, `list_categories`, `list_tags`) accept `page` and `limit` but don't expose total-count metadata. Callers must manually paginate with no way to know how many pages exist.
- Files: `tools.py` lines 180-198 (`_handler_list_transactions`), 328-347 (`_handler_list_accounts`), 408-425 (`_handler_list_categories`), 428-445 (`_handler_list_tags`)
- Cause: Each handler returns `[t.to_dict() for t in resp.data]` and discards the `meta.pagination` fields from the Firefly III response.
- Improvement path: Include pagination metadata in the return dict: `{"transactions": [...], "pagination": {"total": N, "per_page": 50, "current_page": 1}}`. This requires extracting `resp.meta` or equivalent from the API response.

**Write handlers are non-atomic (race condition):**
- Problem: `_handler_update_transaction_tags` and `_handler_update_transaction_category` perform GET-then-PUT without any locking or optimistic concurrency checks.
- Files: `tools.py` lines 274-298, 301-325
- Cause: The GET fetches the current transaction, `_build_split_update` modifies it, and the PUT writes it back. If two concurrent requests modify the same transaction, the second write overwrites the first with stale data.
- Improvement path: Use Firefly III's native endpoints for partial updates if available. Alternatively, implement optimistic locking by checking `updated_at` timestamps before writing. Document the concurrency limitation for callers.

**New API client per handler call:**
- Problem: Every handler creates a new `TransactionsApi(client.api_client)` / `AccountsApi(...)` / etc. instance. While lightweight, this is unnecessary object creation per call.
- Files: `tools.py` — every `_handler_*` function
- Cause: No API client caching.
- Improvement path: Low priority. Cache API class instances on `FireflyClient` (e.g., `_transactions_api` property) if profiling shows this matters.

## Fragile Areas

**Firefly III client import quirk:**
- Files: `tools.py` line 9
- Why fragile: `from firefly_iii_client.configuration import Configuration` — importing from the submodule is required because `firefly_iii_client.Configuration` (from `__init__`) is a Pydantic response model, not the HTTP client config. If the SDK reorganizes its package structure, this import breaks silently (wrong class at runtime).
- Safe modification: Never change this import to `from firefly_iii_client import Configuration`. Add a runtime assertion that `Configuration` is the expected class (has `host` and `access_token` parameters).
- Test coverage: No test verifies this specific import path.

**`_build_split_update` may miss required fields:**
- Files: `tools.py` lines 256-271
- Why fragile: The function manually selects which fields to preserve from the existing split (description, date, amount, type, tags, category_name, source_id, destination_id). If Firefly III adds required fields or if the existing transaction has fields like `currency_code`, `notes`, `budget_id`, etc., those will be silently dropped by the PUT.
- Safe modification: Before adding fields to `_build_split_update`, check the Firefly III API docs for all required `TransactionSplitUpdate` fields. Consider using a broader approach: `TransactionSplitUpdate(**{k: v for k, v in split.to_dict().items() if k not in excluded_fields})`.
- Test coverage: Tested indirectly through `update_transaction_tags` tests, but no direct unit test for `_build_split_update`.

**`_insight_total` depends on `difference_float` field name:**
- Files: `tools.py` lines 448-453
- Why fragile: The function reads `e.get("difference_float", 0)` from insight dicts. This field name is an implementation detail of the Firefly III SDK's `to_dict()` output. If the SDK changes the field name or structure, this function silently returns 0 for all entries.
- Safe modification: Add a test that validates the expected dict structure from `_mock_insight_entry(...).to_dict()`. Consider accessing the model attribute directly instead of going through `to_dict()`.
- Test coverage: Tested indirectly through `calculate_net`, but no direct unit test for `_insight_total`.

**TOOLS/_HANDLERS registry can silently desynchronize:**
- Files: `tools.py` lines 160-174 (`TOOLS`) and 591-605 (`_HANDLERS`)
- Why fragile: Adding a tool requires updating two separate data structures. If a handler is registered in `_HANDLERS` but the schema is missing from `TOOLS`, `dispatch` works but OpenAI function-calling breaks (or vice versa). Test `test_get_tools_names_match_handlers` only checks that names match between the two, not that schemas are correct.
- Safe modification: Use a single registration mechanism (decorator or list of tuples) that guarantees sync.
- Test coverage: `test_get_tools_names_match_handlers` and `test_get_tools_returns_13_tools` exist but are brittle — they hardcode `13` and a name set.

## Scaling Limits

**No connection pooling or timeout configuration:**
- Current capacity: Single `ApiClient` instance per `FireflyClient`. No explicit timeout, retry, or connection pool settings.
- Limit: Long-running processes or high-throughput scenarios may exhaust connections or hang indefinitely on network issues.
- Scaling path: Configure `ApiClient` with timeout settings. Add connection pooling via `urllib3.PoolManager`. Consider adding retry logic with exponential backoff for transient 5xx errors.

**No rate limiting or throttling:**
- Current capacity: Every handler directly calls the Firefly III API with no rate limiting.
- Limit: Firefly III may rate-limit or refuse requests under high concurrency.
- Scaling path: Add rate-limit awareness (e.g., respect `X-RateLimit-*` headers, add configurable delays between batch requests).

**No batch/bulk operations:**
- Current capacity: Write handlers update one transaction at a time.
- Limit: Updating tags/categories on 100 transactions requires 100+ API calls (GET + PUT each).
- Scaling path: Implement batch handlers where supported by the Firefly III API, or add queue-based processing.

## Dependencies at Risk

**`firefly-iii-api-client>=6.2.21.0`:**
- Risk: Auto-generated SDK from OpenAPI spec. API surface may change significantly between versions. The import quirk (`firefly_iii_client.configuration` vs `firefly_iii_client.Configuration`) is a symptom of codegen inconsistencies.
- Impact: Version bumps may break model classes, field names, or import paths.
- Migration plan: Pin exact version in production (e.g., `firefly-iii-api-client==6.2.21.0`). Add integration tests or contract tests that verify key model shapes. Monitor changelog.

**`openai>=2.34.0`:**
- Risk: The `pydantic_function_tool` import from `openai` is used for schema generation but this API may not be stable across major versions. The entire `openai` package is pulled in just for this one utility.
- Impact: `openai` breaking changes could break schema generation, though handlers would still work.
- Migration plan: Pin `openai` major version. Consider extracting `pydantic_function_tool` logic or using `pydantic` directly to generate JSON Schema (reducing dependency weight).

## Missing Critical Features

**No logging framework:**
- Problem: Zero `logging` or `print` statements anywhere in the codebase. No way to trace API calls, debug errors, or audit operations in production.
- Files: `tools.py`, `main.py`

**No input validation layer:**
- Problem: Pydantic schemas define parameter types for OpenAI function-calling, but `dispatch()` passes raw `args: dict` to handlers. When calling `dispatch()` directly (not via OpenAI), all arguments bypass schema validation.
- Files: `tools.py` line 608-622 (`dispatch`)

**No retry or resilience logic:**
- Problem: API calls fail permanently on transient errors (network timeouts, 5xx responses). No retry logic exists.
- Files: Every `_handler_*` function

**No pagination metadata in responses:**
- Problem: List handlers return only data arrays without total count, page info, or `has_next` indicators. Callers can't determine if more pages exist.
- Files: All `_handler_list_*` functions

## Test Coverage Gaps

**Untested error paths:**
- What's not tested: API error handling for 7 of 9 read handlers (only `list_transactions` and `update_transaction_tags` have `ApiException` error tests). Missing: `get_transactions_by_date_range`, `search_transactions`, `list_accounts`, `get_expense_insights`, `get_income_insights`, `list_categories`, `list_tags` API error paths.
- Files: `tests/test_tools.py`
- Risk: Error handling for most handlers is untested. A change to error return format could break silently.
- Priority: High

**Untested date validation:**
- What's not tested: Passing malformed date strings (e.g., `"2024-13-01"`, `"not-a-date"`) to `get_transactions_by_date_range` or insight handlers.
- Files: `tests/test_tools.py`
- Risk: `ValueError` path in date parsing is untested.
- Priority: High

**Untested `_build_split_update` directly:**
- What's not tested: The helper function's field preservation logic, especially edge cases like `source_id=0` or `destination_id=None`.
- Files: `tests/test_tools.py`
- Risk: Write handlers could silently drop fields on transactions with unusual data.
- Priority: Medium

**Untested `_insight_total` directly:**
- What's not tested: Edge cases like empty insights list, entries with `difference_float=0`, entries with missing `difference_float` key.
- Files: `tests/test_tools.py`
- Risk: Sum logic bugs could go undetected.
- Priority: Medium

**Untested `_fetch_net` directly:**
- What's not tested: Error propagation when one insight call fails but the other succeeds.
- Files: `tests/test_tools.py`
- Risk: Net calculation could return partial data or confusing errors.
- Priority: Medium

**Untested `compare_periods` division-by-zero:**
- What's not tested: When `period_a` has zero income/expenses/net, the `_delta` function should return `percent=None`. No test verifies this.
- Files: `tools.py` line 574, `tests/test_tools.py`
- Risk: `ZeroDivisionError` or `NoneType` formatting errors if edge case not handled.
- Priority: Medium

**Untested `sum_transactions` with malformed data:**
- What's not tested: Transactions missing the `amount` field, transactions with non-numeric amounts, transactions with empty `attributes.transactions` array.
- Files: `tests/test_tools.py`
- Risk: Silent data loss via the `except Exception: continue` at line 500-501.
- Priority: High

**No integration tests:**
- What's not tested: Any real interaction with a Firefly III instance.
- Files: N/A (no integration test file exists)
- Risk: Responses from the actual Firefly III SDK may not match mock shapes.
- Priority: Low (unit tests with mocks are the intended pattern, per AGENTS.md)

---

*Concerns audit: 2026-05-06*