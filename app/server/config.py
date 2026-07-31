"""Dual-mode auth: profile local, service principal no Databricks Apps."""
import os
from functools import lru_cache

from databricks.sdk import WorkspaceClient

# No Databricks Apps a env var DATABRICKS_APP_NAME é injetada automaticamente.
IS_DATABRICKS_APP = bool(os.environ.get("DATABRICKS_APP_NAME"))

# IDs / configs vindos do app.yaml (com defaults iguais aos do bundle).
WAREHOUSE_ID = os.environ.get("SQL_WAREHOUSE_ID", "TODO-preencher-com-seu-warehouse-id")
DASHBOARD_ID = os.environ.get("DASHBOARD_ID", "TODO-preencher-com-seu-dashboard-id")
CATALOG = os.environ.get("CATALOG", "player_feedback_catalog")
SCHEMA = os.environ.get("SCHEMA", "player_feedback")
# job_id do pf_ingest_and_enrich — para a tela "Gerenciar" disparar a ingestão
# ao adicionar um jogo. Vazio = botão de disparo desabilitado (app só salva).
INGEST_JOB_ID = os.environ.get("INGEST_JOB_ID", "")

REVIEWS_TABLE = f"{CATALOG}.{SCHEMA}.reviews_enriched"
REPORTS_TABLE = f"{CATALOG}.{SCHEMA}.weekly_reports"
GAMES_META_TABLE = f"{CATALOG}.{SCHEMA}.games_meta"
GAMES_CONFIG_TABLE = f"{CATALOG}.{SCHEMA}.games_config"


@lru_cache(maxsize=1)
def get_workspace_client() -> WorkspaceClient:
    """WorkspaceClient autenticado nos dois modos."""
    if IS_DATABRICKS_APP:
        # Remoto: usa as credenciais de service principal injetadas.
        return WorkspaceClient()
    # Local: usa o profile da CLI.
    profile = os.environ.get("DATABRICKS_PROFILE", "TODO-preencher-com-seu-profile-cli")
    return WorkspaceClient(profile=profile)


def get_workspace_host() -> str:
    """Host do workspace com prefixo https://."""
    if IS_DATABRICKS_APP:
        # No Apps DATABRICKS_HOST vem só como hostname, sem scheme.
        host = os.environ.get("DATABRICKS_HOST", "")
        if host and not host.startswith("http"):
            host = f"https://{host}"
        return host
    return get_workspace_client().config.host
