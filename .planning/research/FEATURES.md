# Feature Research

**Domain:** LLM-powered personal finance analyzer
**Researched:** 2026-05-06
**Confidence:** MEDIUM (based on competitor analysis and project requirements; no direct user research conducted)

## Feature Landscape

### Table Stakes (Users Expect These)

Features users assume exist. Missing these = product feels incomplete.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Natural language spending Q&A | "How much did I spend on X?" is the core promise of an LLM finance tool | MEDIUM | Requires LLM-to-tool routing, date parsing, result formatting. Existing tools.py provides data access; the layer is the conversation orchestration |
| Auto-categorization of transactions | Every competitor (Monarch, Copilot, Lunch Money) categorizes automatically | MEDIUM | LLM classifies by description + account name + amount patterns. Must integrate with Firefly III's category system via existing `update_transaction_category` tool |
| Spending breakdown by category | "Where did my money go?" — table stakes for any finance product | LOW | Already partially covered by `get_expense_insights`; needs natural language framing |
| Period comparison | "How does this month compare to last?" — users naturally ask this | LOW | `compare_periods` tool already exists; needs conversational wrapping |
| Conversation context within session | Follow-up questions like "What about last month?" require remembering context | MEDIUM | LLM must maintain short-term context (date ranges, categories mentioned, filters applied). Without this, every question starts from scratch |
| List/filter transactions via chat | "Show me all grocery transactions from last week" | LOW | `search_transactions` and `get_transactions_by_date_range` already exist; needs LLM routing |
| Error handling in natural language | When data is missing or queries fail, user gets a clear explanation, not a stack trace | LOW | Existing handlers return `{"error": "..."}` — LLM can translate these into human responses |

### Differentiators (Competitive Advantage)

Features that set the product apart. Not required, but valuable.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Learning categorization from corrections | User corrects "AMZN" → Groceries to "AMZN" → Shopping; system re-evaluates categorization rules rather than memorizing the single correction | HIGH | Must distinguish between specific override ("this transaction is X") and rule update ("transactions from Amazon are X"). Simple rule engines just memorize; LLM can generalize patterns |
| Narrative savings reports | Written analysis + data: "Your dining spending increased 40% over 3 months, driven by..." | MEDIUM | Most apps show charts; this provides interpretation. Combines `compare_periods` + `get_expense_insights` data with LLM narrative generation |
| Concrete actionable suggestions | "Consider capping dining at $200/mo" backed by actual spending data | MEDIUM | Goes beyond observation to recommendation. Requires confidence thresholds — suggestions must cite data ("you averaged $350/mo over 6 months") |
| Unnecessary spending identification | "Which expenses weren't necessary?" — judgment call LLMs can make | MEDIUM-HIGH | Requires LLM to reason about transaction context (subscriptions, impulse purchases, upgrades). Edge cases are subjective; must present as suggestions, not facts |
| Proactive anomaly flagging | "Your utilities were 3x the 6-month average" — unsolicited insight | LOW-MEDIUM | Low-hanging fruit: compute monthly averages, flag deviations >2σ. High value relative to implementation cost |
| Net worth / cash flow narrative | "You're spending $400/mo more than you earn, driven by..." | LOW | `calculate_net` already exists; adding conversational framing is straightforward |
| Multi-month trend analysis | "Show me my dining trend over the last 6 months" with inline data | MEDIUM | Requires iterating over monthly periods, aggregating, and presenting as trend. LLM can call tools in a loop |
| Spending category suggestions | "You might want a 'Home Office' category — you have 15 transactions matching that pattern" | MEDIUM | LLM examines uncategorized transactions and suggests new categories. Unique to LLM-first approach |

### Anti-Features (Commonly Requested, Often Problematic)

