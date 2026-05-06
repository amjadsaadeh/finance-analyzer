# Finance Analyzer

## What This Is

An LLM-powered personal finance analyzer connected to a private Firefly III instance. Users interact through a web chat interface to ask questions about their spending, get intelligent categorization of transactions, and receive actionable savings recommendations backed by real financial data.

## Core Value

Turning raw transaction data into actionable financial insight through natural conversation — the LLM understands context, learns from corrections, and gives advice you can act on.

## Requirements

### Validated

- ✓ List and search transactions from Firefly III — existing
- ✓ Tag and categorize individual transactions — existing
- ✓ View accounts, categories, and tags — existing
- ✓ Generate expense and income insights by date range — existing
- ✓ Calculate net cash flow and compare periods — existing
- ✓ Sum transaction amounts with Decimal precision — existing

### Active

- [ ] System auto-categorizes transactions based on description, date, and account name
- [ ] System learns from user corrections — re-evaluates rules when corrected, not memorized blindly
- [ ] Savings reports combining written narrative insights with charts/tables showing 3-6 month trends
- [ ] Reports suggest concrete actions ("Consider capping dining at $200/mo") backed by data
- [ ] Web chat interface as primary interaction — ask questions in natural language
- [ ] Chat answers specific queries ("How much did I spend on hobbies?") with real transaction data
- [ ] Chat identifies unnecessary spendings when asked ("Which expenses weren't necessary?")

### Out of Scope

- Multiple data sources beyond Firefly III — personal single-instance use only
- Mobile app — web interface first
- Budget creation/management — reports suggest actions, but don't enforce budgets
- Invoice/bill tracking — focus on analysis, not bill management

## Context

- Existing codebase provides a solid Firefly III API tool layer (`tools.py`) with 13 tools following OpenAI function-calling protocol
- Tools use Pydantic schemas for parameter validation and dispatch pattern for routing
- Firefly III API client is already working — transactions, accounts, categories, tags, insights
- No web framework or chat interface exists yet — `main.py` is a stub
- LLM integration currently limited to tool schema generation (`pydantic_function_tool`); no actual LLM call loop

## Constraints

- **Tech Stack**: Python 3.12, managed by uv — existing codebase must be extended, not replaced
- **Data Source**: Single private Firefly III instance — no multi-tenant or multi-source support needed
- **API Client**: Must use existing `firefly-iii-api-client` package (auto-generated, quirky)
- **Error Pattern**: Handlers return `{"error": "..."}` dicts, never raise — new code should follow this convention

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Extend existing tools.py rather than refactor | Working API layer, well-tested | — Pending |
| Categorization re-evaluates rather than memorizes | User corrections inform but don't create rigid rules | — Pending |
| Chat is primary interface, not reports page | Natural language is the most accessible way to explore finances | — Pending |

---
*Last updated: 2026-05-06 after initialization*