# Project Research Summary

**Project:** Finance Analyzer
**Domain:** LLM-powered personal finance analyzer (Firefly III backend)
**Researched:** 2026-05-06
**Confidence:** HIGH

## Executive Summary

Finance Analyzer is an LLM-first personal finance tool that turns raw Firefly III transaction data into actionable insight through natural conversation. Experts build这类 tools with a thin agent loop orchestrating tool calls — not with heavyweight frameworks like LangChain. The product's differentiator is that the LLM is the primary interface (chat-first, not dashboard-first), and its intelligence comes from directing existing tools, not from complex orchestration code. The recommended approach is FastAPI + SSE streaming for the web layer, OpenAI SDK direct for the agent loop (no framework), and vanilla JS for the chat UI — keeping the stack minimal and the control flow explicit.

The primary risks are: (1) LLM tool-use reliability — with 13+ tools, the model will confuse arguments, call wrong tools, or hallucinate IDs unless tool descriptions are meticulously crafted; (2) data integrity — the existing write handlers are fire-and-forget, so the LLM could silently corrupt financial data without human confirmation; (3) narrative accuracy — LLMs generate confident but fabricated numbers, so all financial calculations must come from tools, never from the LLM's "reasoning." Mitigation: invest heavily in tool descriptions, implement a pending-changes confirmation pattern before writes, and enforce that all numbers in reports are verbatim from tool results.

## Key Findings

### Recommended Stack

The stack is intentionally minimal: FastAPI for async web serving (essential for SSE streaming of LLM responses), OpenAI Python SDK direct for the agent loop (LangChain adds abstraction far beyond what the simple call-tool-respond cycle requires), Pydantic for schemas (already in use), and Jinja2 + vanilla JS for the chat UI (no SPA framework needed for a single-user personal tool). Plotly is included for interactive charts in savings reports only. The synchronous Firefly III SDK must be wrapped in `asyncio.to_thread()` to avoid blocking the async event loop.

**Core technologies:**
- **Python 3.12** — runtime; existing codebase constraint
- **FastAPI 0.136+** — web framework; async-first, Pydantic-native, built-in SSE support matches the streaming chat use case exactly
- **OpenAI Python SDK 2.34+** — LLM integration; already a dependency, function-calling API is the core mechanism, no agent framework needed
- **sse-starlette 3.4+** — SSE streaming; battle-tested for production streaming with ping/reconnect/cooperative shutdown
- **Plotly 6.7+** — interactive charts for savings reports; renders to embeddable HTML fragments
- **Jinja2** — server-rendered templates for the chat page shell and report pages
- **pydantic-settings** — centralized config for API keys and settings, cleaner than scattered `os.environ` calls

### Expected Features

**Must have (table stakes) — v1:**
- Natural language spending Q&A — core promise; routes user questions to existing Firefly tools
- Auto-categorization of unc categorized transactions — every competitor does this; LLM classifies by description + amount + account
- Spending breakdowns and period comparisons in plain English — wrapping existing `get_expense_insights`, `calculate_net`, `compare_periods`
- Session-scoped conversation context — follow-up questions like "what about last month?" require remembering what was discussed
- Error handling in natural language — translate `{"error": "..."}` handler responses into human explanations

**Should have (differentiators) — v1.x:**
- Learning from corrections — re-evaluate categorization patterns, not memorize single corrections (explicit PROJECT.md requirement)
- Narrative savings reports — written analysis + data charts; the differentiator over dashboard-only apps
- Actionable suggestions — "Consider capping dining at $200/mo" backed by actual spending data
- Proactive anomaly flagging — "Your utilities were 3x the 6-month average" surfaced without being asked

**Defer (v2+):**
- Unnecessary spending identification — subjective, needs careful framing to avoid giving financial advice
- Spending category suggestions — "You might want a 'Home Office' category"
- Recurring expense detection and highlighting
- PDF/image report export

### Architecture Approach

Four-layer architecture: Presentation (Chat UI + REST + SSE) → Agent (Loop + Prompt + Dispatcher) → Tool/Logic (Firefly Tools + Categorizer + Report Builder) → Data/Client (FireflyClient + Category Store + Conversation Store). The agent loop is a thin orchestrator — it sends messages + tools to OpenAI, dispatches any tool calls, feeds results back, and repeats until a text response. New domain tools extend the existing `_HANDLERS` dict through a dispatch extension pattern without modifying `tools.py`.

