"""Lista de jogos monitorados — derivada dinamicamente das tabelas.

A fonte de verdade sobre QUAIS jogos existem é a própria tabela enriquecida:
os jogos são configurados na variável `games` de databricks.yml, extraídos da
Play Store pelo job de ingestão e gravados em `reviews_enriched.game`. Este
módulo lê os valores distintos dessa coluna e faz LEFT JOIN com `games_meta`
(ícone/título oficiais da Play Store, também populados na ingestão), para que o
App reflita automaticamente qualquer conjunto de jogos configurado — com a logo
de cada um — sem hardcode.

O `accent` (cor de destaque) é determinístico por jogo (paleta cíclica). Se o
jogo ainda não tem ícone em `games_meta`, `icon` vem vazio e o frontend cai num
placeholder com a inicial do nome. Se a tabela ainda estiver vazia (antes da 1ª
ingestão), devolvemos um exemplo genérico só para a UI não quebrar.
"""
from google_play_scraper import app as play_app
from google_play_scraper.exceptions import NotFoundError

from .config import (
    CATALOG,
    GAMES_CONFIG_TABLE,
    GAMES_META_TABLE,
    INGEST_JOB_ID,
    REVIEWS_TABLE,
    SCHEMA,
    get_workspace_client,
)
from .sql import run_query

# Paleta de destaque (cíclica) aplicada por ordem alfabética dos jogos.
_ACCENTS = ["#FF4D6D", "#4DD0FF", "#FFC24D", "#7C4DFF", "#4DFFA6", "#FF7A4D"]

# Fallback usado apenas enquanto não há dados ingeridos.
_FALLBACK = [{"name": "Exemplo", "package": "", "icon": "", "accent": _ACCENTS[0]}]


def get_games() -> list[dict]:
    """Jogos monitorados, derivados de reviews_enriched + ícone de games_meta."""
    rows = run_query(
        f"""
        SELECT r.game AS game,
               coalesce(m.icon, '') AS icon,
               coalesce(m.package_name, '') AS package
        FROM (SELECT DISTINCT game FROM {REVIEWS_TABLE} WHERE game IS NOT NULL) r
        LEFT JOIN {GAMES_META_TABLE} m ON m.game = r.game
        ORDER BY r.game
        """
    )
    if not rows:
        return list(_FALLBACK)
    return [
        {
            "name": row["game"],
            "package": row["package"],
            "icon": row["icon"],
            "accent": _ACCENTS[i % len(_ACCENTS)],
        }
        for i, row in enumerate(rows)
    ]


def get_game_names() -> list[str]:
    """Nomes dos jogos monitorados (para validação e ordenação)."""
    return [g["name"] for g in get_games()]


# --- Gerenciamento de jogos (tela "Gerenciar") -------------------------------


def list_configured_games() -> list[dict]:
    """Jogos adicionados pela UI (tabela games_config), mais recente primeiro."""
    return run_query(
        f"""
        SELECT c.game AS name, c.package_name AS package, m.icon AS icon
        FROM {GAMES_CONFIG_TABLE} c
        LEFT JOIN {GAMES_META_TABLE} m ON m.game = c.game
        ORDER BY c._added_at DESC
        """
    )


def add_game(package: str) -> dict:
    """Valida o package na Play Store e grava em games_config + games_meta.

    Levanta ValueError se o package não existe na Play Store. Retorna o jogo
    criado ({name, package, icon}).
    """
    try:
        info = play_app(package)
    except NotFoundError:
        raise ValueError(f"Package '{package}' não encontrado na Play Store.")

    name = info["title"]
    icon = info["icon"]

    # Upsert em games_config (chave: game). Parametrizado para evitar injeção.
    run_query(
        f"""
        MERGE INTO {GAMES_CONFIG_TABLE} t
        USING (SELECT :game AS game, :pkg AS package_name) s
        ON t.game = s.game
        WHEN MATCHED THEN UPDATE SET package_name = s.package_name
        WHEN NOT MATCHED THEN
            INSERT (game, package_name, source, _added_at)
            VALUES (s.game, s.package_name, 'ui', current_timestamp())
        """,
        parameters=[{"name": "game", "value": name}, {"name": "pkg", "value": package}],
    )
    # Upsert do ícone/título em games_meta para a logo aparecer de imediato.
    run_query(
        f"""
        MERGE INTO {GAMES_META_TABLE} t
        USING (SELECT :game AS game, :pkg AS package_name,
                      :icon AS icon, :title AS title) s
        ON t.game = s.game
        WHEN MATCHED THEN UPDATE SET
            package_name = s.package_name, icon = s.icon, title = s.title
        WHEN NOT MATCHED THEN
            INSERT (game, package_name, icon, title, _updated_at)
            VALUES (s.game, s.package_name, s.icon, s.title, current_timestamp())
        """,
        parameters=[
            {"name": "game", "value": name},
            {"name": "pkg", "value": package},
            {"name": "icon", "value": icon},
            {"name": "title", "value": name},
        ],
    )
    return {"name": name, "package": package, "icon": icon}


def remove_game(game: str) -> bool:
    """Remove um jogo de games_config. Retorna True se algo foi removido.

    Dados históricos em reviews_raw/reviews_enriched permanecem intactos.
    """
    before = run_query(
        f"SELECT count(*) AS n FROM {GAMES_CONFIG_TABLE} WHERE game = :game",
        parameters=[{"name": "game", "value": game}],
    )[0]["n"]
    if before == 0:
        return False
    run_query(
        f"DELETE FROM {GAMES_CONFIG_TABLE} WHERE game = :game",
        parameters=[{"name": "game", "value": game}],
    )
    return True


def trigger_ingestion() -> int | None:
    """Dispara o job de ingestão+enriquecimento. Retorna o run_id, ou None se
    o job não estiver configurado (INGEST_JOB_ID vazio)."""
    if not INGEST_JOB_ID:
        return None
    w = get_workspace_client()
    run = w.jobs.run_now(job_id=int(INGEST_JOB_ID))
    return run.run_id
