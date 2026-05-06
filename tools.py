import os
import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field
from openai import pydantic_function_tool

from firefly_iii_client.configuration import Configuration
from firefly_iii_client import ApiClient
from firefly_iii_client.api import (
    TransactionsApi,
    AccountsApi,
    CategoriesApi,
    TagsApi,
    SearchApi,
    InsightApi,
)
from firefly_iii_client.models import TransactionUpdate, TransactionSplitUpdate
from firefly_iii_client.exceptions import ApiException


class FireflyClient:
    """Thin wrapper around the Firefly III ApiClient, configured from env vars or explicit args.

    Config precedence: constructor arguments > environment variables
    (``FIREFLY_BASE_URL``, ``FIREFLY_API_TOKEN``).
    """

    def __init__(self, base_url: str | None = None, api_token: str | None = None):
        self.base_url = base_url or os.environ.get("FIREFLY_BASE_URL")
        self.api_token = api_token or os.environ.get("FIREFLY_API_TOKEN")
        if not self.base_url:
            raise ValueError("FIREFLY_BASE_URL must be set via env var or constructor argument")
        if not self.api_token:
            raise ValueError("FIREFLY_API_TOKEN must be set via env var or constructor argument")
        config = Configuration(host=self.base_url, access_token=self.api_token)
        self.api_client = ApiClient(configuration=config)


# --- Tool parameter schemas ---------------------------------------------------


class ListTransactions(BaseModel):
    """List transactions from Firefly III. Results are paginated (default 50 per page); use the page parameter to retrieve subsequent pages."""

    limit: int = Field(50, description="Max results per page (default 50)")
    page: int = Field(1, description="Page number (default 1)")


class GetTransactionsByDateRange(BaseModel):
    """List transactions between start_date and end_date (YYYY-MM-DD format). Results are paginated; increase page to retrieve more."""

    start_date: str = Field(..., description="Start date in YYYY-MM-DD format")
    end_date: str = Field(..., description="End date in YYYY-MM-DD format")
    limit: int = Field(50, description="Max results per page (default 50)")
    page: int = Field(1, description="Page number (default 1)")


class SearchTransactions(BaseModel):
    """Full-text search across transaction descriptions."""

    query: str = Field(..., description="Search query string")
    limit: int = Field(50, description="Max results per page (default 50)")
    page: int = Field(1, description="Page number (default 1)")


class UpdateTransactionTags(BaseModel):
    """Replace all tags on a transaction with a new list of tags."""

    transaction_id: str = Field(..., description="ID of the transaction")
    tags: list[str] = Field(..., description="New list of tags (replaces existing tags)")


class UpdateTransactionCategory(BaseModel):
    """Set the category on a transaction."""

    transaction_id: str = Field(..., description="ID of the transaction")
    category_name: str = Field(..., description="Category name to assign")


class ListAccounts(BaseModel):
    """List all accounts with their current balances."""

    account_type: str | None = Field(
        None,
        description="Filter by account type, e.g. asset, expense, revenue, liability, cash, liabilities (optional — omit for all)",
    )
    limit: int = Field(50, description="Max results per page (default 50)")
    page: int = Field(1, description="Page number (default 1)")


class GetExpenseInsights(BaseModel):
    """Get expense totals grouped by category for a date range."""

    start_date: str = Field(..., description="Start date in YYYY-MM-DD format")
    end_date: str = Field(..., description="End date in YYYY-MM-DD format")
    account_ids: list[int] | None = Field(None, description="Filter by account IDs (optional)")


class GetIncomeInsights(BaseModel):
    """Get income totals grouped by category for a date range."""

    start_date: str = Field(..., description="Start date in YYYY-MM-DD format")
    end_date: str = Field(..., description="End date in YYYY-MM-DD format")
    account_ids: list[int] | None = Field(None, description="Filter by account IDs (optional)")


class ListCategories(BaseModel):
    """List all transaction categories."""

    limit: int = Field(50, description="Max results per page (default 50)")
    page: int = Field(1, description="Page number (default 1)")


class ListTags(BaseModel):
    """List all transaction tags."""

    limit: int = Field(50, description="Max results per page (default 50)")
    page: int = Field(1, description="Page number (default 1)")


