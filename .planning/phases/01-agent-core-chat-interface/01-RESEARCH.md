# Phase 1: Agent Core & Chat Interface - Research

**Researched:** 2026-05-06
**Domain:** LLM agent loop, web chat interface, tool-calling, write-safety confirmation
**Confidence:** HIGH

## Summary

Phase 1 requires building an LLM-powered agent loop that routes user questions to existing Firefly III tools via OpenAI function calling, streams responses to a browser via SSE, maintains session-scoped conversation context, translates errors into natural language, and pauses for user confirmation before applying any data modifications. The key architectural decision is whether to use the OpenAI Agents SDK (which provides built-in human-in-the-loop approvals, session management, and tool registration that map directly onto the existing dispatch pattern) or to build a custom agent loop with raw Chat Completions API calls. After research, the Agents SDK is the recommended approach — its `needs_approval` flag on function tools maps directly to the SAFE-01/SAFE-02 confirmation requirement, its `Runner` manages the agent loop including multi-turn tool calls, and its session support handles CHAT-03. The alternative (custom loop with raw OpenAI SDK) gives more control but requires reimplementing the agent loop, approval pausing, and streaming plumbing that the Agents SDK already provides.

For the web layer, FastAPI with sse-starlette is the standard Python SSE implementation. It's well-maintained (v3.4.2, May 2026), production-stable, and integrates naturally with FastAPI's async model. The frontend can be a minimal HTML+JS page using the `EventSource` browser API — no build tooling required for Phase 1.

**Primary recommendation:** Use OpenAI Agents SDK for the agent loop (with `needs_approval` for write tools) + FastAPI + sse-starlette for the web/SSE layer, wrapping the existing `tools.py` dispatch system as Agents SDK function tools.

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| CHAT-01 | User can interact via web-based chat interface served by FastAPI | FastAPI serves REST endpoints; simple HTML+JS frontend using EventSource API; sse-starlette provides SSE streaming |
| CHAT-02 | Chat displays LLM responses in real-time via SSE streaming | Agents SDK `Runner.run_streamed()` yields typed SSE events; sse-starlette `EventSourceResponse` bridges to browser; event types include `response.output_text.delta`, `response.function_call_arguments.delta` |
| CHAT-03 | Chat maintains session-scoped conversation context | Agents SDK `Session` class wraps conversation history; in-memory dict keyed by session ID for Phase 1; context window managed by passing messages list on each turn |
| CHAT-04 | Chat gracefully handles errors — natural language explanations, not stack traces | Agents SDK tool errors propagate as function call outputs; system prompt instructs LLM to translate error dicts into natural language; agent-level error handling catches API failures |
| TOOL-01 | LLM routes natural language questions to existing Firefly III tools | Agents SDK `function_tool` decorator registers Python functions as LLM-callable tools; maps 1:1 onto existing `_handler_*` functions via `dispatch()` |
| TOOL-02 | LLM answers spending questions with real transaction data | Read-only tools (`list_transactions`, `get_expense_insights`, etc.) called by LLM; system prompt enforces "answer from data, never calculate" |
| TOOL-03 | LLM identifies unnecessary or anomalous spending when asked | LLM uses `get_expense_insights`, `compare_periods`, `list_transactions` tools in combination; system prompt guides reasoning about anomalies |
| TOOL-04 | All numeric results come from tool calls, never from LLM calculation | System prompt rule: "always use `sum_transactions`, `calculate_net`, or `compare_periods` for any arithmetic; never calculate yourself"; `SumTransactions` tool enforces Decimal precision |
| SAFE-01 | All financial data modifications require explicit user confirmation | Agents SDK `@function_tool(needs_approval=True)` on write handlers (`update_transaction_tags`, `update_transaction_category`); runner pauses and yields `interruptions`; frontend shows preview and collects confirm/reject |
| SAFE-02 | System previews proposed changes before confirmation | When `needs_approval` tool is called, agent loop returns the tool call arguments as a preview; frontend renders "I'll categorize transaction X as Groceries. Confirm?"; user responds; `state.approve()` or `state.reject()` to continue |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| openai-agents | 0.15.3 | Agent loop, tool dispatch, human-in-the-loop, sessions | Official OpenAI SDK; built-in approval flow for SAFE-01/SAFE-02; manages conversation context; streaming support; maps directly onto existing tool pattern |
| fastapi | >=0.115 | Web framework, REST endpoints, ASGI | De-facto standard Python async web framework; ASGI-native; integrates with sse-starlette; Pydantic request/response models |
| sse-starlette | >=2.0 | Server-Sent Events for Starlette/FastAPI | Production-ready SSE implementation (v3.4.2, May 2026); W3C SSE spec compliant; handles client disconnect, ping/keepalive, cooperative shutdown |
| uvicorn | >=0.30 | ASGI server | Standard production ASGI server for FastAPI; supports graceful shutdown |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| openai | >=2.34 (existing) | Underlying OpenAI API client (dependency of openai-agents) | Already in deps; Agents SDK uses it internally; `pydantic_function_tool` import stays for schema gen |
| pydantic | >=2.0 (existing) | Request/response models, data validation | Already used for tool schemas; FastAPI also uses Pydantic |
| python-multipart | >=0.0.9 | Form data parsing for FastAPI | Only if needed for file uploads (not needed in Phase 1) |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| openai-agents | Custom agent loop with raw Chat Completions API | Custom loop gives more control but requires reimplementing: multi-turn tool call loop, approval pause/resume, streaming event parsing, session management — all of which Agents SDK provides. Agents SDK is officially maintained by OpenAI and uses Chat Completions under the hood. |
| FastAPI | Flask, Django, Starlette bare | Flask is synchronous; Django is overkill; Starlette is what FastAPI wraps, adding Pydantic validation and automatic docs. FastAPI is the standard choice. |
| sse-starlette | Websockets (via FastAPI) | SSE is simpler, works over HTTP/1.1, auto-reconnects, firewall-friendly, unidirectional (which matches our chat: server→client streaming). WebSockets add complexity for bidirectional we don't need. |
| openai-agents Sessions | Manual conversation dict | Manual dict is simpler for Phase 1 but misses token counting, truncation, and serialization that Sessions provide. Agents SDK Sessions handle the full lifecycle. |

