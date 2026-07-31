"""Rotas de API: config de embeds, jogos, KPIs de overview e relatórios."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..config import (
    DASHBOARD_ID,
    REPORTS_TABLE,
    REVIEWS_TABLE,
    get_workspace_host,
)
from ..games import (
    add_game,
    get_game_names,
    get_games,
    list_configured_games,
    remove_game,
    trigger_ingestion,
)
from ..sql import run_query

router = APIRouter()


@router.get("/config")
def config():
    """Config pública para o frontend montar a URL de embed do dashboard.

    O Genie é acessado nativamente dentro do próprio AI/BI Dashboard, então o
    App não embeda um Genie space separado.
    """
    host = get_workspace_host()
    return {
        "host": host,
        "dashboard_id": DASHBOARD_ID,
        "dashboard_embed_url": f"{host}/embed/dashboardsv3/{DASHBOARD_ID}",
        "games": get_games(),
    }


@router.get("/games")
def games():
    return get_games()


@router.get("/overview")
def overview():
    """KPIs lidos ao vivo das tabelas Delta via SQL Warehouse."""
    totals = run_query(
        f"""
        SELECT
            count(*) AS total_reviews,
            round(avg(score), 2) AS avg_score
        FROM {REVIEWS_TABLE}
        """
    )[0]

    per_game = run_query(
        f"""
        SELECT
            game,
            count(*) AS reviews,
            round(avg(score), 2) AS avg_score
        FROM {REVIEWS_TABLE}
        GROUP BY game
        """
    )

    # Sentimento QUEBRADO POR JOGO (linhas game x sentiment).
    sentiment_by_game = run_query(
        f"""
        SELECT game, sentiment, count(*) AS n
        FROM {REVIEWS_TABLE}
        WHERE sentiment IS NOT NULL
        GROUP BY game, sentiment
        """
    )

    return {
        "totals": totals,
        "per_game": per_game,
        "sentiment_by_game": sentiment_by_game,
    }


@router.get("/reports")
def reports():
    """Relatório semanal mais recente de cada jogo."""
    rows = run_query(
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
    # Ordenar conforme a ordem canônica dos jogos.
    order = {name: i for i, name in enumerate(get_game_names())}
    rows.sort(key=lambda r: order.get(r["game"], 99))
    return rows


@router.get("/reviews/{game}")
def recent_reviews(game: str, limit: int = 8):
    """Amostra de reviews recentes de um jogo (para dar textura à página)."""
    if game not in get_game_names():
        raise HTTPException(status_code=404, detail="Jogo desconhecido")
    return run_query(
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


# --- Gerenciamento de jogos monitorados (tela "Gerenciar") -------------------


class AddGamePayload(BaseModel):
    package: str


@router.get("/games/config")
def games_config():
    """Jogos configurados via UI (games_config) — para a tela de gerenciamento."""
    return list_configured_games()


@router.post("/games")
def create_game(payload: AddGamePayload):
    """Adiciona um jogo pelo package name da Play Store e dispara a ingestão.

    Valida o package na Play Store (captura nome/ícone), grava em games_config
    + games_meta e dispara o job de ingestão. Retorna o jogo criado e se o job
    foi disparado.
    """
    package = payload.package.strip()
    if not package:
        raise HTTPException(status_code=400, detail="Package name vazio.")
    try:
        game = add_game(package)
    except ValueError as e:
        # Package inexistente / inválido na Play Store.
        raise HTTPException(status_code=422, detail=str(e))
    run = trigger_ingestion()
    return {"game": game, "ingestion_run_id": run}


@router.delete("/games/{game}")
def delete_game(game: str):
    """Remove um jogo do monitoramento (games_config). Dados históricos ficam."""
    removed = remove_game(game)
    if not removed:
        raise HTTPException(
            status_code=404,
            detail="Jogo não encontrado na configuração da UI (pode vir do bundle).",
        )
    return {"removed": game}
