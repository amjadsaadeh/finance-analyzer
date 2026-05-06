# Architecture Research

**Domain:** LLM-powered personal finance analyzer with chat interface
**Researched:** 2026-05-06
**Confidence:** HIGH

## Recommended Architecture

### System Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Presentation Layer                           │
│  ┌─────────────────┐  ┌──────────────────┐  ┌──────────────────┐  │
│  │  Chat UI (HTML)  │  │  REST API Routes  │  │  SSE Endpoint    │  │
│  └────────┬────────┘  └────────┬─────────┘  └────────┬─────────┘  │
├───────────┴─────────────────────┴─────────────────────┴────────────┤
│                        Agent Layer                                  │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │                    Agent Loop (OpenAI)                        │  │
│  │  ┌──────────┐  ┌──────────────┐  ┌────────────────────────┐ │  │
│  │  │ System   │  │ Tool Call    │  │ Response Assembly      │ │  │
│  │  │ Prompt   │  │ Dispatcher   │  │ (structured + narrative)│ │  │
│  │  └──────────┘  └──────┬───────┘  └────────────────────────┘ │  │
│  └────────────────────────┼─────────────────────────────────────┘  │
├───────────────────────────┼────────────────────────────────────────┤
│                     Tool / Logic Layer                              │
│  ┌───────────────┐  ┌──────────────┐  ┌────────────────────────┐  │
│  │ Firefly Tools  │  │ Categorizer  │  │ Report Builder         │  │
│  │ (existing)     │  │ (new)        │  │ (new)                  │  │
│  └───────┬───────┘  └──────┬───────┘  └────────────┬───────────┘  │
├──────────┼──────────────────┼─────────────────────────┼─────────────┤
│                     Data / Client Layer                              │
│  ┌────────────────┐  ┌────────────────┐  ┌─────────────────────┐  │
│  │ FireflyClient   │  │ Category Store │  │ Conversation Store  │  │
│  │ (existing)      │  │ (JSON/SQLite)  │  │ (in-memory/disk)    │  │
│  └────────────────┘  └────────────────┘  └─────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
```

### Component Boundaries

| Component | Responsibility | Communicates With |
|-----------|----------------|-------------------|
| **Chat UI** | Browser-based chat interface; renders messages, tables, charts | REST API (POST /chat), SSE (GET /chat/stream) |
| **REST API Routes** | HTTP endpoints; validates requests, delegates to Agent Loop | Agent Loop, SSE stream |
| **SSE Endpoint** | Streams LLM tokens and tool results to browser in real-time | Agent Loop, Chat UI |
| **Agent Loop** | Orchestrates LLM ↔ tool call cycle; manages conversation state | System Prompt, Tool Call Dispatcher, Response Assembly |
| **System Prompt** | Defines the finance assistant persona, available tools, and response format rules | Agent Loop (read-only) |
| **Tool Call Dispatcher** | Routes LLM tool_calls to correct handler; injects new tools (categorize, report) | Firefly Tools, Categorizer, Report Builder |
| **Firefly Tools** | Existing 13 tools in tools.py; CRUD for transactions, accounts, categories, insights | FireflyClient |
| **Categorizer** | Auto-categorizes transactions using LLM; learns from user corrections | Firefly Tools (read transactions), Category Store |
| **Report Builder** | Generates savings reports with narrative + structured data (tables, trends) | Firefly Tools (insight data), Agent Loop (narrative generation) |
| **FireflyClient** | HTTP client for Firefly III API; holds config + auth (existing) | Firefly III instance |
| **Category Store** | Persists learned categorization rules and corrections | File or SQLite |
| **Conversation Store** | Persists chat history per session for multi-turn conversations | In-memory dict (MVP), upgradeable to SQLite |

## Recommended Project Structure

```
src/
├── main.py                  # FastAPI app factory, lifespan, mount static files
├── agent/
│   ├── __init__.py
│   ├── loop.py              # Agent loop: LLM call → tool_calls → dispatch → repeat
│   ├── prompt.py            # System prompt templates for finance assistant
│   └── dispatcher.py        # Extends tools.dispatch() with new tools
├── categorizer/
│   ├── __init__.py
│   ├── engine.py            # LLM-powered categorization logic
│   ├── rules.py             # Category rule storage and matching
│   └── models.py            # Pydantic schemas for categorization
├── reports/
│   ├── __init__.py
│   ├── builder.py           # Report generation: data gathering + narrative
│   ├── models.py            # Pydantic schemas for report output
│   └── templates.py          # Report format templates
├── api/
│   ├── __init__.py
│   ├── routes.py             # FastAPI routers: /chat, /chat/stream
│   ├── deps.py               # Dependency injection: FireflyClient, OpenAI client
│   └── schemas.py             # Request/response Pydantic models
├── web/
│   ├── index.html             # Chat UI (single-page app)
│   ├── app.js                 # Frontend JS: message rendering, SSE handling
│   └── style.css              # Minimal chat styling
└── tools.py                   # Existing — unchanged or minimally extended
```

### Structure Rationale

- **`agent/`**: The LLM orchestration layer is intellectually distinct from "which HTTP endpoints exist" and "which data gets fetched." Isolating it means the agent loop can be tested without FastAPI.
- **`categorizer/`**: Categorization is a domain feature with its own state (rules, corrections). Its logic is independent of the chat interface — it could also be called from a CLI or API endpoint.
- **`reports/`**: Report building crosses the LLM (narrative) and data (insights) boundaries. Isolating it prevents the agent loop from becoming a god object.
- **`api/`**: FastAPI routes + dependency injection. Keeps HTTP concerns out of business logic.
- **`web/`**: Static files served by FastAPI. No build step — vanilla HTML/JS is sufficient for an MVP chat interface.
- **`tools.py`**: Existing file, largely untouched. New tools (categorize, generate_report) register via the same Pydantic schema → `_HANDLERS` dict pattern.

## Architectural Patterns

### Pattern 1: Agent Loop (LLM Tool-Calling Cycle)

**What:** The core orchestration pattern. Send messages + tools to OpenAI, receive either a text response or tool calls. If tool calls, execute them, feed results back, repeat until text response.

**When to use:** Every chat turn that involves the LLM.

**Trade-offs:** + Simple, well-understood pattern; + Directly maps to OpenAI's API design; - Risk of infinite loops if LLM keeps calling tools (mitigate with max iterations); - Each loop iteration is an API round-trip (latency).

**Example:**
```python
async def run_agent_loop(
    client: OpenAI,
    firefly: FireflyClient,
    messages: list[dict],
    max_iterations: int = 10,
) -> AsyncIterator[str]:
    tools = get_all_tools()
    for _ in range(max_iterations):
        response = await client.chat.completions.create(
            model="gpt-4o",
            messages=messages,
            tools=tools,
            stream=True,
        )
        # ... handle streaming tokens + tool_calls
        # if no tool_calls: break (LLM gave final text answer)
        # if tool_calls: dispatch each, append results, continue loop