**Major components:**
1. **Agent Loop** — orchestrates LLM ↔ tool call cycle; thin, no business logic, max iteration safety limit
2. **Tool Dispatch Extension** — merges existing 13 Firefly tools with new categorize/report tools via registry pattern
3. **SSE Streaming Layer** — streams LLM tokens and tool results to browser in real-time via `sse-starlette`
4. **Categorizer** — LLM-powered categorization engine with rule store; learns from corrections without memorizing
5. **Report Builder** — assembles multi-month data from insight tools, generates LLM narrative with data-backed claims

### Critical Pitfalls

1. **LLM hallucinating tool arguments** — With 13+ tools sharing similar parameter shapes, the model will confuse arguments. Mitigate with exhaustive tool descriptions (when to use, when NOT to use, example inputs), poka-yoke schema design (date range objects, not loose strings), and validation of LLM outputs before dispatch.
2. **Writes without human confirmation** — Existing write handlers are fire-and-forget. The LLM must not directly call `update_transaction_category` etc. without user confirmation. Implement a pending-changes pattern: propose → user confirms → execute.
3. **Stale or contradictory context in multi-turn conversations** — LLM re-fetches data it already retrieved, giving different numbers. Implement context budgeting, cache tool results with timestamps, and separate "data from tools" from "LLM inferences" in context.
4. **Narrative reports with fabricated numbers** — LLMs calculate poorly and fabricate confidently. Never let the LLM do arithmetic; all numbers must come verbatim from tool results. Prohibit causal claims without data backing.
5. **Unbounded tool-call loops** — LLM calls tools indefinitely trying to "fully answer." Enforce max 5-8 tool calls per turn, include pagination metadata in responses, and design prompts to discourage exhaustive retrieval.

## Implications for Roadmap

Based on research, suggested phase structure:

### Phase 1: Agent Core & Chat Interface
**Rationale:** The agent loop is the foundational innovation. If the LLM ↔ tool dispatch cycle doesn't work reliably, nothing else matters. Tool descriptions, the confirmation pattern, and the adapter layer must be established before building features on top.
**Delivers:** Working chat where users can ask finance questions and get accurate, tool-backed answers streamed via SSE.
**Addresses:** NL Q&A, spending breakdowns, period comparisons, transaction filtering, conversation context, error handling in NL
**Avoids:** Hallucinated tool arguments (invest in descriptions), writes without confirmation (build adapter with pending-changes), unbounded loops (enforce iteration limit), tight coupling (establish adapter layer from day one), stale context (implement context budgeting)
**Key new dependencies:** fastapi, uvicorn, sse-starlette, pydantic-settings

### Phase 2: Auto-Categorization & Learning
**Rationale:** Categorization depends on the agent loop working — it's a tool the LLM calls. Building it second means the dispatch pattern is proven and the confirmation flow exists for write operations.
**Delivers:** LLM-powered auto-categorization of uncategorized transactions, with a learning-from-corrections system that re-evaluates rather than memorizes.
**Addresses:** Auto-categorization, learning from corrections
**Avoids:** Memorized corrections (use few-shot prompt context + rule store, not rigid overrides), LLM inventing category names (fetch valid categories from Firefly III at session start)
**Key design challenge:** How to distinguish specific override vs. pattern generalization — cannot use simple rule-matching; need LLM re-evaluation with correction history as context

### Phase 3: Narrative Savings Reports
**Rationale:** Reports require multi-month data aggregation (calling insight tools repeatedly), which depends on stable tool dispatch. They also require the "numbers must come from tools, not LLM calculation" discipline established in Phase 1.
**Delivers:** 3-6 month savings reports with narrative analysis, trend data, and actionable suggestions backed by real numbers.
**Addresses:** Narrative savings reports, actionable suggestions, net worth/cash flow narrative, trend analysis
**Avoids:** Narrative-data confusion (enforce tool-sourced numbers only, add source attribution), expensive report generation (pre-compute aggregates, offer date-range presets)

### Phase 4: Proactive Insights & Polish
**Rationale:** Anomaly flagging and category suggestions are lower-priority features that enhance an already-working product. They don't introduce new architectural patterns — they reuse the agent loop and tool layer.
**Delivers:** Proactive anomaly detection, spending category suggestions for uncategorized transaction patterns, UI polish, any v1.x refinements.
**Addresses:** Proactive anomaly flagging, category suggestions

### Phase Ordering Rationale

