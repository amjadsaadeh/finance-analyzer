"""Integration tests for tools.py against a real Firefly III instance.

Two ways to run:

  # Spin up Docker automatically (requires Docker + docker compose):
  uv run pytest tests/test_integration.py --run-integration

  # Point at an already-running instance:
  FIREFLY_TEST_URL=http://localhost:8080/api \\
  FIREFLY_TEST_TOKEN=<pat> \\
  uv run pytest tests/test_integration.py
"""

import datetime
import os
import re
import subprocess
import time
import uuid

import pytest

from tools import FireflyClient, dispatch

pytestmark = pytest.mark.integration

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_COMPOSE_FILE = os.path.join(os.path.dirname(__file__), "docker-compose.firefly.yml")
_PORT = 18080

# PHP script written into the container to mint a PAT without tinker
_TOKEN_SCRIPT = """\
<?php
define('LARAVEL_START', microtime(true));
require '/var/www/html/vendor/autoload.php';
$app = require_once '/var/www/html/bootstrap/app.php';
$app->make(Illuminate\\Contracts\\Console\\Kernel::class)->bootstrap();
$user = \\FireflyIII\\User::where('email', 'admin@inttest.local')->firstOrFail();
$tok = $user->createToken('ci-test');
// JWT token is the last token in stdout; log noise goes to stderr via LOG_CHANNEL
file_put_contents('php://stderr', '');
echo $tok->accessToken;
"""


# ---------------------------------------------------------------------------
# Docker / environment lifecycle
# ---------------------------------------------------------------------------

def _compose(project: str, *args) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["docker", "compose", "-f", _COMPOSE_FILE, "-p", project, *args],
        check=True,
        capture_output=True,
    )


def _wait_healthy(project: str, service: str, timeout: int = 180) -> None:
    """Block until the named compose service reports 'healthy'."""
    container = f"{project}-{service}-1"
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = subprocess.run(
            ["docker", "inspect", container, "--format", "{{.State.Health.Status}}"],
            capture_output=True,
        )
        if result.stdout.decode().strip() == "healthy":
            return
        time.sleep(3)
    raise TimeoutError(
        f"Container {container} did not become healthy within {timeout}s"
    )


def _bootstrap_token(project: str) -> str:
    """
    Prepare the Firefly III container for testing and return a Bearer JWT.

    Steps:
      1. Create the first admin user via built-in artisan command.
      2. Create a Passport personal-access client (needed for createToken()).
      3. Run a small PHP bootstrap script to mint and print the token.
    """
    def _exec(*cmd) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["docker", "compose", "-f", _COMPOSE_FILE, "-p", project,
             "exec", "-T", "firefly_app", *cmd],
            capture_output=True,
            timeout=60,
        )

    # Step 1: create first admin user (only works in APP_ENV=testing)
    r = _exec("php", "artisan", "system:create-first-user", "admin@inttest.local")
    if r.returncode != 0 and b"already exists" not in r.stderr:
        raise RuntimeError(f"create-first-user failed:\n{r.stderr.decode()[:500]}")

    # Step 2: create user group membership (required in Firefly III v6)
    _exec("php", "artisan", "correction:create-group-memberships")
    _exec("php", "artisan", "correction:preferences")

    # Step 3: create personal access OAuth client (idempotent)
    _exec("php", "artisan", "passport:client",
          "--personal", "--name=ci-client", "--no-interaction")

    # Step 4: write the token-minting script into the container via base64
    import base64
    php_b64 = base64.b64encode(_TOKEN_SCRIPT.encode()).decode()
    _exec("bash", "-c", f"echo '{php_b64}' | base64 -d > /tmp/make_token.php")
    result = _exec("php", "/tmp/make_token.php")

    # The JWT starts with eyJ; extract it from combined output
    combined = result.stdout.decode() + result.stderr.decode()
    m = re.search(r"(eyJ[A-Za-z0-9_.-]+)", combined)
    if not m:
        raise RuntimeError(
            f"Could not find JWT in make_token.php output.\n"
            f"stdout: {result.stdout.decode()[:800]}\n"
            f"stderr: {result.stderr.decode()[:800]}"
        )
    return m.group(1)