class SumTransactions(BaseModel):
    """Sum transaction amounts from a list already returned by a previous tool call.

    Use this instead of doing arithmetic yourself to avoid floating-point errors on large datasets.
    Returns totals split by transaction type (deposit=income, withdrawal=expense, transfer=neutral).
    """

    transactions: list[dict[str, Any]] = Field(
        ...,
        description="List of transaction dicts as returned by list_transactions, get_transactions_by_date_range, or search_transactions",
    )


class CalculateNet(BaseModel):
    """Calculate net cash flow (total income minus total expenses) for a date range.

    Fetches expense and income insight totals from Firefly III and subtracts to produce net.
    """

    start_date: str = Field(..., description="Start date in YYYY-MM-DD format")
    end_date: str = Field(..., description="End date in YYYY-MM-DD format")
    account_ids: list[int] | None = Field(None, description="Filter by account IDs (optional)")


class ComparePeriods(BaseModel):
    """Compare income, expenses, and net cash flow between two date ranges.

    Returns totals for each period plus the absolute and percentage delta (period_b minus period_a).
    """

    period_a_start: str = Field(..., description="Start of the first period (YYYY-MM-DD)")
    period_a_end: str = Field(..., description="End of the first period (YYYY-MM-DD)")
    period_b_start: str = Field(..., description="Start of the second period (YYYY-MM-DD)")
    period_b_end: str = Field(..., description="End of the second period (YYYY-MM-DD)")
    account_ids: list[int] | None = Field(None, description="Filter by account IDs (optional)")


TOOLS: list = [
    pydantic_function_tool(ListTransactions, name="list_transactions"),
    pydantic_function_tool(GetTransactionsByDateRange, name="get_transactions_by_date_range"),
    pydantic_function_tool(SearchTransactions, name="search_transactions"),
    pydantic_function_tool(UpdateTransactionTags, name="update_transaction_tags"),
    pydantic_function_tool(UpdateTransactionCategory, name="update_transaction_category"),
    pydantic_function_tool(ListAccounts, name="list_accounts"),
    pydantic_function_tool(GetExpenseInsights, name="get_expense_insights"),
    pydantic_function_tool(GetIncomeInsights, name="get_income_insights"),
    pydantic_function_tool(ListCategories, name="list_categories"),
    pydantic_function_tool(ListTags, name="list_tags"),
    pydantic_function_tool(SumTransactions, name="sum_transactions"),
    pydantic_function_tool(CalculateNet, name="calculate_net"),
    pydantic_function_tool(ComparePeriods, name="compare_periods"),
]


# --- Handlers -----------------------------------------------------------------


def _handler_list_transactions(client: FireflyClient, args: dict) -> dict:
    """Return a paginated list of transactions.

    Args:
        args: Optional keys: ``limit`` (int, default 50), ``page`` (int, default 1).

    Returns:
        ``{"transactions": [...]}`` or ``{"error": "..."}`` on API failure.
    """
    api = TransactionsApi(client.api_client)
    try:
        resp = api.list_transaction(
            limit=args.get("limit", 50),
            page=args.get("page", 1),
        )
        return {"transactions": [t.to_dict() for t in resp.data]}
    except ApiException as e:
        return {"error": str(e)}


def _handler_get_transactions_by_date_range(client: FireflyClient, args: dict) -> dict:
    """Return transactions whose date falls within [start_date, end_date].

    Args:
        args: Required keys: ``start_date``, ``end_date`` (YYYY-MM-DD strings).
              Optional: ``limit`` (int, default 50), ``page`` (int, default 1).

    Returns:
        ``{"transactions": [...]}`` or ``{"error": "..."}`` on bad args or API failure.
    """
    api = TransactionsApi(client.api_client)
    try:
        start = datetime.date.fromisoformat(args["start_date"])
        end = datetime.date.fromisoformat(args["end_date"])
    except KeyError as e:
        return {"error": f"Missing required argument: {e}"}
    except ValueError as e:
        return {"error": f"Invalid date format: {e}"}
    try:
        resp = api.list_transaction(
            start=start,
            end=end,
            limit=args.get("limit", 50),
            page=args.get("page", 1),
        )
        return {"transactions": [t.to_dict() for t in resp.data]}
    except ApiException as e:
        return {"error": str(e)}


