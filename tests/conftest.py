import os
import pytest


def pytest_addoption(parser):
    parser.addoption(
        "--run-integration",
        action="store_true",
        default=False,
        help="Run integration tests that spin up Firefly III via Docker",
    )


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "integration: integration tests that require a live Firefly III instance (Docker or env vars)",
    )


def pytest_collection_modifyitems(config, items):
    run_docker = config.getoption("--run-integration", default=False)
    has_env = bool(os.environ.get("FIREFLY_TEST_URL") and os.environ.get("FIREFLY_TEST_TOKEN"))
    if run_docker or has_env:
        return
    skip = pytest.mark.skip(
        reason="integration test: pass --run-integration or set FIREFLY_TEST_URL + FIREFLY_TEST_TOKEN"
    )
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip)
