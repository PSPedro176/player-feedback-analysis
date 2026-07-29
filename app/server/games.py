"""Lista de jogos monitorados — derivada dinamicamente das tabelas.

A fonte de verdade sobre QUAIS jogos existem é a própria tabela enriquecida:
os jogos são configurados na variável `games` de databricks.yml, extraídos da
Play Store pelo job de ingestão e gravados em `reviews_enriched.game`. Este
módulo lê os valores distintos dessa coluna, para que o App reflita
automaticamente qualquer conjunto de jogos configurado — sem hardcode.

Como a tabela não guarda ícone/cor, atribuímos um `accent` determinístico por
jogo (paleta cíclica) e deixamos `icon` vazio (o frontend cai num placeholder
com a inicial do nome). Se a tabela ainda estiver vazia (antes da 1ª ingestão),
devolvemos um exemplo genérico só para a UI não quebrar.
"""
from .config import REVIEWS_TABLE
from .sql import run_query

# Paleta de destaque (cíclica) aplicada por ordem alfabética dos jogos.
_ACCENTS = ["#FF4D6D", "#4DD0FF", "#FFC24D", "#7C4DFF", "#4DFFA6", "#FF7A4D"]

# Fallback usado apenas enquanto não há dados ingeridos.
_FALLBACK = [{"name": "Exemplo", "package": "", "icon": "", "accent": _ACCENTS[0]}]


def get_games() -> list[dict]:
    """Jogos monitorados, derivados dos valores distintos em reviews_enriched."""
    rows = run_query(
        f"SELECT DISTINCT game FROM {REVIEWS_TABLE} WHERE game IS NOT NULL ORDER BY game"
    )
    if not rows:
        return list(_FALLBACK)
    return [
        {
            "name": row["game"],
            "package": "",
            "icon": "",
            "accent": _ACCENTS[i % len(_ACCENTS)],
        }
        for i, row in enumerate(rows)
    ]


def get_game_names() -> list[str]:
    """Nomes dos jogos monitorados (para validação e ordenação)."""
    return [g["name"] for g in get_games()]
