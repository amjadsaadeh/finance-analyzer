# Stack Research

**Domain:** LLM-powered personal finance analyzer with web chat, auto-categorization, and report generation on Firefly III
**Researched:** 2026-05-06
**Confidence:** HIGH

## Recommended Stack

### Core Technologies

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| Python | 3.12 | Runtime | Existing codebase constraint; matches `.python-version` |
| FastAPI | 0.136+ | Web framework | Async-first, Pydantic-native, built-in SSE support, auto-docs. The project needs SSE streaming for chat and async for LLM calls — FastAPI was designed for exactly this. Its Pydantic integration means the existing tool schemas plug in directly. Verified latest 0.136.1 (Apr 2026). |
| OpenAI Python SDK | 2.34+ | LLM integration | Already a dependency. Chat Completions API with function calling is the core mechanism for the entire agent loop — the existing 13 tools are already OpenAI function-calling schemas. Upgrade path to 2.35+ is safe (minor version). Verified latest 2.35.0 (May 2026). |
| Pydantic | 2.13+ | Data modeling | Already a transitive dep. Used for all request/response schemas, tool parameters, and configuration. FastAPI and OpenAI SDK both depend on it — no version conflict risk. |
| Uvicorn | 0.46+ | ASGI server | Standard production server for FastAPI. Required for async LLM streaming. Install with `[standard]` extras for uvloop. Verified latest 0.46.0 (Apr 2026). |
| uv | 0.11+ | Package manager | Already in use. Manages virtualenv, dependencies, and script running via `uv.lock`. |

### Supporting Libraries

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| sse-starlette | 3.4+ | Server-Sent Events streaming | Chat streaming from server to browser. FastAPI has built-in SSE support in newer versions, but `sse-starlette` provides battle-tested `EventSourceResponse` with ping, reconnect, and cooperative shutdown. Verified 3.4.2 (May 2026). |
| Plotly | 6.7+ | Interactive chart generation | Savings reports with trend charts, pie charts, bar charts. Can render to HTML fragments for embedding in Jinja2 templates, or to static images via Kaleido. The interactive HTML mode is ideal for web-based reports. Verified 6.7.0 (Apr 2026). |
| Kaleido | 0.2+ | Static image export for Plotly | When reports need to be exported as images/PDFs rather than interactive HTML. Optional — only add if image export is required. |
| Jinja2 | 3.1+ | HTML template rendering | Report page rendering, chat UI shell. Already a transitive dep of FastAPI `[standard]`. Use for server-rendered HTML that embeds Plotly charts and chat widgets. Verified 3.1.6 (Mar 2025). |
| pydantic-settings | 2.x | Environment/config management | Centralize `OPENAI_API_KEY`, `OPENAI_MODEL`, `FIREFLY_BASE_URL`, `FIREFLY_API_TOKEN`, and app settings like host/port. Cleaner than scattered `os.environ` calls. Lives in the `pydantic` ecosystem. |
| httpx | 0.28+ | Async HTTP client (testing) | Already a transitive dep of OpenAI SDK. Used via FastAPI's `TestClient` for integration tests. No separate install needed. |

### Development Tools

| Tool | Purpose | Notes |
|------|---------|-------|
| pytest | Test runner | Already in use. Add `pytest-asyncio` for async test support (FastAPI endpoints are async). |
| pytest-asyncio | Async test mode | Required for testing async FastAPI endpoints and SSE streaming handlers. |
| httpx | Test client | Already transitive dep. Use `from fastapi.testclient import TestClient` which wraps httpx. |
| ruff | Linter + formatter | Recommended now since project has no linter configured. Fast linter, drop-in for flake8+black. |

## Installation

```bash
# Core (new deps)
uv add fastapi "uvicorn[standard]" sse-starlette plotly pydantic-settings

# Dev dependencies
uv add --dev pytest-asyncio ruff

# Optional: static image export from Plotly
# uv add kaleido
```

## Alternatives Considered

| Category | Recommended | Alternative | Why Not |
|----------|-------------|-------------|---------|
| Web framework | FastAPI | Flask | Flask is synchronous, no native async/await, harder SSE story. FastAPI's async model is essential for non-blocking LLM calls. |
| Web framework | FastAPI | Django | Massive overkill. ORM, admin, auth system — none needed for a single-user personal finance tool. |
| Web framework | FastAPI | Litestar | Nice alternative, but smaller ecosystem, fewer examples for SSE+LLM patterns, less community support. FastAPI's Pydantic integration is a perfect match for the existing OpenAI function-calling schemas. |
| LLM orchestration | OpenAI SDK direct | LangChain | LangChain adds enormous abstraction layers for what amounts to: call OpenAI with tools, handle the response loop. The project already has the tool schemas. LangChain's complexity buys nothing here and actively obscures the agent loop. |
| LLM orchestration | OpenAI SDK direct | LlamaIndex | Designed for RAG/document indexing, not needed here. The data source is already structured (Firefly III API). |
| Charting | Plotly | Matplotlib | Plotly generates interactive HTML charts that work in a web UI. Matplotlib produces static images only. For a web-first product, Plotly is the right choice. |
| Charting | Plotly | Dash | Dash is an entire dashboard framework (heavy, owns the page). We need charts embedded in our own templates, not a Dash app. |
| SSE | sse-starlette | WebSockets | SSE is unidirectional server→client, which is exactly right for streaming LLM responses. WebSockets add bidirectional complexity we don't need. The browser `EventSource` API is simpler than WS. |
| SSE | sse-starlette | FastAPI built-in SSE | FastAPI added `StreamJSONLines` and SSE docs in recent versions, but the built-in support is less mature than `sse-starlette` (which handles ping, reconnect, cooperative shutdown). Use `sse-starlette` for production-grade SSE. |
| Frontend | Jinja2 + vanilla JS/HTMX | React/Vue SPA | Personal single-user tool. A full SPA framework adds build tooling (webpack/vite), npm ecosystem, and deployment complexity for zero benefit. Jinja2 renders the page shell; vanilla JS handles SSE for chat. Keep it simple. |
| Frontend | Jinja2 + vanilla JS/HTMX | Streamlit | Streamlit abstracts the entire UI but makes custom layouts painful, has poor SSE support, and expects a different execution model (script reruns). Not suitable for a chat-first interface. |