Features that seem good but create problems.

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| Budget enforcement / tracking | Users want to set budgets and track against them | Project scope is analysis, not budget enforcement. Firefly III has its own budget system. Building budget UI duplicates existing functionality and is a bottomless UX hole | Show spending trends that inform budget decisions; don't enforce budgets |
| Real-time bank feed syncing | Users want live transactions | Firefly III's data importer handles this. Duplicating bank connection logic is massive scope (Plaid/nordigen integration, credential management, refresh scheduling) | Work with data already in Firefly III. Document the workflow: import → analyze |
| Complex charting / visualization engine | Dashboards with interactive charts | Building a chart library is a separate product. Maintenance cost is high, chart libraries are opinionated, and the LLM narrative approach is the differentiator | Use simple data tables in chat responses. LLM describes trends in natural language. Save charts for savings reports if needed, and use lightweight inline charts |
| Multi-user / household collaboration | "My partner and I want to share" | Project explicitly says single-instance, personal use. Multi-tenancy adds auth, permissions, data isolation — massive complexity | Single user model. Firefly III itself supports multi-user, but the analyzer is personal |
| Investment / portfolio tracking | "Track my stocks" | Copilot does this well, but it's a separate domain from spending analysis. Different data sources, different analysis patterns, different regulatory concerns | Focus on spending analysis. If users want portfolio tracking, that's a different product |
| Automated transaction creation | "Schedule recurring bills" | Read-only analysis focus. Creating/scheduling transactions changes the product from analyzer to manager, with all the data integrity concerns that entails | Detect and report recurring expenses; don't create them |
| Licensed financial advice | "Should I invest in VTEB?" | Regulatory landmine. Even disclaimers don't fully protect. LLM output can be misinterpreted as professional advice | Stick to descriptive analysis ("you spent X on Y") and behavioral suggestions ("consider reducing Z"). Never give investment or tax advice |
| Persistent memory across sessions | "Remember that I don't want to count transfers" | Cross-session memory creates privacy and consistency issues. LLM context windows grow. Users forget what they told the system | Session-scoped context only. If patterns emerge, suggest they set up rules in Firefly III |

## Feature Dependencies

```
Natural Language Q&A (Table Stakes)
    ├──requires──> LLM Chat Loop (orchestration layer)
    │                   └──requires──> Web Chat Interface
    │
    ├──requires──> Tool Routing (LLM → tools.py dispatch)
    │
    └──enhances──> Conversation Context (session-scoped)

Auto-Categorization
    ├──requires──> LLM Chat Loop
    ├──requires──> Transaction fetching + category update tools
    └──conflicts──> Firefly III Rules Engine (overlap in scope)

Learning from Corrections
    └──requires──> Auto-Categorization (must have categorization before you can correct it)
    └──requires──> Correction pattern storage (in-memory for session)

Narrative Savings Reports
    ├──requires──> Natural Language Q&A
    ├──requires──> Multi-month data aggregation (compare_periods called repeatedly)
    └──enhances──> Actionable Suggestions (reports provide data for suggestions)

Actionable Suggestions
    ├──requires──> Narrative Savings Reports (data-backed suggestions need data)
    └──requires──> Spending breakdown + period comparison tools

Proactive Anomaly Detection
    └──requires──> Multi-month trend data
    └──can exist independently of chat (background check on session start)
```

### Dependency Notes

- **LLM Chat Loop requires Web Chat Interface:** The orchestration layer (LLM ↔ tools) and the web UI are tightly coupled — the chat loop IS the interface. Build them together.
- **Auto-Categorization conflicts with Firefly III Rules:** Firefly III has its own rule engine for categorization. The LLM approach should complement, not replace. Strategy: LLM categorizes uncategorized transactions; Firefly III rules handle known patterns.
- **Learning from Corrections requires Auto-Categorization:** You can't learn from corrections if there's no categorization to correct. The "learning" layer sits on top of the initial categorization.
- **Narrative Reports require multi-period data:** A 6-month trend report needs 6 separate API calls. The tool layer supports this via `compare_periods` and `get_expense_insights`, but the LLM orchestration must chain them.

## MVP Definition

### Launch With (v1)

- [ ] Web chat interface — natural language input, tool-routed responses
- [ ] LLM chat loop with tool dispatch — routes user questions to existing tools.py handlers
- [ ] Session-scoped conversation context — remember date ranges, categories, and filters within a chat session
- [ ] Natural language spending Q&A — "How much did I spend on X?" with real transaction data
- [ ] Auto-categorization of uncategorized transactions — LLM classifies by description, amount, account, date
- [ ] Spending breakdowns and period comparisons in plain English — wrapping existing `get_expense_insights`, `calculate_net`, `compare_periods`

### Add After Validation (v1.x)

