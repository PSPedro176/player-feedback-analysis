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
from .config import GAMES_META_TABLE, REVIEWS_TABLE
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
