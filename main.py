"""Uvicorn entry point for the Finance Analyzer chat server.

Run with:
    uv run python main.py
or:
    uv run uvicorn src.app:app --reload

Environment variables (set in .env file or shell):
    OPENAI_API_KEY      — Required. Your OpenAI API key.
    OPENAI_BASE_URL     — Optional. Override the OpenAI API endpoint
                          (e.g. for OpenAI-compatible providers).
    FIREFLY_BASE_URL    — Required. Your Firefly III API base URL.
    FIREFLY_API_TOKEN   — Required. Your Firefly III personal access token.
"""

import logging
import os

from dotenv import load_dotenv

# Load .env file before anything else so all modules can read env vars.
# override=False means shell env vars take precedence over .env values.
load_dotenv(override=False)

# Configure logging so application log messages appear in the console.
logging.basicConfig(
    level=logging.DEBUG,
    format="%(levelname)s:%(name)s:%(message)s",
)

import uvicorn  # noqa: E402


def main():
    """Start the Finance Analyzer server with auto-reload for development."""
    # Validate required env vars early so the user sees a clear error
    # instead of cryptic failures later.
    missing = []
    if not os.environ.get("OPENAI_API_KEY"):
        missing.append("OPENAI_API_KEY")
    if not os.environ.get("FIREFLY_BASE_URL"):
        missing.append("FIREFLY_BASE_URL")
    if not os.environ.get("FIREFLY_API_TOKEN"):
        missing.append("FIREFLY_API_TOKEN")
    if missing:
        print(f"Missing required environment variables: {', '.join(missing)}")
        print("Create a .env file or set them in your shell.")
        print("See .env.example for details.")
        raise SystemExit(1)

    uvicorn.run(
        "src.app:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="debug",
    )


if __name__ == "__main__":
    main()