@pytest.fixture(scope="session")
def firefly_env():
    """Yield (base_url, api_token) for a live Firefly III instance."""
    ext_url = os.environ.get("FIREFLY_TEST_URL", "").rstrip("/")
    ext_tok = os.environ.get("FIREFLY_TEST_TOKEN", "")
    if ext_url and ext_tok:
        yield ext_url, ext_tok
        return

    project = f"ffinttest{uuid.uuid4().hex[:8]}"
    try:
        _compose(project, "up", "-d")
        _wait_healthy(project, "firefly_app")
        token = _bootstrap_token(project)
        yield f"http://localhost:{_PORT}", token
    finally:
        subprocess.run(
            ["docker", "compose", "-f", _COMPOSE_FILE, "-p", project, "down", "-v"],
            check=False,
            capture_output=True,
        )


@pytest.fixture(scope="session")
def ff_client(firefly_env):
    base_url, token = firefly_env
    # Firefly III API lives under /api
    api_base = base_url.rstrip("/")
    if not api_base.endswith("/api"):
        api_base = f"{api_base}/api"
    return FireflyClient(base_url=api_base, api_token=token)


# ---------------------------------------------------------------------------
# Fixture data
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def seed(ff_client):
    """Create accounts, categories, and transactions; return a dict of their IDs."""
    from firefly_iii_client.api import AccountsApi, TransactionsApi
    from firefly_iii_client.models import (
        AccountRoleProperty,
        AccountStore,
        ShortAccountTypeProperty,
        TransactionSplitStore,
        TransactionStore,
        TransactionTypeProperty,
    )

    acc_api = AccountsApi(ff_client.api_client)
    tx_api = TransactionsApi(ff_client.api_client)

    # --- accounts ---
    checking = acc_api.store_account(
        AccountStore(
            name="IT Checking",
            type=ShortAccountTypeProperty("asset"),
            account_role=AccountRoleProperty("defaultAsset"),
            currency_code="EUR",
        )
    ).data

    acc_api.store_account(
        AccountStore(
            name="IT Employer",
            type=ShortAccountTypeProperty("revenue"),
            currency_code="EUR",
        )
    )

    acc_api.store_account(
        AccountStore(
            name="IT Supermarket",
            type=ShortAccountTypeProperty("expense"),
            currency_code="EUR",
        )
    )

    # --- transactions ---
    # Withdrawal: Groceries — has category + tags (for tag/category/insight tests)
    tx_groceries = tx_api.store_transaction(
        TransactionStore(
            transactions=[
                TransactionSplitStore(
                    type=TransactionTypeProperty("withdrawal"),
                    var_date=datetime.datetime(2024, 1, 15),
                    amount="50.00",
                    description="IT Groceries run",
                    source_id=str(checking.id),
                    destination_name="IT Supermarket",
                    category_name="IT Food",
                    tags=["integration", "groceries"],
                    currency_code="EUR",
                )
            ]
        )
    ).data

    # Deposit: Salary — has category (for income insight tests)
    tx_salary = tx_api.store_transaction(
        TransactionStore(
            transactions=[
                TransactionSplitStore(
                    type=TransactionTypeProperty("deposit"),
                    var_date=datetime.datetime(2024, 1, 1),
                    amount="3000.00",
                    description="IT Monthly salary",
                    source_name="IT Employer",
                    destination_id=str(checking.id),
                    category_name="IT Income",
                    currency_code="EUR",
                )
            ]
        )
    ).data

    # Withdrawal: Transport — no category/tags initially (used by update tests)
    tx_transport = tx_api.store_transaction(
        TransactionStore(
            transactions=[
                TransactionSplitStore(
                    type=TransactionTypeProperty("withdrawal"),
                    var_date=datetime.datetime(2024, 1, 10),
                    amount="25.00",
                    description="IT Bus pass",
                    source_id=str(checking.id),
                    destination_name="IT Supermarket",
                    currency_code="EUR",
                )
            ]
        )
    ).data

    return {
        "checking_id": str(checking.id),
        "tx_groceries_id": str(tx_groceries.id),
        "tx_salary_id": str(tx_salary.id),
        "tx_transport_id": str(tx_transport.id),
    }


# ---------------------------------------------------------------------------
# Read-only tool tests
# ---------------------------------------------------------------------------

def test_list_transactions(ff_client, seed):
    result = dispatch(ff_client, "list_transactions", {"limit": 50})
    assert "transactions" in result
    assert len(result["transactions"]) >= 3


def test_get_transactions_by_date_range(ff_client, seed):
    result = dispatch(ff_client, "get_transactions_by_date_range", {
        "start_date": "2024-01-01",
        "end_date": "2024-01-31",
    })
    assert "transactions" in result
    descriptions = [
        split["description"]
        for tx in result["transactions"]
        for split in tx.get("attributes", {}).get("transactions", [])
    ]
    assert any("IT" in d for d in descriptions)


