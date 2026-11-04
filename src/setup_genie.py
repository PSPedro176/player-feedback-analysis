# Databricks notebook source
# MAGIC %md
# MAGIC # Setup do Genie — Player Feedback
# MAGIC Idempotente. Cria (ou atualiza) o **Genie space** dedicado sobre as tabelas governadas do
# MAGIC projeto, a partir da definição versionada em `src/genie/player_feedback.geniespace.json`:
# MAGIC - procura o space pelo **título**; se existir, atualiza (tabelas, instruções, perguntas
# MAGIC   de exemplo e SQLs confiáveis); senão, cria;
# MAGIC - concede **CAN_RUN** no space ao service principal do App (o chat do App usa a
# MAGIC   Genie Conversation API com a identidade do SP).
# MAGIC
# MAGIC Por que um job e não o recurso `genie_spaces` do bundle: a API do Genie valida na criação
# MAGIC que as tabelas existem, e `reviews_enriched` / `weekly_game_summary` / `ai_inference_log`
# MAGIC só existem depois do `pf_setup` + primeira execução do pipeline. Rodar como job mantém o
# MAGIC `bundle deploy` funcionando num workspace vazio.

# COMMAND ----------

# MAGIC %pip install -U "databricks-sdk>=0.161.0"
# MAGIC %restart_python

# COMMAND ----------

dbutils.widgets.text("catalog", "perdomo_demos_catalog")
dbutils.widgets.text("schema", "febar_player_feedback")
dbutils.widgets.text("warehouse_id", "")
dbutils.widgets.text("app_name", "febar-player-feedback")
dbutils.widgets.text("space_title", "Player Feedback — Genie")
dbutils.widgets.text("definition_path", "")

catalog = dbutils.widgets.get("catalog")
schema = dbutils.widgets.get("schema")
warehouse_id = dbutils.widgets.get("warehouse_id")
app_name = dbutils.widgets.get("app_name")
space_title = dbutils.widgets.get("space_title")
definition_path = dbutils.widgets.get("definition_path")

if not warehouse_id:
    raise ValueError("warehouse_id é obrigatório")

print(f"Catalog: {catalog} | Schema: {schema} | Warehouse: {warehouse_id} | Título: {space_title}")

# COMMAND ----------

# MAGIC %md ## Definição do space (JSON versionado → serialized_space)

# COMMAND ----------

import json
import os

if not definition_path:
    # Notebook task em workspace files: o cwd é a pasta do notebook (src/).
    definition_path = os.path.join(os.getcwd(), "genie", "player_feedback.geniespace.json")

with open(definition_path, encoding="utf-8") as f:
    raw = f.read()

# A definição usa o placeholder __CATALOG__.__SCHEMA__ para ser portável entre targets.
space = json.loads(raw.replace("__CATALOG__", catalog).replace("__SCHEMA__", schema))

# A API exige coleções ordenadas (tabelas por identifier; demais por id) — garantimos aqui.
space["data_sources"]["tables"].sort(key=lambda t: t["identifier"])
space["config"]["sample_questions"].sort(key=lambda q: q["id"])
for key in ("text_instructions", "example_question_sqls"):
    space["instructions"].get(key, []).sort(key=lambda i: i["id"])

table_ids = [t["identifier"] for t in space["data_sources"]["tables"]]
print("Tabelas do space:\n  " + "\n  ".join(table_ids))

# COMMAND ----------

# MAGIC %md ## Pré-checagem: todas as tabelas/views precisam existir

# COMMAND ----------

missing = [t for t in table_ids if not spark.catalog.tableExists(t)]
if missing:
    raise RuntimeError(
        "Tabelas ainda inexistentes (a API do Genie rejeitaria o space): "
        + ", ".join(missing)
        + ". Rode antes o pf_setup e o pf_ingest_and_enrich (pipeline + views governadas)."
    )

# COMMAND ----------

# MAGIC %md ## Cria ou atualiza o space (busca pelo título)

# COMMAND ----------

from databricks.sdk import WorkspaceClient
from databricks.sdk.service import iam

w = WorkspaceClient()

description = (
    "Genie space do Player Feedback: reviews da Google Play enriquecidos por AI Functions "
    "(sentimento + 7 rótulos), resumo semanal por jogo, relatórios semanais e auditoria de IA."
)
serialized = json.dumps(space, ensure_ascii=False)


def find_space_by_title(title: str):
    token = None
    while True:
        resp = w.genie.list_spaces(page_size=100, page_token=token)
        for s in resp.spaces or []:
            if s.title == title:
                return s
        token = resp.next_page_token
        if not token:
            return None


existing = find_space_by_title(space_title)
if existing:
    space_id = existing.space_id
    w.genie.update_space(
        space_id=space_id,
        title=space_title,
        description=description,
        warehouse_id=warehouse_id,
        serialized_space=serialized,
    )
    print(f"Genie space atualizado: {space_id}")
else:
    created = w.genie.create_space(
        warehouse_id=warehouse_id,
        serialized_space=serialized,
        title=space_title,
        description=description,
    )
    space_id = created.space_id
    print(f"Genie space criado: {space_id}")

# COMMAND ----------

# MAGIC %md ## CAN_RUN para o service principal do App

# COMMAND ----------

# PATCH (update) é aditivo: não remove as permissões existentes do space.
sp = w.apps.get(name=app_name).service_principal_client_id
w.permissions.update(
    request_object_type="genie",
    request_object_id=space_id,
    access_control_list=[
        iam.AccessControlRequest(
            service_principal_name=sp,
            permission_level=iam.PermissionLevel.CAN_RUN,
        )
    ],
)
print(f"CAN_RUN concedido ao SP do App {app_name} ({sp}).")

host = w.config.host.rstrip("/")
print(f"Genie space: {host}/genie/rooms/{space_id}")
dbutils.jobs.taskValues.set(key="space_id", value=space_id)
dbutils.notebook.exit(space_id)