```

### Pattern 2: Dispatch Extension (Registry Pattern)

**What:** New domain tools (categorize, generate_report) extend the existing `tools.py` dispatch `_HANDLERS` dict without modifying the core file. A unified dispatcher merges built-in and extension tools.

**When to use:** Whenever adding LLM-callable tools beyond the original 13 Firefly tools.

**Trade-offs:** + Preserves existing tested code; + Clean separation of concerns; - Need a merge point for `get_tools()` return value; - Two dispatch tables to keep in sync (mitigate with a registration function).

**Example:**
```python
# In agent/dispatcher.py
from tools import get_tools as get_firefly_tools, dispatch as firefly_dispatch

_EXTENSION_HANDLERS = {
    "auto_categorize": _handler_auto_categorize,
    "generate_savings_report": _handler_generate_report,
}

def get_all_tools() -> list[dict]:
    return get_firefly_tools() + [pydantic_function_tool(AutoCategorize, name="auto_categorize"), ...]

def dispatch_all(client: FireflyClient, tool_name: str, args: dict) -> dict:
    if tool_name in _EXTENSION_HANDLERS:
        return _EXTENSION_HANDLERS[tool_name](client, args)
    return firefly_dispatch(client, tool_name, args)
```

### Pattern 3: SSE Streaming for Chat

**What:** Use Server-Sent Events (FastAPI `StreamingResponse`) to stream LLM tokens and tool results to the browser in real-time, avoiding full-request blocking.

**When to use:** Chat interface responses. Required for good UX — users expect streaming tokens.

**Trade-offs:** + Simple HTTP-based protocol; + Native browser EventSource API; + FastAPI has first-class support; - Unidirectional (server→client only — sufficient for chat); - No binary data (not needed here).

**Example:**
```python
from fastapi.responses import StreamingResponse
import json

