"""Config e auth. Dual-mode: profile local, service principal no Databricks Apps.

Todas as configs chegam por env injetada pelo bundle (resources.apps.pf_app.config.env):
IDs de recursos via referências automáticas do bundle.
"""
import os
from functools import lru_cache

from databricks.sdk import WorkspaceClient

# No Databricks Apps a env var DATABRICKS_APP_NAME é injetada automaticamente.
IS_DATABRICKS_APP = bool(os.environ.get("DATABRICKS_APP_NAME"))

# IDs / configs (defaults iguais aos do bundle; em produção vêm dos bindings).
WAREHOUSE_ID = os.environ.get("SQL_WAREHOUSE_ID", "")
INGEST_JOB_ID = os.environ.get("INGEST_JOB_ID", "")
DASHBOARD_ID = os.environ.get("DASHBOARD_ID", "")
CATALOG = os.environ.get("CATALOG", "player_feedback_catalog")
SCHEMA = os.environ.get("SCHEMA", "player_feedback")
GAME_LOGOS_VOLUME = os.environ.get("GAME_LOGOS_VOLUME", "game_logos")

REVIEWS_TABLE = f"{CATALOG}.{SCHEMA}.reviews_enriched"
REPORTS_TABLE = f"{CATALOG}.{SCHEMA}.weekly_reports"
GAMES_CURRENT_TABLE = f"{CATALOG}.{SCHEMA}.games_current"
LOGOS_VOLUME_PATH = f"/Volumes/{CATALOG}/{SCHEMA}/{GAME_LOGOS_VOLUME}"


@lru_cache(maxsize=1)
def get_workspace_client() -> WorkspaceClient:
    """WorkspaceClient autenticado nos dois modos."""
    if IS_DATABRICKS_APP:
        return WorkspaceClient()
    profile = os.environ.get("DATABRICKS_PROFILE", "TODO-preencher-com-seu-profile-cli")
    return WorkspaceClient(profile=profile)


def get_workspace_host() -> str:
    """Host do workspace com prefixo https://."""
    if IS_DATABRICKS_APP:
        host = os.environ.get("DATABRICKS_HOST", "")
        if host and not host.startswith("http"):
            host = f"https://{host}"
        return host
    return get_workspace_client().config.host


def get_dashboard_id() -> str:
    """ID do AI/BI Dashboard, injetado pelo bundle (${resources.dashboards.pf_dashboard.dashboard_id})."""
    return DASHBOARD_ID


def get_dashboard_embed_url() -> str:
    if not DASHBOARD_ID:
        return ""
    return f"{get_workspace_host()}/embed/dashboardsv3/{DASHBOARD_ID}"