def test_get_transactions_by_date_range_excludes_other_months(ff_client, seed):
    result = dispatch(ff_client, "get_transactions_by_date_range", {
        "start_date": "2024-02-01",
        "end_date": "2024-02-29",
    })
    assert "transactions" in result
    assert result["transactions"] == []


def test_search_transactions(ff_client, seed):
    result = dispatch(ff_client, "search_transactions", {"query": "IT Groceries"})
    assert "transactions" in result
    assert len(result["transactions"]) >= 1
    descriptions = [
        split["description"]
        for tx in result["transactions"]
        for split in tx.get("attributes", {}).get("transactions", [])
    ]
    assert any("IT Groceries" in d for d in descriptions)


def test_list_accounts(ff_client, seed):
    result = dispatch(ff_client, "list_accounts", {})
    assert "accounts" in result
    names = [a.get("attributes", {}).get("name", "") for a in result["accounts"]]
    assert "IT Checking" in names


def test_list_accounts_type_filter(ff_client, seed):
    result = dispatch(ff_client, "list_accounts", {"account_type": "asset"})
    assert "accounts" in result
    types = [a.get("attributes", {}).get("type", "") for a in result["accounts"]]
    assert all(t == "asset" for t in types)


def test_get_expense_insights(ff_client, seed):
    result = dispatch(ff_client, "get_expense_insights", {
        "start_date": "2024-01-01",
        "end_date": "2024-01-31",
    })
    assert "insights" in result
    names = [i.get("name", "") for i in result["insights"]]
    assert "IT Food" in names


def test_get_income_insights(ff_client, seed):
    result = dispatch(ff_client, "get_income_insights", {
        "start_date": "2024-01-01",
        "end_date": "2024-01-31",
    })
    assert "insights" in result
    names = [i.get("name", "") for i in result["insights"]]
    assert "IT Income" in names


def test_list_categories(ff_client, seed):
    result = dispatch(ff_client, "list_categories", {})
    assert "categories" in result
    names = [c.get("attributes", {}).get("name", "") for c in result["categories"]]
    assert "IT Food" in names
    assert "IT Income" in names


def test_list_tags(ff_client, seed):
    result = dispatch(ff_client, "list_tags", {})
    assert "tags" in result
    tag_names = [t.get("attributes", {}).get("tag", "") for t in result["tags"]]
    assert "integration" in tag_names
    assert "groceries" in tag_names


def test_calculate_net(ff_client, seed):
    result = dispatch(ff_client, "calculate_net", {
        "start_date": "2024-01-01",
        "end_date": "2024-01-31",
    })
    assert "error" not in result
    assert "net" in result
    # Income (3000) > expenses (50 groceries; transport has no category so not in insights)
    assert float(result["total_income"]) > 0
    assert float(result["total_expenses"]) > 0
    assert float(result["net"]) > 0


def test_compare_periods(ff_client, seed):
    result = dispatch(ff_client, "compare_periods", {
        "period_a_start": "2024-01-01",
        "period_a_end": "2024-01-31",
        "period_b_start": "2024-02-01",
        "period_b_end": "2024-02-29",
    })
    assert "error" not in result
    assert "period_a" in result and "period_b" in result and "delta" in result
    # Period A has income; period B has none → income delta is negative
    assert float(result["period_a"]["total_income"]) > 0
    assert float(result["period_b"]["total_income"]) == 0.0


# ---------------------------------------------------------------------------
# Write tool tests (use tx_transport which starts with no tags/category)
# ---------------------------------------------------------------------------

def test_update_transaction_tags(ff_client, seed):
    result = dispatch(ff_client, "update_transaction_tags", {
        "transaction_id": seed["tx_transport_id"],
        "tags": ["transit", "monthly"],
    })
    assert "error" not in result
    # Verify the tags were persisted
    splits = result.get("attributes", {}).get("transactions", [])
    assert splits, "Expected at least one split in the response"
    assert set(splits[0].get("tags", [])) == {"transit", "monthly"}


def test_update_transaction_category(ff_client, seed):
    result = dispatch(ff_client, "update_transaction_category", {
        "transaction_id": seed["tx_transport_id"],
        "category_name": "IT Transport",
    })
    assert "error" not in result
    splits = result.get("attributes", {}).get("transactions", [])
    assert splits, "Expected at least one split in the response"
    assert splits[0].get("category_name") == "IT Transport"
