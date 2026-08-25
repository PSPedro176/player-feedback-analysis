"""Rotas de API: config de embeds, gestão de jogos, KPIs, relatórios e coleta."""
import time

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from ..config import (
    GAMES_CURRENT_TABLE,
    INGEST_JOB_ID,
    LOGOS_VOLUME_PATH,
    REPORTS_TABLE,
    REVIEWS_TABLE,
    get_dashboard_embed_url,
    get_dashboard_id,
    get_workspace_client,
    get_workspace_host,
)
from .. import games as games_mod
from .. import lakebase
from ..sql import run_query

router = APIRouter()


# --------------------------------------------------------------------------- #
# Config e jogos
# --------------------------------------------------------------------------- #
@router.get("/config")
def config():
    """Config pública para o frontend (embed do dashboard + jogos cadastrados)."""
    return {
        "host": get_workspace_host(),
        "dashboard_id": get_dashboard_id(),
        "dashboard_embed_url": get_dashboard_embed_url(),
        "games": games_mod.list_games_meta(),
    }


@router.get("/games")
def games():
    return games_mod.list_games_meta()


class GameIn(BaseModel):
    name: str
    package: str


@router.post("/games")
def add_games(items: list[GameIn]):
    """Adiciona vários jogos de uma vez ao cadastro (Lakebase)."""
    n = lakebase.add_games([i.model_dump() for i in items])
    games_mod.invalidate_cache()
    return {"added": n}


@router.delete("/games/{package}")
def remove_game(package: str):
    lakebase.remove_game(package)
    games_mod.invalidate_cache()
    return {"removed": package}


@router.get("/logo/{package}")
def logo(package: str):
    """Stream do logo do jogo a partir do Volume (fallback 404 → UI mostra inicial)."""
    w = get_workspace_client()
    try:
        resp = w.files.download(f"{LOGOS_VOLUME_PATH}/{package}.png")
        data = resp.contents.read()
    except Exception:
        raise HTTPException(status_code=404, detail="Logo não encontrado")
    return Response(content=data, media_type="image/png")


# --------------------------------------------------------------------------- #
# Coleta sob demanda
# --------------------------------------------------------------------------- #
@router.post("/jobs/collect/run")
def run_collect():
    """Dispara UMA coleta cobrindo todos os jogos.

    Garante o Ponto 1: espera o CDF refletir em `games_current` todos os jogos ativos do
    Postgres (timeout ~60s; CDF batcha ~15s) antes de disparar o job — senão a extração
    leria o cadastro sem os jogos recém-adicionados.
    """
    if not INGEST_JOB_ID:
        raise HTTPException(status_code=500, detail="INGEST_JOB_ID não configurado")

    active = {g["package"] for g in lakebase.list_games()}
    deadline = time.time() + 60
    while active:
        try:
            present = {
                r["package_name"]
                for r in run_query(
                    f"SELECT package_name FROM {GAMES_CURRENT_TABLE} WHERE active"
                )
            }
        except Exception:
            present = set()
        if active.issubset(present):
            break
        if time.time() > deadline:
            break
        time.sleep(5)

    w = get_workspace_client()
    run = w.jobs.run_now(job_id=int(INGEST_JOB_ID))
    run_id = run.run_id if hasattr(run, "run_id") else run.response.run_id
    run_url = f"{get_workspace_host()}/jobs/{INGEST_JOB_ID}/runs/{run_id}"
    return {"run_id": run_id, "run_url": run_url}


# --------------------------------------------------------------------------- #
# Analytics (lidos ao vivo das tabelas Delta via SQL Warehouse)
# --------------------------------------------------------------------------- #
def _safe_query(statement: str, parameters=None) -> list[dict]:
    """run_query resiliente: se a tabela ainda não existe (deploy sem coleta/enriquecimento
    ainda), retorna [] em vez de 500 — a UI renderiza o estado vazio."""
    try:
        return run_query(statement, parameters)
    except Exception as e:  # noqa: BLE001
        print(f"[api] query ignorada (tabela ainda ausente?): {e}")
        return []


@router.get("/overview")
def overview():
    trow = _safe_query(
        f"SELECT count(*) AS total_reviews, round(avg(score), 2) AS avg_score FROM {REVIEWS_TABLE}"
    )
    totals = {
        "total_reviews": (trow[0].get("total_reviews") if trow else 0) or 0,
        "avg_score": (trow[0].get("avg_score") if trow else 0.0) or 0.0,
    }
    per_game = _safe_query(
        f"""
        SELECT game, count(*) AS reviews, round(avg(score), 2) AS avg_score
        FROM {REVIEWS_TABLE}
        GROUP BY game
        """
    )
    sentiment_by_game = _safe_query(
        f"""
        SELECT game, sentiment, count(*) AS n
        FROM {REVIEWS_TABLE}
        WHERE sentiment IS NOT NULL
        GROUP BY game, sentiment
        """
    )
    return {"totals": totals, "per_game": per_game, "sentiment_by_game": sentiment_by_game}


@router.get("/reports")
def reports():
    """Relatório semanal mais recente de cada jogo."""
    rows = _safe_query(
        f"""
        WITH ranked AS (
            SELECT
                game, report_week, grade, report, n_reviews,
                round(avg_score, 2) AS avg_score, window_start, window_end, _generated_at,
                row_number() OVER (PARTITION BY game ORDER BY report_week DESC) AS rn
            FROM {REPORTS_TABLE}
        )
        SELECT game, report_week, grade, report, n_reviews, avg_score,
               window_start, window_end, _generated_at
        FROM ranked
        WHERE rn = 1
        ORDER BY game
        """
    )
    order = {name: i for i, name in enumerate(games_mod.game_names())}
    rows.sort(key=lambda r: order.get(r["game"], 99))
    return rows


@router.get("/reviews/{game}")
def recent_reviews(game: str, limit: int = 8):
    if game not in games_mod.game_names():
        raise HTTPException(status_code=404, detail="Jogo desconhecido")
    return _safe_query(
        f"""
        SELECT review_id, user_name, content, score, sentiment,
               bug_report, at, language
        FROM {REVIEWS_TABLE}
        WHERE game = :game AND content IS NOT NULL AND length(content) > 20
        ORDER BY at DESC
        LIMIT {int(limit)}
        """,
        parameters=[{"name": "game", "value": game}],
    )
