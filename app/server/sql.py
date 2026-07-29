"""Execução de SQL no SQL Warehouse serverless via Statement Execution API."""
from typing import Any

from databricks.sdk.service.sql import StatementParameterListItem

from .config import WAREHOUSE_ID, get_workspace_client


def run_query(statement: str, parameters: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    """Executa uma query e retorna a lista de linhas como dicts (col->valor).

    `parameters` é uma lista de dicts {"name": ..., "value": ...} que são
    convertidos para os objetos StatementParameterListItem esperados pelo SDK.
    """
    w = get_workspace_client()
    kwargs: dict[str, Any] = {
        "warehouse_id": WAREHOUSE_ID,
        "statement": statement,
        "wait_timeout": "50s",
    }
    if parameters:
        kwargs["parameters"] = [
            StatementParameterListItem(name=p["name"], value=p["value"])
            for p in parameters
        ]

    resp = w.statement_execution.execute_statement(**kwargs)

    # Statement pode acabar em estado de erro — falhar alto com a mensagem real.
    if resp.status and resp.status.state and resp.status.state.value not in ("SUCCEEDED",):
        msg = resp.status.error.message if resp.status.error else "estado inesperado"
        raise RuntimeError(f"Query falhou ({resp.status.state.value}): {msg}")

    if not resp.manifest or not resp.manifest.schema or not resp.manifest.schema.columns:
        return []

    columns = [c.name for c in resp.manifest.schema.columns]
    types = {c.name: c.type_name.value for c in resp.manifest.schema.columns}

    rows: list[dict[str, Any]] = []
    data = resp.result.data_array if resp.result and resp.result.data_array else []
    for raw in data:
        row: dict[str, Any] = {}
        for col, val in zip(columns, raw):
            row[col] = _coerce(val, types[col])
        rows.append(row)
    return rows


def _coerce(value: Any, type_name: str) -> Any:
    """Converte strings do resultado para tipos Python conforme o schema."""
    if value is None:
        return None
    if type_name in ("INT", "LONG", "SHORT", "BYTE"):
        return int(value)
    if type_name in ("FLOAT", "DOUBLE", "DECIMAL"):
        return float(value)
    if type_name == "BOOLEAN":
        return value == "true" or value is True
    return value
