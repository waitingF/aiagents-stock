"""FastAPI application factory."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, Response
from fastapi.staticfiles import StaticFiles

from src.aiagents_stock.api.routes import router
from src.aiagents_stock.core.paths import PROJECT_ROOT, ensure_runtime_dirs
from src.aiagents_stock.infrastructure.network.proxy import disable_proxy_env


def create_app() -> FastAPI:
    disable_proxy_env()
    ensure_runtime_dirs()

    app = FastAPI(title="AI Agents Stock API", version="2.0.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(router)

    dist_dir = PROJECT_ROOT / "frontend" / "dist"
    assets_dir = dist_dir / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

    @app.websocket("/_stcore/stream")
    async def legacy_streamlit_websocket(websocket: WebSocket) -> None:
        """Close stale Streamlit browser tabs without noisy 403 logs."""

        await websocket.accept()
        await websocket.close(code=1000, reason="Streamlit frontend has been removed")

    @app.get("/_stcore/{full_path:path}", include_in_schema=False)
    def legacy_streamlit_http(full_path: str) -> Response:
        return Response(status_code=410, headers={"Cache-Control": "no-store"})

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str):
        index_html = dist_dir / "index.html"
        requested = _safe_dist_file(dist_dir, full_path)
        if requested and requested.is_file():
            return FileResponse(str(requested))
        if index_html.exists():
            return FileResponse(str(index_html))
        return HTMLResponse(
            "<html><body><h1>Frontend has not been built</h1>"
            "<p>Run <code>npm install</code> and <code>npm run build</code> in frontend/.</p>"
            "</body></html>",
            status_code=200,
        )

    return app


def _safe_dist_file(dist_dir: Path, path: str) -> Path | None:
    if not path:
        return None
    candidate = (dist_dir / path).resolve()
    try:
        candidate.relative_to(dist_dir.resolve())
    except ValueError:
        return None
    return candidate