**Installation:**
```bash
uv add openai-agents fastapi sse-starlette uvicorn
```

## Architecture Patterns

### Recommended Project Structure
```
src/
├── agent.py           # Agent definition, system prompt, tool registration
├── chat.py            # Chat endpoint (FastAPI routes, SSE streaming, session mgmt)
├── approval.py        # Approval flow: preview rendering, confirm/reject logic
├── models.py          # Pydantic models for API requests/responses
└── static/
    └── index.html     # Minimal chat UI (EventSource + fetch)
tools.py               # Existing: FireflyClient, 13 tools, dispatch (unchanged)
main.py                # Entry point: uvicorn runner
```

### Pattern 1: Agents SDK Function Tool Wrapping
**What:** Wrap existing `dispatch()` pattern as Agents SDK function tools
**When to use:** Every Firefly III tool that the LLM can call
**Example:**
```python
# Source: OpenAI Agents SDK docs - https://platform.openai.com/docs/guides/agents
from agents import Agent, Runner, function_tool
from tools import FireflyClient, dispatch

# Read tools - no approval needed
@function_tool
async def list_transactions(limit: int = 50, page: int = 1) -> str:
    """List transactions from Firefly III. Results are paginated."""
    client = get_firefly_client()  # from app state
    result = dispatch(client, "list_transactions", {"limit": limit, "page": page})
    return json.dumps(result)

# Write tools - require approval (SAFE-01/SAFE-02)
@function_tool(needs_approval=True)
async def update_transaction_category(transaction_id: str, category_name: str) -> str:
    """Set the category on a transaction. REQUIRES USER CONFIRMATION."""
    client = get_firefly_client()
    result = dispatch(client, "update_transaction_category", {
        "transaction_id": transaction_id,
        "category_name": category_name,
    })
    return json.dumps(result)

finance_agent = Agent(
    name="Finance Assistant",
    instructions=SYSTEM_PROMPT,
    tools=[list_transactions, update_transaction_category, ...],
)
```

