"""Player Feedback Analysis — FastAPI entry point.

Backend serve a API (/api/*) e o frontend React buildado (frontend/dist).
"""
import os

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from server.routes.api import router as api_router

app = FastAPI(title="Player Feedback Analysis")

app.include_router(api_router, prefix="/api")


@app.on_event("startup")
def _startup():
    """Garante a tabela de cadastro no Lakebase (idempotente); não derruba o app se falhar."""
    try:
        from server import lakebase
        lakebase.ensure_games_table()
    except Exception as e:  # noqa: BLE001
        print(f"[startup] ensure_games_table falhou (seguindo mesmo assim): {e}")


@app.get("/api/health")
def health():
    return {"status": "ok"}


# --- Servir o frontend React buildado ---
FRONTEND_DIST = os.path.join(os.path.dirname(__file__), "frontend", "dist")

if os.path.isdir(FRONTEND_DIST):
    app.mount(
        "/assets",
        StaticFiles(directory=os.path.join(FRONTEND_DIST, "assets")),
        name="assets",
    )

    @app.get("/{full_path:path}")
    def serve_spa(full_path: str):
        if full_path.startswith("api/"):
            return JSONResponse({"detail": "Not found"}, status_code=404)
        candidate = os.path.join(FRONTEND_DIST, full_path)
        if full_path and os.path.isfile(candidate):
            return FileResponse(candidate)
        return FileResponse(os.path.join(FRONTEND_DIST, "index.html"))
