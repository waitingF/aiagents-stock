#!/usr/bin/env python3
"""Run the FastAPI backend and serve the built React frontend."""

from __future__ import annotations

import argparse
import importlib
import sys


REQUIRED_MODULES = [
    "fastapi",
    "uvicorn",
    "pandas",
    "plotly",
    "yfinance",
    "akshare",
    "openai",
]


def check_requirements() -> bool:
    missing = []
    for module_name in REQUIRED_MODULES:
        try:
            importlib.import_module(module_name)
        except ImportError:
            missing.append(module_name)
    if missing:
        print(f"Missing dependencies: {', '.join(missing)}")
        print("Run: pip install -r requirements.txt")
        return False
    return True


def check_config() -> None:
    import src.aiagents_stock.core.config as config

    if not config.DEEPSEEK_API_KEY:
        print("Warning: DEEPSEEK_API_KEY is not configured. AI analysis endpoints may fail.")


def main() -> int:
    parser = argparse.ArgumentParser(description="AI Agents Stock web server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8503)
    parser.add_argument("--reload", action="store_true")
    args = parser.parse_args()

    if not check_requirements():
        return 1
    check_config()

    from src.aiagents_stock.app.main import main as serve

    print(f"Serving FastAPI + React at http://{args.host}:{args.port}")
    serve(host=args.host, port=args.port, reload=args.reload)
    return 0


if __name__ == "__main__":
    sys.exit(main())
