"""Uvicorn entry point for the Finance Analyzer chat server.

Run with:
    uv run python main.py
or:
    uv run uvicorn src.app:app --reload
"""

import uvicorn


def main():
    """Start the Finance Analyzer server with auto-reload for development."""
    uvicorn.run("src.app:app", host="0.0.0.0", port=8000, reload=True)


if __name__ == "__main__":
    main()