## What NOT to Use

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| LangChain / LangGraph | Massive abstraction over a simple agent loop. The project has 13 tools already defined as Pydantic models — just call `client.chat.completions.create()` with `tools=` and handle the loop. LangChain would add 50+ deps and obscure the control flow. | OpenAI SDK direct with manual agent loop |
|Celery / Redis / message queues | Single-user personal tool. No need for task queues or pub/sub. LLM calls may be slow, but SSE keeps the connection alive. Background tasks (report generation) can use FastAPI's `BackgroundTasks`. | FastAPI `BackgroundTasks` for async work |
| Dash / Streamlit | Both want to own the entire page lifecycle. They're dashboard/data-app frameworks, not suitable for a chat-first web UI with embedded charts. | Jinja2 templates with Plotly chart HTML fragments |
| Flask | Synchronous framework. The entire benefit of FastAPI for this project is async — the LLM call is long-running, and we need SSE streaming. Flask would require workarounds (threading, gevent). | FastAPI |
| Gradio | Designed for ML model demos, not production web apps. Limited customization, auto-generated UI, poor chat streaming support. | FastAPI + Jinja2 |
| SQLite / database layer | Firefly III is the data source. No local DB needed for categorization rules or corrections — store them as JSON/YAML config files, or re-derive from Firefly III tags/categories. | Firefly III API + JSON config files |

## Stack Patterns by Variant

**If prioritizing fast time-to-first-working-chat:**
- Use FastAPI + Jinja2 for the page shell
- Embed a minimal JS `EventSource` listener (no framework)
- Use the existing OpenAI SDK directly — no agent framework
- Start with synchronous agent loop, upgrade to streaming later
- This gets you a working chat in ~200 lines of Python + ~50 lines of JS

**If prioritizing report generation quality:**
- Use Plotly with `fig.to_html(full_html=False, include_plotlyjs='cdn')` to embed interactive charts in Jinja2 templates
- Reports render server-side as HTML pages with embedded chart divs
- Use Kaleido only if PDF/image export is needed later

**If scaling to multiple users (unlikely per scope, but):**
- Add authentication middleware (FastAPI `Depends` + bearer token)
- Store user sessions in a lightweight store
- Consider WebSocket upgrade for bidirectional real-time updates

## Version Compatibility

| Package A | Compatible With | Notes |
|-----------|-----------------|-------|
| fastapi@0.136+ | pydantic@2.x | FastAPI requires Pydantic 2.x (Pydantic 1 not supported) |
| openai@2.34+ | pydantic@2.x | OpenAI SDK uses Pydantic v2 models for responses |
| sse-starlette@3.4+ | fastapi@0.100+ | Requires Starlette-compatible ASGI; works with all modern FastAPI |
| plotly@6.7+ | python@3.8+ | No conflicts with project deps |
| uvicorn@0.46+ | python@3.10+ | Compatible with Python 3.12 |
| pydantic-settings@2.x | pydantic@2.x | Same v2 ecosystem, designed to work together |
| firefly-iii-api-client@6.2.21 | urllib3, pydantic | Uses Pydantic v2 models; confirmed working in existing codebase |

## Sources

- PyPI: FastAPI 0.136.1 (verified Apr 23, 2026) — official PyPI page
- PyPI: OpenAI 2.35.0 (verified May 6, 2026) — official PyPI page
- PyPI: Uvicorn 0.46.0 (verified Apr 23, 2026) — official PyPI page
- PyPI: Plotly 6.7.0 (verified Apr 9, 2026) — official PyPI page
- PyPI: Jinja2 3.1.6 (verified Mar 5, 2025) — official PyPI page
- PyPI: sse-starlette 3.4.2 (verified May 6, 2026) — official PyPI page
- FastAPI official docs: SSE, WebSocket, streaming support verified
- OpenAI Python SDK official docs: `chat.completions.create` with `tools` parameter and `stream=True`
- Existing codebase: `tools.py` (630 lines), `pyproject.toml`, `.planning/codebase/STACK.md`

---
*Stack research for: LLM-powered personal finance analyzer with Firefly III backend*
*Researched: 2026-05-06*