- **Phase 1 must come first** because the agent loop, tool descriptions, and confirmation pattern are foundational — every subsequent feature depends on LLM ↔ tool communication working reliably
- **Categorization before reports** because reports need multi-period data which requires the agent loop to handle tool-call chaining correctly (tested and validated in Phase 1); categorization is simpler and validates the dispatch extension pattern
- **Reports before insights** because anomaly detection needs stable insight tool data access, which is validated through report generation
- **Architecture is established in Phase 1** — the adapter layer, dispatch extension pattern, and confirmation flow must exist before features are built on top; retrofitting them is expensive (per PITFALLS: "impossible to retrofit meaningfully" for security)

### Research Flags

Phases likely needing deeper research during planning:
- **Phase 2 (Auto-Categorization & Learning):** The "re-evaluate, don't memorize" pattern is a core PROJECT.md requirement but has no well-documented reference implementation. The research identified it as a design challenge, not a solved problem. Needs `/gsd-research-phase` for LLM categorization prompt engineering, correction pattern storage, and the specific prompt structure for few-shot correction context.
- **Phase 3 (Narrative Reports):** Report format, chart embedding strategy, and the "numbers only from tools" enforcement mechanism need detailed design. The Plotly integration for embedded charts in SSE-streamed responses needs prototyping.

Phases with standard patterns (skip research-phase):
- **Phase 1 (Agent Core):** OpenAI function-calling agent loop is well-documented; FastAPI + SSE streaming is a standard pattern; the existing `tools.py` dispatch mechanism is proven in the codebase.
- **Phase 4 (Proactive Insights):** Statistical anomaly detection (z-score on monthly averages) is straightforward; category suggestions are a simpler variant of the categorization engine.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | All packages verified on PyPI with latest versions; no version conflicts; stack is minimal and well-established; existing codebase constraints respected |
| Features | MEDIUM | Based on competitor analysis and project requirements, not direct user research; prioritization is sound but "learning from corrections" and "unnecessary spending identification" are notoriously hard to implement well — may need scope reduction |
| Architecture | HIGH | Agent loop pattern is well-documented by OpenAI; architecture follows from single-responsibility principle and avoids known anti-patterns; build order follows dependency constraints |
| Pitfalls | MEDIUM | Based on domain analysis and known LLM tool-use failure modes, not production incident reports; some mitigations (context budgeting, correction re-evaluation) will need iteration to get right |

**Overall confidence:** HIGH

### Gaps to Address

- **Confirmation UX pattern:** Research identified the need for pending-changes confirmation before writes, but didn't specify the exact UX flow (inline chat buttons? separate confirmation step? batch-then-confirm?). Needs design during Phase 1 planning.
- **Context window budgeting strategy:** The principle is clear (keep tool results, summarize pleasantries) but the specific algorithm for what to keep/drop and when to summarize needs to be determined during implementation. Token counting and summarization approach needs experimentation.
- **Categorization "re-evaluate" vs "memorize" mechanism:** PROJECT.md requires re-evaluation, not memorization. The research identifies few-shot prompt context and rule stores as the approach, but the exact balance between prompt-based and persistent-rule-based categorization needs prototyping. This is the hardest unsolved design challenge.
- **SSE + Plotly integration:** Streaming an LLM narrative while also delivering interactive charts requires a specific protocol for how chart data is sent alongside text tokens. Needs prototyping in Phase 3.
- **Firefly III SDK async wrapping:** The `firefly_iii_client` SDK is synchronous. The `asyncio.to_thread()` pattern is established, but exact integration with FastAPI dependency injection needs to be worked out during Phase 1.

## Sources

### Primary (HIGH confidence)
- OpenAI Function Calling documentation — tool schema design, streaming, agent loop patterns
- FastAPI official documentation — SSE, dependency injection, async patterns
- Existing codebase (`tools.py`, `pyproject.toml`, tests) — current handler patterns, existing dispatch mechanism, test approach
- PyPI version verification — all recommended packages verified with current versions

### Secondary (MEDIUM confidence)
- Anthropic "Building Effective Agents" research — ACI principles, tool design guidance, human-in-the-loop patterns
- Competitor feature analysis (Monarch Money, Copilot Money, Lunch Money) — feature expectations and differentiation opportunities; medium confidence (product websites, no independent verification)
- Firefly III documentation — base platform capabilities, rules engine, API patterns

### Tertiary (LOW confidence)
- Production LLM tool-use failure mode patterns — inferred from domain knowledge and documentation, not from incident reports; specific failure rates and edge cases will need validation during implementation
- LLM categorization accuracy expectations — no benchmark data for this specific domain (personal finance transaction categorization via LLM); accuracy will need real-world testing

---
*Research completed: 2026-05-06*
*Ready for roadmap: yes*