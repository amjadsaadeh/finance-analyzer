# Pitfalls Research

**Domain:** LLM-powered personal finance analyzer (Firefly III API tool layer + chat/categorization/reports)
**Researched:** 2026-05-06
**Confidence:** MEDIUM (domain patterns from Anthropic research + codebase analysis; finance-LLM specifics from codebase inspection and known tool-use failure modes)

## Critical Pitfalls

### Pitfall 1: LLM Hallucinating Tool Arguments or Calling Wrong Tool

**What goes wrong:**
The LLM calls a tool with plausible-but-wrong parameters — e.g., passing a category name that doesn't exist in Firefly III, mixing up `start_date`/`end_date` order, calling `update_transaction_tags` when the user only asked to view tags, or inventing a `transaction_id` that never existed. With 13 tools, many sharing similar parameter shapes (dates, limits, pages, account_ids), the model confuses which tool to call and with which arguments.

**Why it happens:**
Function-calling models select tools and fill arguments based on schema descriptions alone. When tool names and parameter names are ambiguous or similar (e.g., `get_expense_insights` vs `get_income_insights` differ only in name, not parameter shape), the model has insufficient signal to choose correctly. The existing `tools.py` schemas use brief docstrings and generic `Field` descriptions — not enough discriminative context.

**How to avoid:**
1. Invest heavily in tool descriptions — treat them as prompt engineering for a junior developer (per Anthropic's ACI guidance). Each tool description should include: what it does, when to use it, when *not* to use it, example inputs, and edge cases.
2. Add `enum` constraints where possible (e.g., `account_type` should list valid values: `asset`, `expense`, `revenue`, `liability`).
3. Use poka-yoke: make wrong calls structurally impossible. E.g., require date ranges as a single object rather than two loose strings that can be swapped.
4. Validate LLM outputs against the actual Firefly III state before executing writes (category exists? transaction exists?).

**Warning signs:**
- LLM calls `update_transaction_tags` when user asked "show me my tags"
- LLM invents transaction IDs instead of calling `list_transactions` first
- LLM swaps `start_date` and `end_date`
- LLM calls `get_income_insights` when user asked about expenses

**Phase to address:**
Phase 1 (LLM integration layer) — tool descriptions are the foundation everything else builds on. Get them wrong and every conversation fails.

---

### Pitfall 2: LLM Modifying Financial Data Without Confirmation

**What goes wrong:**
The LLM directly calls write tools (`update_transaction_tags`, `update_transaction_category`) based on a user's casual request ("that should be Groceries") or its own auto-categorization, and the change is committed immediately with no undo, no confirmation prompt, and no audit trail. A misunderstood request or hallucinated categorization corrupts real financial data.

**Why it happens:**
The existing tool layer's write handlers (`_handler_update_transaction_tags`, `_handler_update_transaction_category`) are fire-and-forget — they perform GET-then-PUT immediately and return the result. There's no confirmation step, no dry-run mode, and no concept of "pending changes." The LLM loop will see the tool result, confirm success, and move on. The user never gets a chance to say "wait, that's wrong."

**How to avoid:**
1. **Never give the LLM direct write access without a human-in-the-loop confirmation step.** Implement a "pending changes" pattern: the LLM proposes a change, the UI presents it to the user, and only after confirmation does the write execute.
2. Add a `--dry-run` or `propose` mode to write tools that returns what *would* change without committing it.
3. For auto-categorization: the LLM should suggest categories, not apply them. The user confirms or corrects before execution.
4. Log all write operations with before/after state so mistakes can be traced and reverted.

**Warning signs:**
- LLM applies a category without showing the user what it will change first
- No "undo" capability in the chat interface
- Auto-categorization runs silently on transaction import
- User says "that wasn't what I meant" after a write tool call

**Phase to address:**
Phase 1 (LLM integration) for the confirmation pattern; Phase 2 (auto-categorization) for the propose-don't-apply discipline.

---

### Pitfall 3: Stale or Missing Context in Multi-Turn Conversations

**What goes wrong:**
The LLM loses track of what it already told the user, re-fetches data it already has, or makes inconsistent statements across turns. Example: in turn 1 the LLM reports "$1,200 spent on dining in March." In turn 3 the user asks "and February?" and the LLM fetches February data but also re-fetches March, giving a different number ($1,180) because new transactions were added between API calls. The user now has contradictory information.

**Why it happens:**
Chat interfaces must manage conversation state: which data was fetched, when it was fetched, and whether it's still valid. The existing codebase has no concept of session state — each `dispatch()` call is stateless. LLMs also have context window limits; summarizing or truncating history drops the data-fetch tool calls whose results the LLM was reasoning about.

**How to avoid:**
1. **Implement a context budget system** that decides what to keep vs. summarize. Tool-call results (financial data) should be kept verbatim; conversational pleasantries can be summarized.
2. **Cache fetched data with timestamps** — when the LLM cites a number, it should be able to say "as of 10:32 AM" or re-fetch to confirm freshness.
3. **Separate "data the LLM knows" from "data the LLM inferred."** Fetched numbers are facts; interpretations ("you're overspending") are opinions. Mark these differently in context.
4. **Design the system prompt to explicitly track what's been fetched and what hasn't**, rather than hoping the model memory is sufficient.

**Warning signs:**
- LLM gives different answers for the same query across turns
- LLM re-fetches data it already retrieved (wasting API calls, introducing inconsistency)
- Context window fills up mid-conversation, causing the LLM to "forget" earlier results
- User says "you just told me X, now you're saying Y"

**Phase to address:**
Phase 1 (chat interface) — context management is foundational to chat UX.

---

### Pitfall 4: Auto-Categorization Memorizing Corrections Instead of Learning From Them

**What goes wrong:**
The system "learns" from user corrections by creating hard rules ("if description contains 'Starbucks', categorize as 'Dining'"), which then break when context changes. Example: user corrects a "Starbucks" transaction from "Groceries" to "Dining." The system creates a rule that all Starbucks = Dining. But the user sometimes buys coffee beans at Starbucks (Groceries) and sometimes buys drinks (Dining). Rigid memorization creates more errors than it fixes.

**Why it happens:**
It's much easier to implement "learning" as rule memorization than genuine context-aware re-evaluation. PROJECT.md explicitly flags this: "Categorization re-evaluates rather than memorizes." But the natural inclination when building an LLM categorizer is to give it a memory of past corrections and let it pattern-match against them. The LLM will eagerly generalize from one or two examples.

**How to avoid:**
1. **Treat corrections as signals for re-evaluation, not as override rules.** When the user corrects a categorization, the system should re-examine the full context (description, amount, date, account, merchant patterns) and adjust its understanding of *why* the correction was made.
2. **Use few-shot examples in the prompt** rather than a permanent rule database. Corrections inform the prompt context for future categorization calls, but each call reconsiders holistically.
3. **Surface confidence levels** — when auto-categorizing, include a confidence score. Low-confidence categorizations should be flagged for user review, not silently applied.
4. **Never auto-apply a categorization that contradicts an explicit correction from the same session** without asking the user.

**Warning signs:**
- Categorization accuracy degrades over time as "learned" rules conflict
- User has to correct the same type of transaction repeatedly
- System creates rigid rules from single data points
- Category suggestions diverge from what a reasonable person would choose

**Phase to address:**
Phase 2 (auto-categorization) — this is the core design challenge for that phase.

---

### Pitfall 5: Exposing Sensitive Financial Data Through Prompt Injection or Context Leakage

**What goes wrong:**
A malicious or accidental prompt causes the LLM to reveal another user's financial data (in a multi-user scenario), or the LLM's context window contains raw transaction data that gets logged, cached, or surfaced in error messages. Even in a single-user scenario, the system prompt + tool results + user messages build a rich financial profile in the LLM's context that could leak through logging, API errors, or prompt-injection attacks.

**Why it happens:**
The current codebase stores `api_token` as a plain attribute on `FireflyClient` (CONCERNS.md flags this). The LLM layer will add new attack surfaces: the system prompt contains user context, tool responses contain raw transaction data, and chat history accumulates financial insights. Any of these can leak through: (a) LLM provider logging/prompt caching, (b) application-level error logging that dumps full contexts, (c) prompt injection that tricks the LLM into revealing data from other sessions, (d) web chat localStorage/sessionStorage.

**How to avoid:**
1. **Never include raw transaction data in the system prompt.** System prompts should contain instructions, not data. Data comes from tool calls.
2. **Sanitize LLM inputs and outputs** — strip PII from logs, never log full tool responses, redact amounts/account names in error messages.
3. **Implement prompt-injection guards** — validate that user messages don't contain instruction-like patterns that could manipulate the LLM into calling write tools or revealing data.
4. **Use the LLM provider's data-handling settings** — opt out of prompt caching/training on API calls containing financial data where possible.
5. **Override `FireflyClient.__repr__`** to redact `api_token` (per CONCERNS.md recommendation).
6. **Enforce HTTPS on `base_url`** (per CONCERNS.md recommendation) — add validation in `FireflyClient.__init__`.

**Warning signs:**
- LLM logs contain raw transaction amounts and descriptions
- Error messages include full API responses with financial data
- Web chat stores unsanitized financial data in localStorage
- API token appears in debug logs or stack traces
- LLM responds to "ignore previous instructions" type prompts

**Phase to address:**
Phase 1 (security from day one) — impossible to retrofit meaningfully.

---

### Pitfall 6: Unbounded LLM Tool-Call Loops (Infinite Looping)

**What goes wrong:**
The LLM enters a loop where it repeatedly calls tools: calls `list_transactions`, gets paginated results, calls again for the next page, gets more results, calls `search_transactions` to find something it missed, calls again with different parameters, etc. Each call hits the Firefly III API, costs tokens, and increases latency. A single user query can trigger 20+ tool calls, costing dollars and tens of seconds.

**Why it happens:**
LLMs don't have inherent stopping criteria. Without explicit loop limits, the model will keep calling tools trying to "fully answer" the user's question. Paginated APIs worsen this — the model wants all results, not just one page. The existing handlers return flat arrays without pagination metadata (CONCERNS.md: "No pagination metadata in responses"), so the LLM can't know if there are more pages without making another call.

**How to avoid:**
1. **Set a hard limit on tool calls per turn** (e.g., max 5-8 calls per user message). After the limit, force the LLM to answer with what it has.
2. **Include pagination metadata in tool responses** (total pages, current page, has_next) so the LLM can make informed decisions about whether to paginate.
3. **Design the system prompt to discourage exhaustive retrieval** — instruct the LLM to work with what it has and ask the user if they want more.
4. **Add cost/latency tracking** and surface it to the user: "This query required 4 API calls."
5. **Consider a multi-step approach** for large data: fetch summary first, then drill down on user request.

**Warning signs:**
- User asks "how much did I spend last month?" and waits 30+ seconds for a response
- Single user query triggers 10+ tool calls
- Token usage per conversation exceeds expected bounds
- LLM keeps fetching pages of transactions instead of using `get_expense_insights` (which aggregates)

**Phase to address:**
Phase 1 (LLM integration layer) — loop limits are a safety requirement, not an optimization.

---

### Pitfall 7: Savings Reports That Confuse Narrative With Data

**What goes wrong:**
The LLM generates a "savings report" that reads beautifully but contains fabricated numbers, misattributes spending trends, or draws causal inferences the data doesn't support. Example: "Your dining spending increased 15% in March, likely due to more social events" — the 15% might be wrong (calculation error from the LLM, not from the tool), and the causal claim has no data backing.

**Why it happens:**
LLMs are fluent narrative generators but unreliable calculators. When asked to "analyze my spending," the model will produce confident-sounding prose that may mix real tool-returned numbers with its own hallucinated figures. The tendency to add causal explanations ("likely due to…") is especially dangerous in finance, where users make real decisions based on these claims.

**How to avoid:**
1. **Never let the LLM calculate numbers.** Use the existing computation tools (`sum_transactions`, `calculate_net`, `compare_periods`) for all arithmetic. The LLM should only present numbers that came verbatim from tool results.
2. **Separate the report into structured data (tables/charts) and narrative (prose).** The structured data comes from tools; only the narrative is LLM-generated. Make this distinction visible to the user.
3. **Prohibit causal claims without explicit user direction.** The system prompt should instruct: "Report what the data shows. Do not speculate about causes unless the user asks."
4. **Add source attribution** — every number in the report should be traceable to a specific tool call. "Spending increased 12% (source: compare_periods call, March vs February)."
5. **Round aggressively** — present "$1,234.56" not "$1,234.5600000000001" (the `Decimal` precision in the codebase can produce ugly output).

**Warning signs:**
- Report numbers don't match the tool results
- LLM produces dollar amounts that can't be verified against any tool call
- Report includes causal claims ("because you…") without citation
- User makes financial decisions based on LLM narrative, then discovers the numbers were wrong

**Phase to address:**
Phase 2 (savings reports) — this is the core design challenge for that phase.

---

### Pitfall 8: Tight Coupling Between LLM Layer and Tool Handlers

**What goes wrong:**
The LLM integration code directly imports and calls handler functions from `tools.py`, creating tight coupling. When handler interfaces change (e.g., pagination metadata is added to responses), the LLM prompt templates, tool descriptions, and response-parsing logic all break simultaneously. Worse, the single-file `tools.py` (already 630 lines per CONCERNS.md) becomes even more unwieldy with LLM orchestration code mixed in.

**Why it happens:**
The natural path is: import `dispatch` from `tools.py`, call it, pass the result to the LLM. This works for a prototype. But as the LLM layer adds context management, conversation memory, tool-call validation, and human-in-the-loop confirmation logic, this tight coupling means any change to the tool layer ripples through the LLM orchestration and vice versa.

**How to avoid:**
1. **Introduce an adapter/mediator layer** between the LLM and `tools.py`. The LLM layer calls the adapter; the adapter validates, transforms, and delegates to `dispatch`. This is where confirmation prompts, input validation, and response enrichment happen.
2. **Split `tools.py` into modules** (per CONCERNS.md recommendation): `client.py`, `schemas.py`, `handlers/`, `registry.py`. The LLM layer should only depend on `schemas.py` (for tool definitions) and `dispatch` (for invocation), not on handler internals.
3. **Use the decorator registration pattern** (per CONCERNS.md) to ensure new tools are automatically available to the LLM without manual wiring in two registries.
4. **Define a clear interface contract** — the LLM layer expects `{tool_name: str, args: dict} -> dict` and nothing else. If the response format changes, version it rather than breaking the contract.

**Warning signs:**
- Changing a handler's return format breaks LLM prompt templates
- Adding a new tool requires changes in 3+ files
- LLM orchestration code lives in the same file as API client code
- Tests for LLM behavior are coupled to `tools.py` internals

**Phase to address:**
Phase 1 (architecture) — the adapter pattern must be established before building features on top.

---

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Passing raw tool results directly to LLM context | Fast to implement, works in prototype | Context window bloat, leaked PII, inconsistent formatting, stale data | Only for initial prototype demo — must replace before real users |
| Storing conversation history in memory (no persistence) | Simple implementation, no database needed | Lost conversations on restart, no audit trail, can't recover from crashes | Never for production — single-user personal tool might tolerate, but losing a categorization correction history is painful |
| Using a single system prompt for all queries | One prompt to maintain | Prompt becomes bloated, LLM struggles with conflicting instructions, hard to debug | Acceptable only if total prompt <2000 tokens with instructions for all tools — unlikely with 13 tools |
| Skipping input validation on LLM-generated tool arguments | LLM "should" generate valid args from schema | LLM hallucinates invalid args (bad dates, wrong IDs, negative limits) causing cryptic API errors or silent failures | Never — validate all LLM outputs before passing to `dispatch` |
| Implementing categorization as prompt-only (no rules engine) | Elegant, no code for rules | Unpredictable, can't reproduce decisions, expensive per-transaction, degrades with prompt changes | MVP only — transition to hybrid (rules for obvious + LLM for ambiguous) before production |
| Using `float` for monetary calculations in LLM responses | LLMs naturally produce float strings | Floating-point errors compound: "$100.01 + $200.02" ≠ "$300.03" | Never — the codebase correctly uses `Decimal`; LLM response formatting must preserve this |

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| LLM ↔ tools.py | Passing full API response dicts into LLM context (hundreds of fields per transaction) | Transform API responses into minimal, human-readable summaries before including in context |
| LLM ↔ Firefly III | LLM inventing `transaction_id` values instead of listing/searching first | Force LLM to always fetch data first; never accept user-provided IDs without verification |
| LLM ↔ Firefly III write operations | LLM calling `update_transaction_tags` or `update_transaction_category` directly without confirmation | Intercept write calls in adapter layer; present proposed change to user; only execute on confirmation |
| Chat UI ↔ LLM | Sending entire conversation history every turn with no pruning | Implement sliding window or importance-based context selection; prioritize recent data + summary of older context |
| LLM ↔ Firefly III pagination | LLM not knowing when it has all data (responses lack pagination metadata) | Add `pagination` field to all list responses (CONCERNS.md fix); LLM can then decide whether more pages are needed |
| LLM ↔ date handling | LLM producing dates like "last month" instead of "YYYY-MM-DD" | Instruct LLM in system prompt to always compute explicit dates; add a date-computation utility the LLM can call |
| Auto-categorization ↔ Firefly III categories | LLM suggesting category names that don't exist in the user's Firefly III instance | Fetch category list at session start; include valid categories in system prompt; validate before applying |

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| Tool-call cascades ("I need more data" loops) | Single query takes 10+ seconds, 5+ API calls | Max 5-8 tool calls per turn; prefer aggregated tools (`calculate_net`, `compare_periods`) over raw data retrieval | More than 3 concurrent users |
| Including full transaction objects in LLM context | Token usage explodes; 50 transactions × 30 fields = ~15K tokens just for data | Transform to minimal summaries (date, description, amount, category only) before including in context | More than 20 transactions per query |
| Re-fetching data already retrieved in the conversation | LLM calls `list_transactions` again for data it retrieved 2 turns ago | Cache tool results with timestamps; reference cached data instead of re-fetching | Multi-turn conversations >5 turns |
| Generating savings reports over large date ranges | `calculate_net` over 12 months + `compare_periods` + individual transaction lookups = many API calls | Pre-compute common aggregates; offer date-range presets ("this month", "last 3 months") | Date ranges >6 months |
| No timeout on LLM API calls | User waits indefinitely if LLM provider is slow/down | Set explicit timeouts (30s for LLM call, 10s for Firefly III API); always return a response to the user | Any network instability |

## Security Mistakes

| Mistake | Risk | Prevention |
|---------|------|------------|
| Storing API token in localStorage on web chat | Token accessible to XSS attacks; persistence across sessions isn't worth the risk | Use httpOnly cookies or short-lived session tokens; store API token server-side only |
| Logging full LLM prompts/responses including financial data | Audit logs become a treasure trove of PII; compliance risk | Log tool calls (names, timestamps) but redact arguments and results; only log errors with sanitized details |
| No rate limiting on chat endpoint | Abuse (intentional or broken-client loop) can hammer Firefly III API and LLM provider, running up costs | Per-session rate limits: max N queries/minute, max M tool calls/query |
| Trusting LLM-generated transaction IDs for writes | LLM can hallucinate an ID; `update_transaction_category` on wrong transaction corrupts data | Validate IDs exist via `get_transaction` before any write; consider read-only mode for initial deployment |
| No HTTPS enforcement on Firefly III connection | API token transmitted in plaintext | Add `base_url` validation per CONCERSNS.md: reject `http://` (except localhost) |
| System prompt leaking internal tool structure | Prompt injection reveals how many tools exist, their names, API structure — helps attackers craft injection attacks | Never expose implementation details in system prompt; use abstract tool descriptions, not handler signatures |

## UX Pitfalls

| Pitfall | User Impact | Better Approach |
|---------|-------------|-----------------|
| LLM takes >10 seconds to respond with no feedback | User thinks it's broken; clicks again, creating duplicate requests | Show "Analyzing your question..." with a spinner; stream LLM responses token-by-token |
| LLM gives lengthy narrative when user wants a number | User asked "how much did I spend on dining?" and got a 3-paragraph essay | Instruct LLM: answer the specific question first (1-2 sentences + number), then offer to elaborate |
| No visual distinction between LLM-prose and tool-data | User can't tell which numbers are verified (from tools) vs. estimated (LLM guessing) | Format tool-sourced numbers differently (bold, with data icon); mark LLM inferences with language like "approximately" |
| Auto-categorization changes applied silently | User doesn't know what changed until they check Firefly III directly | Show a diff/preview before applying; email or in-app notification of changes made |
| Error messages from LLM are vague ("something went wrong") | User can't fix the problem or report it effectively | Surface the specific error (API timeout, invalid date, etc.) with a suggested action |

## "Looks Done But Isn't" Checklist

- [ ] **Chat interface works for "hello":** Often missing edge cases — empty state (no transactions), error recovery after API failure, and what happens when the LLM refuses to call any tool
- [ ] **Auto-categorization works for obvious cases:** Often missing edge cases — transactions with no description, existing categories that should be preserved, multi-split transactions where splits need different categories
- [ ] **Savings reports show numbers:** Often missing — verification that LLM-sourced numbers match tool-call results (not fabricated), proper handling of `Decimal`→string formatting, and currency symbols
- [ ] **Tool descriptions are written:** Often missing — example inputs/outputs in descriptions, "when NOT to use this tool" guidance, and constraints (date format, valid `account_type` values)
- [ ] **Confirmation before writes:** Often missing — the chat says "I've updated the category" when it should say "I'd like to update the category to X. Apply?"
- [ ] **Date handling for "natural language" queries:** Often missing — user says "last month" but LLM must convert to YYYY-MM-DD; timezone handling for date boundaries

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| LLM hallucinated tool arguments causing wrong write | LOW | Firefly III has no undo; add transaction note with "auto-categorized by finance-analyzer" for traceability; manual correction in Firefly III UI |
| Tight LLM-tool coupling requires refactor | MEDIUM | Extract adapter layer; define interface contract; incremental migration one tool at a time |
| Context window overflow causing inconsistent answers | LOW | Clear conversation and restart; implement context window monitoring and proactively summarize old turns |
| Auto-categorization learned bad rules from corrections | MEDIUM | Rule database can be wiped; prompt-based few-shot corrections can be updated; add per-correction review mechanism |
| Security breach (token/PII leak from logs) | HIGH | Rotate API tokens; audit all log stores; add sanitization layer; impossible to fully remediate retroactively — prevent upfront |
| Missing pagination metadata forces N+1 API calls | LOW | Add pagination fields to handler responses; LLM can then make informed pagination decisions; performance improves immediately |

## Pitfall-to-Phase Mapping

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| Hallucinated tool arguments | Phase 1 (LLM integration) | Test with adversarial queries; verify LLM selects correct tool and params for 50+ varied inputs |
| Writes without confirmation | Phase 1 (LLM integration) | Verify no write tool is ever called without user confirmation step; test with queries that trigger writes |
| Stale context in multi-turn | Phase 1 (chat interface) | Test 10+ turn conversations; verify numbers stay consistent across turns |
| Memorized corrections | Phase 2 (auto-categorization) | Test: correct a category, then present similar-but-different transaction; verify it re-evaluates rather than blindly applies rule |
| Sensitive data exposure | Phase 1 (security) | Audit all logs, error messages, and LLM prompts for PII; run OWASP-style prompt injection tests |
| Unbounded tool-call loops | Phase 1 (LLM integration) | Verify max tool calls enforced; test with "broad" queries that could trigger pagination; monitor token usage |
| Narrative vs. data confusion | Phase 2 (savings reports) | Cross-check every number in LLM report against tool-call results; verify no calculated values that didn't come from a tool |
| Tight LLM-tool coupling | Phase 1 (architecture) | Verify LLM layer imports only `dispatch`, `get_tools`, and `FireflyClient`; no handler internals |
| Security: token in localStorage | Phase 3 (web chat) | Penetration test; verify no token in browser storage; verify httpOnly cookie or server-side session |
| Security: missing HTTPS | Phase 1 (architecture) | Add validation in `FireflyClient.__init__`; test with `http://` URL |

## Sources

- Anthropic "Building Effective Agents" research (Dec 2024) — tool design, ACI principles, workflow patterns, human-in-the-loop confirmation
- Codebase analysis (`tools.py`, `tests/test_tools.py`, `AGENTS.md`, `CLAUDE.md`)
- `.planning/codebase/CONCERNS.md` — known bugs, security issues, tech debt, scaling limits
- `.planning/PROJECT.md` — requirements and key decisions (re-evaluate vs. memorize, chat-first interface)
- OpenAI function-calling documentation — schema design best practices
- Domain knowledge: personal finance app UX patterns, LLM tool-use failure modes in production systems

---
*Pitfalls research for: LLM-powered personal finance analyzer*
*Researched: 2026-05-06*