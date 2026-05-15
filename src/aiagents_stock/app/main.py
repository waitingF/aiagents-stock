"""Application entrypoint for the FastAPI + React frontend."""

from __future__ import annotations

import uvicorn

from src.aiagents_stock.api import create_app


app = create_app()


def main(
    host: str = "127.0.0.1",
    port: int = 8503,
    reload: bool = False,
    access_log: bool = False,
) -> None:
    uvicorn.run(
        "src.aiagents_stock.app.main:app",
        host=host,
        port=port,
        reload=reload,
        access_log=access_log,
    )


__all__ = ["app", "main"]


if __name__ == "__main__":
    main()