### Pattern 2: Agent Loop with Approval Pause (SAFE-01/SAFE-02)
**What:** When LLM calls a write tool, the runner pauses and returns `interruptions`
**When to use:** Every write operation (tag updates, category changes)
**Example:**
```python
# Source: OpenAI Agents SDK guardrails docs
from agents import Runner

result = await Runner.run(finance_agent, user_message, context=session_context)

if result.interruptions:
    # Return preview to frontend
    preview = format_approval_preview(result.interruptions)
    # Serialize state for later resumption
    state = result.to_state()
    return {"type": "approval_needed", "preview": preview, "state_id": store(state)}

# After user confirms:
state = load(state_id)
for interruption in result.interruptions:
    state.approve(interruption)  # or state.reject(interruption)
result = await Runner.run(finance_agent, state=state, context=session_context)
```

### Pattern 3: SSE Streaming from Agent Loop (CHAT-02)
**What:** Bridge Agents SDK streaming events to browser via SSE
**When to use:** Every chat response
**Example:**
```python
# Source: sse-starlette docs + OpenAI Agents SDK streaming
from sse_starlette import EventSourceResponse
from agents import Runner

async def stream_agent_response(request, message: str, session_id: str):
    async def event_generator():
        result = Runner.run_streamed(finance_agent, message, context=get_session(session_id))
        async for event in result.stream_events():
            if event.type == "response.output_text.delta":
                yield {"event": "text_delta", "data": json.dumps({"text": event.delta})}
            elif event.type == "response.function_call_arguments.done":
                yield {"event": "tool_call", "data": json.dumps({"name": event.name, "args": event.arguments})}
            elif event.type == "response.completed":
                yield {"event": "done", "data": "{}"}
    return EventSourceResponse(event_generator())
```

### Pattern 4: Session Management (CHAT-03)
**What:** In-memory session store mapping session IDs to conversation history
**When to use:** Every conversation turn
**Example:**
```python
from agents import SQLiteSession  # or use in-memory dict for Phase 1

# In-memory session store (Phase 1); upgrade to Redis/SQLite later
_sessions: dict[str, list] = {}

async def get_or_create_session(session_id: str) -> list:
    if session_id not in _sessions:
        _sessions[session_id] = []
    return _sessions[session_id]
```

### Pattern 5: Error-to-Natural-Language Translation (CHAT-04)
**What:** When tool handlers return `{"error": "..."}`, the LLM translates it into natural language
**When to use:** Every tool result that contains an error key
**Example:**
```python
# System prompt instruction:
# "When a tool returns an 'error' key, explain what went wrong in plain language.
#  Never show raw error messages, API codes, or stack traces to the user."

# The dispatch() function already returns {"error": "..."} dicts.
# The LLM receives these as tool call results and translates them.
# Example: {"error": "Missing required argument: 'start_date'"}
#   → "I need a start date to search for transactions. Could you tell me the date range?"
```

### Anti-Patterns to Avoid
- **Don't hand-roll the agent loop** — Agents SDK manages the call→result→continue cycle, streaming, and approval pausing. Building this manually introduces subtle bugs (infinite loops, missing tool results, wrong message ordering).
- **Don't modify tools.py dispatch signature** — The existing `dispatch(client, tool_name, args) -> dict` pattern must remain unchanged. Wrap it with Agents SDK `@function_tool` functions rather than refactoring the dispatch table.
- **Don't use WebSockets for chat streaming** — SSE is simpler, auto-reconnects, and is the right tool for server→client streaming. WebSockets add bidirectional complexity we don't need.
- **Don't let the LLM calculate numbers** — TOOL-04 requires all numbers come from tool calls. The system prompt must explicitly forbid arithmetic and require use of `sum_transactions`, `calculate_net`, `compare_periods`.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Agent tool-call loop | Custom while loop calling Chat Completions API, parsing tool_calls, feeding results back | Agents SDK `Runner.run()` or `Runner.run_streamed()` | Handles multi-turn tool calls, parallel calls, streaming, and approval interruptions correctly |
| Write-operation confirmation | Custom "ask user" prompt engineering, two-step API calls with state encoded in messages | Agents SDK `@function_tool(needs_approval=True)` + `state.approve()` / `state.reject()` | Built-in pause/resume with serialized state; handles edge cases like multiple write calls in one turn |
| SSE streaming | Custom asyncio generator with manual SSE formatting | sse-starlette `EventSourceResponse` | Handles ping/keepalive, client disconnect detection, connection lifecycle, and cooperative shutdown |
| Conversation history | Manual message list management, ad-hoc truncation | Agents SDK `Session` class or `previous_response_id` | Handles message formatting, token counting, serialization, and context window management |
| Error translation | Custom try/except wrapper that transforms API errors | System prompt instruction + existing `{"error": "..."}` pattern | LLM is better at translating technical errors to natural language; prompt instruction is more maintainable than error mapping code |