@router.post("/chat/stream")
async def chat_stream(request: ChatRequest):
    async def event_generator():
        async for token in run_agent_loop(...):
            yield f"data: {json.dumps({'type': 'token', 'content': token})}\n\n"
        yield f"data: {json.dumps({'type': 'done'})}\n\n"
    return StreamingResponse(event_generator(), media_type="text/event-stream")
```

### Pattern 4: Category Learning (Correction-Driven Updates)

**What:** When the user corrects a categorization, the system updates a rule store rather than memorizing the exact correction. The categorizer re-evaluates rules on next use, allowing generalized learning.

**When to use:** After any user correction to a suggested category.

**Trade-offs:** + Generalizes from corrections (not brittle memorization); + Simple to implement with JSON/YAML rules; - Rule ordering and conflict resolution can get complex at scale (acceptable for personal single-instance use); - LLM-based categorization has inherent non-determinism.

**Example:**
```python
# In categorizer/rules.py
class CategoryRules:
    def __init__(self, path: Path):
        self.rules: list[CategoryRule] = self._load(path)

    def add_correction(self, description_pattern: str, account_hint: str, correct_category: str):
        """Add or update a rule. Higher-priority rules (from corrections) override defaults."""
        self.rules = [
            r for r in self.rules
            if not (r.description_pattern == description_pattern and r.account_hint == account_hint)
        ]
        self.rules.append(CategoryRule(
            description_pattern=description_pattern,
            account_hint=account_hint,
            category=correct_category,
            source="correction",
            priority=100,
        ))
        self._save()
```

## Data Flow

### Chat Request Flow

```
[User types message in browser]
    ↓
POST /chat/stream (or /chat for non-streaming)
    ↓
[FastAPI route] → creates/loads conversation → builds messages list
    ↓
[Agent Loop] → sends messages + tools to OpenAI API
    ↓
[LLM decides] → text response OR tool_calls
    ↓ (if tool_calls)
[Dispatcher] → routes to handler (Firefly / Categorizer / Report)
    ↓
[Handler] → calls FireflyClient / CategoryRules
    ↓
[Tool result] → appended to messages → back to LLM
    ↓ (repeat until text response)
[LLM final response] → streamed to browser via SSE
    ↓
[Chat UI] → renders markdown, tables, charts
```

### Categorization Flow

```
[Agent Loop] calls auto_categorize tool
    ↓
[Categorizer.engine] → fetches uncategorized transactions via Firefly Tools
    ↓
[Local rules match] → for each transaction, check description/account patterns
    ↓ (if no local rule match)
[LLM categorization] → send transaction details to LLM with category list
    ↓
[Apply categories] → use update_transaction_category tool
    ↓
[Return summary] → count categorized, unmatched, suggestions
```

### Savings Report Flow

```
[Agent Loop] calls generate_savings_report tool
    ↓
[Report Builder] → calls insight tools for date range (3-6 months)
    ↓
[Data assembly] → aggregate category-level data via calculate_net, compare_periods
    ↓
