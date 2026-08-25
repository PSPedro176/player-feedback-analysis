"""Jogos monitorados — agora dinâmicos, lidos do cadastro no Lakebase.

A UI recebe {name, package, icon, accent}. O ícone é servido do Volume via
`/api/logo/{package}`. Cache curto (TTL) para não bater no Postgres a cada request.
"""
import time
from urllib.parse import quote

from . import lakebase

# Paleta de acentos (só decorativa) ciclada por ordem de cadastro.
_ACCENTS = ["#FF4D6D", "#4DD0FF", "#FFB84D", "#7CFF4D", "#B980FF", "#4DFFC3"]

_CACHE: dict = {"ts": 0.0, "games": []}
_TTL_S = 15.0


def _build(rows: list[dict]) -> list[dict]:
    out = []
    for i, r in enumerate(rows):
        pkg = r["package"]
        out.append({
            "name": r["name"],
            "package": pkg,
            "icon": f"/api/logo/{quote(pkg, safe='')}",
            "accent": _ACCENTS[i % len(_ACCENTS)],
        })
    return out


def list_games_meta() -> list[dict]:
    """Lista de jogos com metadados para a UI (cacheada por _TTL_S).

    Resiliente: se o Lakebase ainda não estiver acessível (deploy recém-feito,
    tabela não criada), retorna [] em vez de estourar — a UI mostra o estado
    "nenhum jogo monitorado". Não cacheia a falha (tenta de novo no próximo request).
    """
    now = time.time()
    if now - _CACHE["ts"] > _TTL_S:
        try:
            _CACHE["games"] = _build(lakebase.list_games())
            _CACHE["ts"] = now
        except Exception as e:  # noqa: BLE001
            print(f"[games] list_games falhou (retornando vazio): {e}")
            return []
    return _CACHE["games"]


def game_names() -> list[str]:
    return [g["name"] for g in list_games_meta()]


def invalidate_cache() -> None:
    _CACHE["ts"] = 0.0