**Key insight:** The Agents SDK's `needs_approval` mechanism is the exact mechanism SAFE-01/SAFE-02 require. Hand-rolling this is the #1 source of bugs in agent apps — the pause/resume state machine is subtle (what if the user navigates away? what if multiple tools need approval? what if one approves and another rejects?). The SDK handles all these edge cases.

## Common Pitfalls

### Pitfall 1: Writing Approval State to Messages Instead of Using SDK State
**What goes wrong:** Encoding approval state in conversation messages (e.g., "User confirmed categorization") means the LLM can hallucinate confirmations or the state machine becomes fragile
**Why it happens:** Natural inclination to treat conversation history as the state store
**How to avoid:** Use Agents SDK `state.approve()` / `state.reject()` — this is a separate state object from messages
**Warning signs:** Any code that says "I'll assume you confirmed" or stores approval status in the message list

### Pitfall 2: Forgetting `needs_approval` on Write Tools
**What goes wrong:** A tool that modifies financial data gets called and applied without confirmation
**Why it happens:** New write tools added later without the `needs_approval=True` flag
**How to avoid:** Create a clear rule: any tool that calls `update_transaction_*` handlers MUST have `needs_approval=True`. Add a test that verifies all write tools have this flag.
**Warning signs:** A tool that calls `_handler_update_*` without `needs_approval=True`

### Pitfall 3: SSE Connection Drops Losing Agent State
**What goes wrong:** User's SSE connection drops mid-stream, agent state is lost, user can't resume
**Why it happens:** Agent result stored only in the SSE response, not persisted
**How to avoid:** Persist serialized `state` from `result.to_state()` keyed by session_id in the session store. On reconnect, reload state and resume.
**Warning signs:** No state persistence between requests; session store only holds message history

### Pitfall 4: FireflyClient Thread Safety in Async Context
**What goes wrong:** `FireflyClient`/`ApiClient` is shared across concurrent requests and may not be thread-safe
**Why it happens:** Creating one `FireflyClient` per app startup and sharing it
**How to avoid:** Create one `FireflyClient` per request (or per session) using FastAPI dependency injection. The `ApiClient` from firefly-iii-client is not documented as thread-safe.
**Warning signs:** `FireflyClient` stored in `app.state` and reused across requests without locking

### Pitfall 5: LLM Calculating Numbers Instead of Using Tools (TOOL-04)
**What goes wrong:** LLM answers "You spent about $350 on dining" by estimating from context, not from tool call results
**Why it happens:** LLMs are trained to be helpful and will try to answer directly if tool results are ambiguous or the prompt isn't explicit enough
**How to avoid:** (1) System prompt rule: "NEVER calculate or estimate monetary values. Always use `sum_transactions`, `calculate_net`, or `compare_periods` tools for any arithmetic." (2) Verify in agent output that any dollar amount traces to a tool call result.
**Warning signs:** LLM response contains dollar amounts that don't appear in any tool call result

### Pitfall 6: Streaming Text Before Approval Preview (SAFE-02)
**What goes wrong:** User sees LLM say "I'll categorize this as Groceries" and the text streams to completion, but the approval prompt appears late or separately, confusing the UX
**Why it happens:** Not coordinating the streaming pipeline with the approval pause point
**How to avoid:** When `needs_approval` tool is called, the Agents SDK runner pauses. The SSE stream should emit a special `approval_required` event. Frontend must render the approval UI and wait for user response before continuing the stream.
**Warning signs:** Text streaming continues after a write tool is called, before user confirmation

## Code Examples

