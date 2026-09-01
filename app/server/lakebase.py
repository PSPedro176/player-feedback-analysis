"""Acesso ao Lakebase (Postgres) — cadastro de jogos monitorados (OLTP).

O App grava/remove jogos aqui; o Lakebase CDF materializa as mudanças numa tabela
Delta no UC (`lb_games_history`), da qual deriva a view `games_current` que os jobs leem.

A conexão usa o service principal do App (permissão concedida pelo binding `postgres`
do App, em resources/pf_frontend.yml): host do endpoint + token OAuth de curta duração
gerados via SDK. O role Postgres do SP é criado pelo pf_setup.
"""
import os
from functools import lru_cache

import psycopg2

from .config import get_workspace_client

# Lakebase Autoscaling — o cadastro vive aqui (CDF exige este tier). Branch e database são os
# auto-criados pelo projeto; o endpoint tem id auto-gerado e é descoberto via list_endpoints.
LAKEBASE_PROJECT = os.environ.get("LAKEBASE_PROJECT", "pf-games")
LAKEBASE_BRANCH = os.environ.get("LAKEBASE_BRANCH", "production")
LAKEBASE_DATABASE = os.environ.get("LAKEBASE_DATABASE", "databricks_postgres")

_BRANCH_PATH = f"projects/{LAKEBASE_PROJECT}/branches/{LAKEBASE_BRANCH}"


@lru_cache(maxsize=1)
def _endpoint_path() -> str:
    from databricks.sdk.service import postgres as pg

    w = get_workspace_client()
    eps = list(w.postgres.list_endpoints(parent=_BRANCH_PATH))
    rw = [e for e in eps
          if e.spec and e.spec.endpoint_type == pg.EndpointType.ENDPOINT_TYPE_READ_WRITE]
    return (rw or eps)[0].name


@lru_cache(maxsize=1)
def _host() -> str:
    w = get_workspace_client()
    return w.postgres.get_endpoint(name=_endpoint_path()).status.hosts.host


def _connect():
    """Conexão psycopg2 nova ao endpoint Autoscaling (token OAuth é curto — reconecta por operação).

    O App conecta com a identidade do service principal (role Postgres criado no pf_setup)
    e um token OAuth gerado para o endpoint descoberto.
    """
    w = get_workspace_client()
    token = w.postgres.generate_database_credential(endpoint=_endpoint_path()).token
    user = w.current_user.me().user_name
    conn = psycopg2.connect(
        host=_host(), port=5432, dbname=LAKEBASE_DATABASE,
        user=user, password=token, sslmode="require",
    )
    conn.autocommit = True
    return conn


def ensure_games_table() -> None:
    """Cria a tabela de cadastro se ainda não existir (idempotente). Chamado no startup."""
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS public.games (
                package_name text PRIMARY KEY,
                game         text NOT NULL,
                active       boolean NOT NULL DEFAULT true,
                added_at     timestamptz NOT NULL DEFAULT now()
            )
            """
        )
        # REPLICA IDENTITY só pode ser alterado pelo dono da tabela. Se a tabela foi
        # criada pelo pf_setup (outro role), ignoramos — o setup já cuidou disso.
        try:
            cur.execute("ALTER TABLE public.games REPLICA IDENTITY FULL")
        except Exception as e:  # noqa: BLE001
            print(f"[lakebase] ALTER REPLICA IDENTITY ignorado (não é dono): {e}")


def list_games() -> list[dict]:
    """Jogos ativos cadastrados (fonte imediata para a UI — sem lag de CDF)."""
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT game, package_name FROM public.games WHERE active ORDER BY game"
        )
        return [{"name": g, "package": p} for g, p in cur.fetchall()]


def add_games(items: list[dict]) -> int:
    """Insere/reativa vários jogos de uma vez. `items` = [{name, package}, ...]."""
    rows = [
        (i["package"].strip(), i["name"].strip())
        for i in items
        if i.get("package", "").strip() and i.get("name", "").strip()
    ]
    if not rows:
        return 0
    with _connect() as conn, conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO public.games (package_name, game, active)
            VALUES (%s, %s, true)
            ON CONFLICT (package_name)
            DO UPDATE SET game = EXCLUDED.game, active = true
            """,
            rows,
        )
    return len(rows)


def remove_game(package: str) -> None:
    """Remove um jogo do cadastro (delete real → CDF propaga a remoção)."""
    with _connect() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM public.games WHERE package_name = %s", (package,))