- [ ] Learning from corrections — re-evaluate categorization patterns when user corrects
- [ ] Narrative savings reports — 3-6 month trend analysis with written interpretation
- [ ] Actionable suggestions — "Consider capping dining at $200/mo" backed by data
- [ ] Proactive anomaly flagging — detect and surface unusual spending patterns

### Future Consideration (v2+)

- [ ] Unnecessary spending identification — subjective, needs careful framing
- [ ] Spending category suggestions — "You might want a 'Home Office' category"
- [ ] Recurring expense detection and highlighting
- [ ] Export savings reports as PDF or shareable format

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| LLM chat loop with tool routing | HIGH | MEDIUM | P1 |
| Web chat interface | HIGH | MEDIUM | P1 |
| Session-scoped conversation context | HIGH | MEDIUM | P1 |
| Natural language spending Q&A | HIGH | LOW | P1 |
| Auto-categorization | HIGH | MEDIUM | P1 |
| Spending breakdowns in PL [English] | MEDIUM | LOW | P1 |
| Period comparisons in PL [English] | MEDIUM | LOW | P1 |
| Proactive anomaly flagging | MEDIUM | LOW-MEDIUM | P2 |
| Narrative savings reports | HIGH | MEDIUM | P2 |
| Learning from corrections | HIGH | HIGH | P2 |
| Actionable suggestions | HIGH | MEDIUM | P2 |
| Unnecessary spending ID | MEDIUM | MEDIUM-HIGH | P3 |
| Category suggestions | LOW-MEDIUM | MEDIUM | P3 |
| Recurring expense detection | MEDIUM | MEDIUM | P3 |

**Priority key:**
- P1: Must have for launch
- P2: Should have, add when possible
- P3: Nice to have, future consideration

## Competitor Feature Analysis

| Feature | Monarch Money | Copilot Money | Lunch Money | Firefly III (base) | Our Approach |
|---------|---------------|---------------|-------------|---------------------|--------------|
| Auto-categorization | AI-powered, learns patterns | AI learns spending patterns, improves with use | Rules engine (if/then) | Rules engine (triggers + actions) | LLM classifies uncategorized transactions; complement Firefly III rules |
| Natural language query | No (traditional UI) | No (traditional UI, now testing "agent") | No (traditional UI) | No (API only) | Primary interface — chat-first, not dashboard-first |
| Spending insights | Charts, trends, customizable reports | Spending line, cash flow, rollover budgets | Analytics, stats & trends pages | Built-in reports by category/tag/budget | LLM-generated narrative interpretation, not raw charts |
| Budgeting | Full budget management, goals | Budget with rollovers | Budget with rollovers | Budgets with limits | Don't build — out of scope. Inform budget decisions via analysis |
| Recurring expense detection | Yes, subscription tracker | Yes, spot subscriptions | Yes, recurring expenses | No built-in | P3 — LLM can detect recurring patterns from transaction data |
| Couple/household | Yes, built-in sharing | No | Yes, collaboration | Multi-user support | Out of scope — single user |
| Investment tracking | Yes, portfolio + net worth | Yes, stocks + crypto + real estate | Yes, crypto portfolio | No | Out of scope — spending analysis focus |
| Actionable suggestions | Limited ("you could save by...") | Spending line shows overspending | No | No | Core differentiator — data-backed behavioral suggestions |
| Correction learning | Implicit (categorization improves) | "The more you use it, the smarter it gets" | Manual rules | Manual rules | Explicit: user corrects → LLM re-evaluates pattern |

## Sources

- Copilot Money feature analysis (copilotmoney.com) — AI tagging, spending line, subscription detection, net worth tracking. MEDIUM confidence (product website, no independent verification)
- Monarch Money feature analysis (monarchmoney.com) — Full budget management, AI categorization, reports, goals, collaboration, subscription tracking. MEDIUM confidence (product website)
- Lunch Money feature analysis (lunchmoney.app) — Rules engine, categories/tags, recurring expenses, analytics, budgeting, developer API. MEDIUM confidence (product website)
- Firefly III (firefly-iii.org) — Base platform provides double-entry, rules engine, budgets, categories, tags, reports, REST API. HIGH confidence (project's own data source)
- Project requirements from PROJECT.md — Active requirements list defining scope. HIGH confidence (project-defined)

---
*Feature research for: LLM-powered personal finance analyzer*
*Researched: 2026-05-06*