### Complete Agent Definition with System Prompt
```python
# Source: OpenAI Agents SDK official docs
from agents import Agent, function_tool

SYSTEM_PROMPT = """You are a personal finance assistant connected to a Firefly III budgeting system.

RULES:
1. NEVER calculate or estimate monetary values yourself. Always use sum_transactions, calculate_net, or compare_periods tools for any arithmetic.
2. When a tool returns an "error" key, explain what went wrong in plain language. Never show raw error messages or API codes.
3. When you want to modify financial data (tags, categories), always present what you plan to change and wait for user confirmation.
4. For date ranges, use YYYY-MM-DD format. "last month" means the previous calendar month.
5. Be concise. Lead with the answer, then show supporting detail if asked.
"""

finance_agent = Agent(
    name="Finance Assistant",
    instructions=SYSTEM_PROMPT,
    tools=[
        list_transactions,
        get_transactions_by_date_range,
        search_transactions,
        update_transaction_tags,      # needs_approval=True
        update_transaction_category,   # needs_approval=True
        list_accounts,
        get_expense_insights,
        get_income_insights,
        list_categories,
        list_tags,
        sum_transactions,
        calculate_net,
        compare_periods,
    ],
)
```

### FastAPI Chat Endpoint with SSE Streaming
```python
# Source: FastAPI + sse-starlette official docs
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from sse_starlette import EventSourceResponse
from agents import Runner

app = FastAPI()

@app.post("/chat")
async def chat_endpoint(request: ChatRequest):
    session = get_or_create_session(request.session_id)
    session.append({"role": "user", "content": request.message})

    async def event_generator():
        try:
            result = Runner.run_streamed(
                finance_agent,
                request.message,
                context=session,
            )
            async for event in result.stream_events():
                if event.type == "response.output_text.delta":
                    yield {"event": "text", "data": json.dumps({"content": event.delta})}
                elif event.type == "response.function_call_arguments.done":
                    yield {"event": "tool_call", "data": json.dumps({
                        "name": event.name,
                        "arguments": json.loads(event.arguments),
                    })}
                elif event.type == "response.completed":
                    # Check for approval interruptions
                    if result.interruptions:
                        preview = format_preview(result.interruptions)
                        state_id = store_state(result.to_state())
                        yield {"event": "approval_needed", "data": json.dumps({
                            "preview": preview,
                            "state_id": state_id,
                        })}
                    else:
                        session.append({"role": "assistant", "content": result.final_output})
                        yield {"event": "done", "data": "{}"}
        except Exception as e:
            yield {"event": "error", "data": json.dumps({"message": str(e)})}

    return EventSourceResponse(event_generator())

@app.post("/chat/approve")
async def approve_endpoint(request: ApproveRequest):
    state = load_state(request.state_id)
    if request.approved:
        for interruption in state.interruptions:
            state.approve(interruption)
    else:
        for interruption in state.interruptions:
            state.reject(interruption)
    result = await Runner.run(finance_agent, state=state)
    return {"response": result.final_output}
```

