import os
import datetime

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