[Narrative generation] → LLM produces written analysis with concrete suggestions
    ↓
[Structured output] → return markdown report + JSON data (for charts/tables)
```

### Key Data Flows

1. **Chat turn:** Browser → FastAPI → Agent Loop → (OpenAI API ↔ Dispatcher ↔ FireflyClient) × N → SSE → Browser
2. **Categorization:** Agent Loop → Categorizer → (Local Rules or LLM) → Firefly Tools (apply category) → Firefly III
3. **Report:** Agent Loop → Report Builder → Firefly Tools (insight data) → LLM (narrative) → Structured response
4. **Learning:** User correction in chat → Agent Loop → Categorizer.add_correction() → Category Store (JSON/YAML file)

## Scaling Considerations

| Scale | Architecture Adjustments |
|-------|--------------------------|
| 1 user (personal) | In-memory conversation store, JSON file for category rules, single-process Uvicorn. This is the MVP target. |
| 10 users | Add SQLite for conversation persistence and category rules. Add basic auth. Still single-process. |
| 100+ users | Externalize session store (Redis or Postgres). Add rate limiting. Consider async Firefly III client. Horizontal scaling behind a load balancer (stateless workers). |

### Scaling Priorities

1. **First bottleneck:** LLM API latency. Each agent loop turn is 1-3 seconds. Streaming (SSE) masks this. For personal use, this is acceptable. Mitigate with prompt caching and reasonable max_iterations limits.
2. **Second bottleneck:** Firefly III API rate limits. The existing handlers make 1-3 API calls per tool invocation. Categorization of many transactions could hit limits. Mitigate with batching and caching.

## Anti-Patterns

### Anti-Pattern 1: God Agent Loop

**What people do:** Put all logic — categorization rules, report formatting, data fetching — inside the system prompt or the agent loop itself.
**Why it's wrong:** The system prompt becomes unmaintainable. The LLM gets confused with too many instructions. Testing becomes impossible.
**Do this instead:** Keep the agent loop as a thin orchestrator. Domain logic (categorization rules, report templates) lives in dedicated modules. The LLM's job is deciding *when* to call tools and synthesizing the response, not implementing business logic.

### Anti-Pattern 2: Blocking Firefly Calls in Async Context

**What people do:** Call Firefly III's synchronous SDK methods directly inside async FastAPI endpoints.
**Why it's wrong:** Blocks the event loop. All other requests stall while Firefly API responds.
**Do this instead:** Wrap synchronous Firefly calls in `asyncio.to_thread()` or run in FastAPI's thread pool via `Depends()`. The existing `firefly_iii_client` SDK is synchronous — it must not block the async event loop.

### Anti-Pattern 3: Storing Full Conversation in Database

**What people do:** Persist every message of every conversation turn permanently.
**Why it's wrong:** LLM conversations grow fast (3-5K tokens per turn with tool results). Storing everything wastes space and makes context window management harder.
**Do this instead:** Keep recent turns in memory for the active session. Use summarization for long conversations. Only persist category corrections and report outputs — not raw chat logs.

### Anti-Pattern 4: Mixing Tool Schemas with System Prompt Logic

**What people do:** Encode tool behavior rules in the system prompt ("Always call list_transactions before categorizing").
**Why it's wrong:** Fragile coupling. When tools change, prompts break silently. The LLM may or may not follow prompt instructions.
**Do this instead:** Let the agent loop handle orchestration logic in Python code (e.g., if categorize is called, auto-fetch transactions first). Keep system prompts focused on persona and output format.

### Anti-Pattern 5: Monolithic Single File for New Features

**What people do:** Keep adding to `tools.py` until it becomes unmanageable.
**Why it's wrong:** The existing `tools.py` is 630 lines for 13 focused handlers. Adding categorization logic, report generation, and the agent loop would push it to 1500+ lines with mixed concerns.
**Do this instead:** Extend through the dispatch extension pattern. New tools register alongside existing ones but live in their own modules. `tools.py` stays unchanged.

## Integration Points

### External Services

| Service | Integration Pattern | Notes |
|---------|---------------------|-------|
| OpenAI API | `openai` Python SDK (already in deps) | Stream=True for chat; function calling with existing `pydantic_function_tool` pattern |
| Firefly III | `firefly_iii_client` SDK (existing) | Synchronous SDK — wrap in `asyncio.to_thread()` for FastAPI |
| LLM (categorization) | OpenAI Chat Completions, separate from main agent | Shallow call: "Given these categories and this transaction, which category fits?" |

### Internal Boundaries

| Boundary | Communication | Notes |
|----------|---------------|-------|
| Chat UI ↔ REST API | HTTP + SSE | JSON request, SSE streaming response |
| REST API ↔ Agent Loop | Direct function call | Agent loop is a Python async function, not a separate service |
| Agent Loop ↔ Tool Dispatcher | Dictionary lookup + function call | Same pattern as existing `dispatch()` |
| Dispatcher ↔ Firefly Tools | Function call | Existing `_handler_*` functions |
| Dispatcher ↔ Categorizer | Function call | New handler calls categorizer engine |
| Dispatcher ↔ Report Builder | Function call | New handler calls report builder |
| Categorizer ↔ Category Store | File I/O (JSON/YAML) | Simple persistence for personal use |
| Agent Loop ↔ Conversation Store | In-memory dict (MVP) | Upgradeable to SQLite |

## Build Order

The following build order follows dependency constraints — each component must exist before components that depend on it can function:

1. **Agent Loop** (no new deps — just `openai` SDK which is already in pyproject.toml)
   - Wire existing `tools.get_tools()` and `tools.dispatch()` into a working LLM tool-call cycle
   - Can be tested in isolation (CLI) before any web layer exists
   - *Rationale:* This is the core innovation. If the agent loop doesn't work, nothing else matters.

2. **FastAPI Web Layer** (adds `fastapi`, `uvicorn`, `sse-starlette`)
   - `/chat` endpoint (non-streaming, simpler to debug)
   - `/chat/stream` SSE endpoint
   - Dependency injection for `FireflyClient` and `OpenAI`
   - *Rationale:* After the agent loop works, you need to expose it via HTTP. Start with non-streaming, then add streaming.

3. **Chat UI** (no new deps — vanilla HTML/CSS/JS)
   - Single `index.html` with EventSource for SSE
   - Message list, input box, basic markdown rendering
   - *Rationale:* Can't test the streaming UX without a UI. Keep it simple — no build step needed.

4. **Categorizer** (no new deps beyond `openai`)
   - LLM-based categorization engine
   - Category rule store (JSON file)
   - New tool `auto_categorize` registered via dispatch extension
   - *Rationale:* Depends on agent loop working (it's a tool the LLM calls). Depends on Firefly tools working (needs transaction data).

5. **Report Builder** (no new deps beyond `openai`)
   - Data assembly from existing insight tools
   - LLM narrative generation
   - New tool `generate_savings_report` registered via dispatch extension
   - *Rationale:* Depends on agent loop + Firefly insight tools. The insight tools already exist and work.

6. **Learning / Corrections** (extends Categorizer)
   - User correction flows in chat
   - Rule update from corrections
   - *Rationale:* Requires working categorizer first, then adds the feedback loop.

## Sources

- OpenAI Function Calling documentation (https://platform.openai.com/docs/guides/function-calling) — HIGH confidence, official source
- OpenAI Structured Outputs documentation (https://platform.openai.com/docs/guides/structured-outputs) — HIGH confidence, official source
- OpenAI Agents SDK overview (https://platform.openai.com/docs/guides/agents) — HIGH confidence, official source
- FastAPI documentation (https://fastapi.tiangolo.com/) — HIGH confidence, official source
- Existing codebase analysis (`tools.py`, `pyproject.toml`, tests) — HIGH confidence, primary source

---
*Architecture research for: LLM-powered personal finance analyzer*
*Researched: 2026-05-06*