def _handler_search_transactions(client: FireflyClient, args: dict) -> dict:
    """Full-text search across transaction descriptions.

    Args:
        args: Required key: ``query`` (str).
              Optional: ``limit`` (int, default 50), ``page`` (int, default 1).

    Returns:
        ``{"transactions": [...]}`` or ``{"error": "..."}`` on bad args or API failure.
    """
    api = SearchApi(client.api_client)
    try:
        query = args["query"]
    except KeyError as e:
        return {"error": f"Missing required argument: {e}"}
    try:
        resp = api.search_transactions(
            query=query,
            limit=args.get("limit", 50),
            page=args.get("page", 1),
        )
        return {"transactions": [t.to_dict() for t in resp.data]}
    except ApiException as e:
        return {"error": str(e)}


def _build_split_update(split, *, tags=None, category_name=None) -> TransactionSplitUpdate:
    """Build a TransactionSplitUpdate from an existing split, overriding tags and/or category.

    Preserves all required fields (description, date, amount, type, source/destination IDs)
    so the PUT request doesn't accidentally clear them.
    """
    return TransactionSplitUpdate(
        description=split.description,
        date=split.date,
        amount=str(split.amount),
        type=split.type,
        tags=tags if tags is not None else split.tags,
        category_name=category_name if category_name is not None else split.category_name,
        source_id=str(split.source_id) if split.source_id else None,
        destination_id=str(split.destination_id) if split.destination_id else None,
    )


def _handler_update_transaction_tags(client: FireflyClient, args: dict) -> dict:
    """Replace all tags on a transaction with a new list.

    Fetches the existing transaction first so all split fields are preserved during the PUT.

    Args:
        args: Required keys: ``transaction_id`` (str), ``tags`` (list[str]).

    Returns:
        Updated transaction data dict or ``{"error": "..."}`` on bad args or API failure.
    """
    api = TransactionsApi(client.api_client)
    try:
        tx_id = str(args["transaction_id"])
        tags = args["tags"]
    except KeyError as e:
        return {"error": f"Missing required argument: {e}"}
    try:
        existing = api.get_transaction(tx_id)
        splits = existing.data.attributes.transactions
        updated = [_build_split_update(s, tags=tags) for s in splits]
        result = api.update_transaction(tx_id, TransactionUpdate(transactions=updated))
        return result.data.to_dict()
    except ApiException as e:
        return {"error": str(e)}


def _handler_update_transaction_category(client: FireflyClient, args: dict) -> dict:
    """Set the category on a transaction.

    Fetches the existing transaction first so all split fields are preserved during the PUT.

    Args:
        args: Required keys: ``transaction_id`` (str), ``category_name`` (str).

    Returns:
        Updated transaction data dict or ``{"error": "..."}`` on bad args or API failure.
    """
    api = TransactionsApi(client.api_client)
    try:
        tx_id = str(args["transaction_id"])
        category_name = args["category_name"]
    except KeyError as e:
        return {"error": f"Missing required argument: {e}"}
    try:
        existing = api.get_transaction(tx_id)
        splits = existing.data.attributes.transactions
        updated = [_build_split_update(s, category_name=category_name) for s in splits]
        result = api.update_transaction(tx_id, TransactionUpdate(transactions=updated))
        return result.data.to_dict()
    except ApiException as e:
        return {"error": str(e)}


def _handler_list_accounts(client: FireflyClient, args: dict) -> dict:
    """List accounts with their current balances.

    Args:
        args: Optional keys: ``account_type`` (str, e.g. "asset", "expense", "revenue"),
              ``limit`` (int, default 50), ``page`` (int, default 1).

    Returns:
        ``{"accounts": [...]}`` or ``{"error": "..."}`` on API failure.
    """
    api = AccountsApi(client.api_client)
    try:
        resp = api.list_account(
            limit=args.get("limit", 50),
            page=args.get("page", 1),
            type=args.get("account_type"),
        )
        return {"accounts": [a.to_dict() for a in resp.data]}
    except ApiException as e:
        return {"error": str(e)}


def _handler_get_expense_insights(client: FireflyClient, args: dict) -> dict:
    """Return expense totals grouped by category for a date range.

    Args:
        args: Required keys: ``start_date``, ``end_date`` (YYYY-MM-DD strings).
              Optional: ``account_ids`` (list[int]) to restrict to specific accounts.

    Returns:
        ``{"insights": [...]}`` or ``{"error": "..."}`` on bad args or API failure.
    """
    api = InsightApi(client.api_client)
    try:
        start = datetime.date.fromisoformat(args["start_date"])
        end = datetime.date.fromisoformat(args["end_date"])
    except KeyError as e:
        return {"error": f"Missing required argument: {e}"}
    except ValueError as e:
        return {"error": f"Invalid date format: {e}"}
    try:
        entries = api.insight_expense_category(
            start=start,
            end=end,
            accounts=args.get("account_ids"),
        )
        return {"insights": [entry.to_dict() for entry in entries]}
    except ApiException as e:
        return {"error": str(e)}


