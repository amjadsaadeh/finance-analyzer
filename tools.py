import os
import datetime

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
    def __init__(self, base_url: str = None, api_token: str = None):
        self.base_url = base_url or os.environ.get("FIREFLY_BASE_URL")
        self.api_token = api_token or os.environ.get("FIREFLY_API_TOKEN")
        if not self.base_url:
            raise ValueError("FIREFLY_BASE_URL must be set via env var or constructor argument")
        if not self.api_token:
            raise ValueError("FIREFLY_API_TOKEN must be set via env var or constructor argument")
        config = Configuration(host=self.base_url, access_token=self.api_token)
        self.api_client = ApiClient(configuration=config)


# Handlers and TOOLS defined in subsequent tasks.
_HANDLERS: dict = {}
TOOLS: list = []


def dispatch(client: FireflyClient, tool_name: str, args: dict) -> dict:
    handler = _HANDLERS.get(tool_name)
    if handler is None:
        return {"error": f"Unknown tool: {tool_name}"}
    return handler(client, args)


def get_tools() -> list:
    return TOOLS