### Minimal Frontend (HTML + JS)
```html
<!-- Source: MDN EventSource + sse-starlette -->
<!DOCTYPE html>
<html>
<head><title>Finance Analyzer</title></head>
<body>
  <div id="chat"></div>
  <input id="msg" placeholder="Ask about your spending...">
  <div id="approval" style="display:none">
    <p id="preview"></p>
    <button onclick="respond(true)">Confirm</button>
    <button onclick="respond(false)">Cancel</button>
  </div>
  <script>
    const sessionId = crypto.randomUUID();
    let pendingStateId = null;

    function send(message) {
      const es = new EventSource(`/chat/stream?session_id=${sessionId}&message=${encodeURIComponent(message)}`);
      es.addEventListener("text", e => {
        document.getElementById("chat").innerHTML += JSON.parse(e.data).content;
      });
      es.addEventListener("approval_needed", e => {
        const data = JSON.parse(e.data);
        pendingStateId = data.state_id;
        document.getElementById("preview").textContent = data.preview;
        document.getElementById("approval").style.display = "block";
        es.close();
      });
      es.addEventListener("done", e => es.close());
    }

    async function respond(approved) {
      await fetch("/chat/approve", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({state_id: pendingStateId, approved}),
      });
      document.getElementById("approval").style.display = "none";
    }
  </script>
</body>
</html>
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| OpenAI Assistants API | Agents SDK (since Feb 2025) | Assistants API deprecated 2025 | New agents should use Agents SDK, not Assistants |
| Custom agent loop with Chat Completions | Agents SDK `Runner.run()` with built-in tool loop | Agents SDK v0.1.0 (Jun 2025) | No need to hand-roll the while loop for multi-turn tool calls |
| Starlette manual SSE | sse-starlette library | v1.0 (Jul 2022), v3.0 (Jul 2025) | Production-stable with cooperative shutdown, ping, disconnect detection |
| OpenAI Chat Completions API only | Responses API + Chat Completions API (both supported) | Responses API Mar 2025 | Agents SDK supports both; Chat Completions recommended for compatibility with existing `pydantic_function_tool` schemas |
| Manual approval flow engineering | `needs_approval=True` on agents SDK function tools | Agents SDK v0.10+ (Feb 2025) | Built-in pause/resume state management for human-in-the-loop |

**Deprecated/outdated:**
- OpenAI Assistants API: Deprecated in favor of Agents SDK + Responses API
- Manual `while True` agent loops: Agents SDK `Runner` handles the full loop including streaming, approvals, and multi-turn tool calls

## Open Questions

1. **Agents SDK with Chat Completions vs Responses API**
   - What we know: Agents SDK supports both model providers. The existing `pydantic_function_tool` generates Chat Completions-style schemas. The Responses API has built-in conversation state (`previous_response_id`).
   - What's unclear: Whether `pydantic_function_tool` output is directly compatible with Agents SDK function tools, or if we need to rewrite the schemas.
   - Recommendation: Use Chat Completions model provider in Agents SDK. Rewrite tool registration as `@function_tool` decorated functions (wrapping existing `dispatch()`), not the raw `pydantic_function_tool` schemas. This is cleaner and idiomatic for the SDK.

2. **State persistence for approval pauses across SSE connections**
   - What we know: Agents SDK `result.to_state()` returns serializable state. SSE connections can drop.
   - What's unclear: How long state should persist; what timeout to use for pending approvals.
   - Recommendation: For Phase 1, use in-memory dict with a 10-minute TTL. Serialize state with `pickle` or `json`. Upgrade to Redis/database in Phase 2+.

3. **Session cleanup and memory limits**
   - What we know: Conversation history grows with each turn. Firefly III tool results can be large (paginated transaction lists).
   - What's unclear: Whether Agents SDK Sessions handle truncation automatically or if we need to manage token limits manually.
   - Recommendation: Start with in-memory sessions, monitor token usage. Implement message summarization or truncation if context window limits are hit. The Agents SDK may handle this — verify during implementation.

## Sources

### Primary (HIGH confidence)
- OpenAI Agents SDK official docs — https://platform.openai.com/docs/guides/agents (agent definition, function tools, guardrails, approvals, streaming)
- OpenAI Agents SDK guardrails/approvals — https://platform.openai.com/docs/guides/agents/guardrails-approvals (needs_approval, state.approve/reject, interruptions)
- OpenAI Agents SDK GitHub (Python) — https://github.com/openai/openai-agents-python (v0.15.3, May 2026, MIT license, 25.9k stars)
- sse-starlette PyPI — https://pypi.org/project/sse-starlette/ (v3.4.2, May 2026, BSD-3, production-stable)
- OpenAI function calling docs — https://platform.openai.com/docs/guides/function-calling (tool calling flow, pydantic_function_tool)
- OpenAI streaming docs — https://platform.openai.com/docs/guides/streaming-responses (SSE event types, streaming patterns)

### Secondary (MEDIUM confidence)
- FastAPI documentation — https://fastapi.tiangolo.com/ (standard Python async web framework)
- OpenAI Responses API migration guide — https://platform.openai.com/docs/guides/migrate-to-responses (Chat Completions → Responses API differences)
- Existing codebase: `tools.py` dispatch pattern, `FireflyClient`, error handling `{"error": "..."}`

### Tertiary (LOW confidence - needs validation during implementation)
- Agents SDK `Session` class behavior with Chat Completions provider — verify during implementation
- Exact SSE event types emitted by `Runner.run_streamed()` — verify during implementation
- Token/context window limits with 13 tools registered — test during implementation

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — Agents SDK, FastAPI, sse-starlette are all mature, well-documented, and directly address the requirements
- Architecture: HIGH — patterns are well-established; the key insight is that Agents SDK `needs_approval` maps directly to SAFE-01/SAFE-02
- Pitfalls: HIGH — based on official docs, known issues with agent loops, and the existing codebase's error pattern

**Research date:** 2026-05-06
**Valid until:** 2026-06-06 (30 days — Agents SDK is actively developed with frequent releases)