def _handler_get_income_insights(client: FireflyClient, args: dict) -> dict:
    """Return income totals grouped by category for a date range.

    Args:
        args: Required keys: ``start_date``, ``end_date`` (YYYY-MM-DD strings).
              Optional: ``account_ids`` (list[int]) to restrict to specific accounts.

    Returns:
        ``{"insights": [...]}`` or ``{"error": "..."}`` on bad args or API failure.
    """
    api = InsightApi(client.api_client)
    try:
        start = datetime.date.fromisoformat(args["start_date"])
        end = datetime.date.fromisoformat(args["end_date"])
    except KeyError as e:
        return {"error": f"Missing required argument: {e}"}
    except ValueError as e:
        return {"error": f"Invalid date format: {e}"}
    try:
        entries = api.insight_income_category(
            start=start,
            end=end,
            accounts=args.get("account_ids"),
        )
        return {"insights": [entry.to_dict() for entry in entries]}
    except ApiException as e:
        return {"error": str(e)}


def _handler_list_categories(client: FireflyClient, args: dict) -> dict:
    """List all transaction categories.

    Args:
        args: Optional keys: ``limit`` (int, default 50), ``page`` (int, default 1).

    Returns:
        ``{"categories": [...]}`` or ``{"error": "..."}`` on API failure.
    """
    api = CategoriesApi(client.api_client)
    try:
        resp = api.list_category(
            limit=args.get("limit", 50),
            page=args.get("page", 1),
        )
        return {"categories": [c.to_dict() for c in resp.data]}
    except ApiException as e:
        return {"error": str(e)}


def _handler_list_tags(client: FireflyClient, args: dict) -> dict:
    """List all transaction tags.

    Args:
        args: Optional keys: ``limit`` (int, default 50), ``page`` (int, default 1).

    Returns:
        ``{"tags": [...]}`` or ``{"error": "..."}`` on API failure.
    """
    api = TagsApi(client.api_client)
    try:
        resp = api.list_tag(
            limit=args.get("limit", 50),
            page=args.get("page", 1),
        )
        return {"tags": [t.to_dict() for t in resp.data]}
    except ApiException as e:
        return {"error": str(e)}


def _insight_total(insights: list[dict]) -> Decimal:
    """Sum the absolute values of difference_float across insight entries."""
    return sum(
        (Decimal(str(abs(e.get("difference_float", 0)))) for e in insights),
        Decimal("0"),
    )


def _fetch_net(client: FireflyClient, start_date: str, end_date: str, account_ids: list | None) -> dict:
    """Return income, expenses, and net for a date range. Shared by calculate_net and compare_periods."""
    args = {"start_date": start_date, "end_date": end_date, "account_ids": account_ids}
    expense_result = _handler_get_expense_insights(client, args)
    if "error" in expense_result:
        return expense_result
    income_result = _handler_get_income_insights(client, args)
    if "error" in income_result:
        return income_result
    total_expenses = _insight_total(expense_result["insights"])
    total_income = _insight_total(income_result["insights"])
    net = total_income - total_expenses
    return {
        "total_income": str(total_income),
        "total_expenses": str(total_expenses),
        "net": str(net),
    }


def _handler_sum_transactions(client: FireflyClient, args: dict) -> dict:
    """Sum amounts from a list of transaction dicts using Decimal arithmetic.

    Navigates the Firefly III transaction dict structure (``attributes.transactions`` splits)
    and groups totals by type: deposit (income), withdrawal (expense), transfer.

    Args:
        args: Required key: ``transactions`` (list of transaction dicts).

    Returns:
        Dict with ``total_income``, ``total_expenses``, ``total_transfers``, ``net``,
        and ``split_count``. All monetary values are strings to preserve precision.
    """
    transactions = args.get("transactions", [])
    total_income = Decimal("0")
    total_expenses = Decimal("0")
    total_transfers = Decimal("0")
    split_count = 0

    for tx in transactions:
        splits = tx.get("attributes", {}).get("transactions", [])
        for split in splits:
            tx_type = split.get("type", "")
            try:
                amount = Decimal(str(split.get("amount", "0")))
            except Exception:
                continue
            split_count += 1
            if tx_type == "deposit":
                total_income += amount
            elif tx_type == "withdrawal":
                total_expenses += amount
            elif tx_type == "transfer":
                total_transfers += amount

    return {
        "total_income": str(total_income),
        "total_expenses": str(total_expenses),
        "total_transfers": str(total_transfers),
        "net": str(total_income - total_expenses),
        "split_count": split_count,
    }


def _handler_calculate_net(client: FireflyClient, args: dict) -> dict:
    """Return net cash flow (income minus expenses) for a date range.

    Aggregates all category-level insight totals from Firefly III into a single net figure.

    Args:
        args: Required keys: ``start_date``, ``end_date`` (YYYY-MM-DD strings).
              Optional: ``account_ids`` (list[int]).

    Returns:
        Dict with ``total_income``, ``total_expenses``, ``net`` (all as strings),
        or ``{"error": "..."}`` on bad args or API failure.
    """
    try:
        start_date = args["start_date"]
        end_date = args["end_date"]
    except KeyError as e:
        return {"error": f"Missing required argument: {e}"}
    return _fetch_net(client, start_date, end_date, args.get("account_ids"))


def _handler_compare_periods(client: FireflyClient, args: dict) -> dict:
    """Compare income, expenses, and net between two date ranges.

    Args:
        args: Required keys: ``period_a_start``, ``period_a_end``,
              ``period_b_start``, ``period_b_end`` (YYYY-MM-DD strings).
              Optional: ``account_ids`` (list[int]).

    Returns:
        Dict with ``period_a``, ``period_b`` (each containing ``total_income``,
        ``total_expenses``, ``net``), and ``delta`` (``period_b - period_a``)
        with ``absolute`` and ``percent`` sub-keys for income, expenses, and net.
        Returns ``{"error": "..."}`` on bad args or API failure.
    """
    try:
        a_start = args["period_a_start"]
        a_end = args["period_a_end"]
        b_start = args["period_b_start"]
        b_end = args["period_b_end"]
    except KeyError as e:
        return {"error": f"Missing required argument: {e}"}

    account_ids = args.get("account_ids")
    period_a = _fetch_net(client, a_start, a_end, account_ids)
    if "error" in period_a:
        return period_a
    period_b = _fetch_net(client, b_start, b_end, account_ids)
    if "error" in period_b:
        return period_b

    def _delta(key: str) -> dict:
        a = Decimal(period_a[key])
        b = Decimal(period_b[key])
        absolute = b - a
        percent = (absolute / a * 100) if a != 0 else None
        return {
            "absolute": str(absolute),
            "percent": str(percent.quantize(Decimal("0.01"))) if percent is not None else None,
        }

    return {
        "period_a": period_a,
        "period_b": period_b,
        "delta": {
            "income": _delta("total_income"),
            "expenses": _delta("total_expenses"),
            "net": _delta("net"),
        },
    }


_HANDLERS: dict = {
    "list_transactions": _handler_list_transactions,
    "get_transactions_by_date_range": _handler_get_transactions_by_date_range,
    "search_transactions": _handler_search_transactions,
    "update_transaction_tags": _handler_update_transaction_tags,
    "update_transaction_category": _handler_update_transaction_category,
    "list_accounts": _handler_list_accounts,
    "get_expense_insights": _handler_get_expense_insights,
    "get_income_insights": _handler_get_income_insights,
    "list_categories": _handler_list_categories,
    "list_tags": _handler_list_tags,
    "sum_transactions": _handler_sum_transactions,
    "calculate_net": _handler_calculate_net,
    "compare_periods": _handler_compare_periods,
}


def dispatch(client: FireflyClient, tool_name: str, args: dict) -> dict:
    """Route a tool call to its handler and return the result.

    Args:
        client: Authenticated FireflyClient instance.
        tool_name: Name of the tool to invoke (must match a key in ``_HANDLERS``).
        args: Parsed tool arguments dict (from ``json.loads(tool_call.function.arguments)``).

    Returns:
        Handler result dict, or ``{"error": "Unknown tool: <name>"}`` for unknown tools.
    """
    handler = _HANDLERS.get(tool_name)
    if handler is None:
        return {"error": f"Unknown tool: {tool_name}"}
    return handler(client, args)


def get_tools() -> list:
    """Return the list of OpenAI function-calling tool schemas.

    Pass the result directly to ``openai.chat.completions.create(tools=get_tools())``.
    """
    return TOOLS
