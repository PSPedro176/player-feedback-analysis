# Databricks notebook source
# MAGIC %md
# MAGIC # Setup — Player Feedback Analysis
# MAGIC Idempotente. Provisiona SÓ o que não tem recurso DAB (o project/branch/endpoint
# MAGIC Lakebase são recursos do bundle — ver `resources/pf_lakebase.yml`). Cria:
# MAGIC - schema, **volume `game_logos`** e tabelas base (`reviews_raw`, `weekly_reports`);
# MAGIC - a tabela Postgres `public.games` + `REPLICA IDENTITY FULL` + o **role do SP do App**
# MAGIC   no Lakebase (o SP só existe pós-deploy, por isso o role é imperativo aqui);
# MAGIC - a **CDF config** (materializa `lb_games_history` no UC) — o único pedaço sem recurso DAB;
# MAGIC - a view **`games_current`** (estado atual dos jogos, a partir do histórico do CDF);
# MAGIC - os **grants de UC** ao service principal do App.
# MAGIC
# MAGIC `reviews_enriched` NÃO é criada aqui — é a streaming table gerenciada pelo pipeline SDP.

# COMMAND ----------

# MAGIC %pip install -U "databricks-sdk>=0.133.0" psycopg2-binary
# MAGIC %restart_python

# COMMAND ----------

dbutils.widgets.text("catalog", "player_feedback_catalog")
dbutils.widgets.text("schema", "player_feedback")
dbutils.widgets.text("app_name", "player-feedback-analysis")
dbutils.widgets.text("dashboard_id", "")
dbutils.widgets.text("warehouse_id", "")
# Lakebase Autoscaling — project/branch/endpoint são recursos do bundle (pf_lakebase.yml).
# Estes params só ecoam esses nomes: o endpoint tem id auto-gerado (descoberto via
# list_endpoints) e o database `databricks_postgres` é o auto-criado com o projeto.
dbutils.widgets.text("pg_project", "pf-games")
dbutils.widgets.text("pg_branch", "production")
dbutils.widgets.text("pg_database", "databricks_postgres")

catalog = dbutils.widgets.get("catalog")
schema = dbutils.widgets.get("schema")
app_name = dbutils.widgets.get("app_name")
dashboard_id = dbutils.widgets.get("dashboard_id")
warehouse_id = dbutils.widgets.get("warehouse_id")
pg_project = dbutils.widgets.get("pg_project")
pg_branch = dbutils.widgets.get("pg_branch")
pg_database = dbutils.widgets.get("pg_database")

VOLUME = "game_logos"

print(f"Catalog: {catalog} | Schema: {schema} | Lakebase project: {pg_project}")

# COMMAND ----------

# MAGIC %md ## Catálogo, schema, volume e tabelas base (Delta)

# COMMAND ----------

# Catálogo é criado best-effort (pode já existir / ser pré-provisionado).
try:
    spark.sql(f"CREATE CATALOG IF NOT EXISTS `{catalog}`")
except Exception as e:
    print(f"(catálogo não criado aqui — provavelmente pré-existente): {e}")

spark.sql(f"CREATE SCHEMA IF NOT EXISTS `{catalog}`.`{schema}`")
spark.sql(f"CREATE VOLUME IF NOT EXISTS `{catalog}`.`{schema}`.`{VOLUME}`")

# COMMAND ----------

spark.sql(f"""
CREATE TABLE IF NOT EXISTS `{catalog}`.`{schema}`.reviews_raw (
    review_id              STRING    COMMENT 'reviewId da Play Store — chave de dedup',
    game                   STRING    COMMENT 'Nome do jogo (chave do cadastro)',
    package_name           STRING    COMMENT 'Package name na Play Store',
    language               STRING    COMMENT 'Idioma da chamada à API',
    user_name              STRING,
    content                STRING    COMMENT 'Texto do review',
    score                  INT       COMMENT 'Nota 1-5',
    thumbs_up_count        INT,
    review_created_version STRING,
    at                     TIMESTAMP COMMENT 'Data/hora do review (usada como watermark)',
    reply_content          STRING,
    replied_at             TIMESTAMP,
    app_version            STRING,
    _ingested_at           TIMESTAMP COMMENT 'Momento da ingestão'
)
USING DELTA
COMMENT 'Bronze: reviews da Play Store, deduplicados por review_id na fonte.'
""")

spark.sql(f"""
CREATE TABLE IF NOT EXISTS `{catalog}`.`{schema}`.weekly_reports (
    report_week  DATE   COMMENT 'Segunda-feira da semana do relatório (ISO date)',
    game         STRING,
    grade        STRING COMMENT 'green | yellow | red — calculado deterministicamente',
    report       STRING COMMENT 'Relatório textual consolidado (20-30 linhas)',
    window_start DATE   COMMENT 'Data do comentário mais antigo incluído na janela',
    window_end   DATE   COMMENT 'Data do comentário mais recente incluído na janela',
    n_reviews    INT    COMMENT 'Nº de reviews amostrados na janela',
    avg_score    DOUBLE COMMENT 'Nota média na janela',
    _generated_at TIMESTAMP
)
USING DELTA
COMMENT 'Relatório semanal por jogo (janela de 7 dias), gerado por ai_query.'
""")

# COMMAND ----------

# MAGIC %md ## Lakebase Autoscaling — valida o projeto, descobre endpoint/database, cria o role do SP
# MAGIC Project/branch/endpoint vêm do bundle (`resources/pf_lakebase.yml`). Aqui só descobrimos
# MAGIC os paths (endpoint/database têm id auto-gerado) e criamos o **role Postgres do SP do App**
# MAGIC (o SP só existe pós-deploy, então não é declarável no bundle).

# COMMAND ----------

import psycopg2
from databricks.sdk import WorkspaceClient
from databricks.sdk.service import postgres as pg
from databricks.sdk.errors import BadRequest, NotFound

w = WorkspaceClient()

project_path = f"projects/{pg_project}"
branch_path = f"{project_path}/branches/{pg_branch}"

# Falha alto se o App ainda não foi implantado (o SP é necessário para role + grants).
run_as_user = w.current_user.me().user_name
sp = w.apps.get(name=app_name).service_principal_client_id
print(f"run_as={run_as_user} | SP do App={sp}")

# 1) Projeto/branch/endpoint/database vêm do BUNDLE (resources/pf_lakebase.yml). Aqui só
# validamos que o projeto existe — falha clara se o `bundle deploy` não rodou antes.
try:
    w.postgres.get_project(name=project_path)
    print(f"Projeto {pg_project} encontrado (criado pelo bundle).")
except NotFound:
    raise RuntimeError(
        f"Projeto Lakebase {project_path} não existe. Rode `databricks bundle deploy` "
        "ANTES do pf_setup — project/branch/endpoint agora são recursos do bundle "
        "(resources/pf_lakebase.yml)."
    )

# 2) Descobre endpoint read-write E database (ambos com id auto-gerado — não hardcodar path).
endpoints = list(w.postgres.list_endpoints(parent=branch_path))
rw = [e for e in endpoints
      if (e.spec and e.spec.endpoint_type == pg.EndpointType.ENDPOINT_TYPE_READ_WRITE)]
endpoint_path = (rw or endpoints)[0].name

databases = list(w.postgres.list_databases(parent=branch_path))
db = next((d for d in databases if d.database_id == pg_database), databases[0])
db_path = db.name
print(f"Endpoint: {endpoint_path}\nDatabase: {db_path}")

# 3) Role do SP do App (SERVICE_PRINCIPAL + OAuth, superuser p/ acessar a tabela).
# Idempotência via padrão create-e-trata-conflito: list_roles pode não popular `spec`,
# então tentamos criar e tratamos SÓ o "already exists". Qualquer outro erro estoura.
try:
    w.postgres.create_role(
        parent=branch_path,
        role=pg.Role(spec=pg.RoleRoleSpec(
            identity_type=pg.RoleIdentityType.SERVICE_PRINCIPAL,
            auth_method=pg.RoleAuthMethod.LAKEBASE_OAUTH_V1,
            postgres_role=sp,
            membership_roles=[pg.RoleMembershipRole.DATABRICKS_SUPERUSER],
        )),
    ).wait()
    print(f"Role do SP criado ({sp}).")
except BadRequest as e:
    if "already exists" in str(e).lower():
        print(f"Role do SP já existe ({sp}).")
    else:
        raise

# COMMAND ----------

# MAGIC %md ## Tabela de cadastro `public.games` + REPLICA IDENTITY FULL

# COMMAND ----------

pg_host = w.postgres.get_endpoint(name=endpoint_path).status.hosts.host
pg_token = w.postgres.generate_database_credential(endpoint=endpoint_path).token

conn = psycopg2.connect(
    host=pg_host, port=5432, dbname=pg_database,
    user=run_as_user, password=pg_token, sslmode="require",
)
conn.autocommit = True
cur = conn.cursor()

cur.execute("""
    CREATE TABLE IF NOT EXISTS public.games (
        package_name text PRIMARY KEY,
        game         text NOT NULL,
        active       boolean NOT NULL DEFAULT true,
        added_at     timestamptz NOT NULL DEFAULT now()
    )
""")
# REPLICA IDENTITY FULL é pré-requisito do Lakebase CDF (captura preimage em updates/deletes).
cur.execute("ALTER TABLE public.games REPLICA IDENTITY FULL")
# O role do SP já tem superuser; o grant a PUBLIC é rede de segurança para a demo.
cur.execute("GRANT USAGE ON SCHEMA public TO PUBLIC")
cur.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.games TO PUBLIC")
print("Tabela public.games pronta (REPLICA IDENTITY FULL + grants Postgres).")

# COMMAND ----------

# MAGIC %md ## Lakebase CDF — cria a config (materializa `lb_games_history` no UC)
# MAGIC Feed por schema Postgres (`public`) → tabelas Delta `lb_<tabela>_history` em catalog.schema.

# COMMAND ----------

# Idempotente: só cria se ainda não existe uma config para esta database. Falha alto em erro real.
existing_cdf = list(w.postgres.list_cdf_configs(parent=db_path))
if existing_cdf:
    print(f"CDF config já existe ({len(existing_cdf)}).")
else:
    w.postgres.create_cdf_config(
        parent=db_path,
        cdf_config=pg.CdfConfig(catalog=catalog, schema=schema, postgres_schema="public"),
    ).wait()
    print("CDF config criada — materializa lb_games_history no UC.")

# COMMAND ----------

# MAGIC %md ## View `games_current` — estado atual dos jogos a partir do histórico do CDF
# MAGIC Última mudança por `package_name` (maior `_pg_lsn`), excluindo linhas de remoção.

# COMMAND ----------

# A view depende do lb_games_history, que o CDF só materializa após processar a 1ª mudança.
# Checagem explícita (não é try/except mascarando): cria a view se a history já existe.
tables = [r.tableName for r in spark.sql(f"SHOW TABLES IN `{catalog}`.`{schema}`").collect()]
if "lb_games_history" in tables:
    spark.sql(f"""
        CREATE OR REPLACE VIEW `{catalog}`.`{schema}`.games_current AS
        WITH ranked AS (
            SELECT package_name, game, active, _pg_change_type,
                   row_number() OVER (PARTITION BY package_name ORDER BY _pg_lsn DESC) AS rn
            FROM `{catalog}`.`{schema}`.lb_games_history
        )
        SELECT package_name, game, active
        FROM ranked
        WHERE rn = 1 AND _pg_change_type IN ('insert', 'update_postimage')
    """)
    print("View games_current criada/atualizada.")
else:
    print(
        "lb_games_history ainda não existe (CDF materializando). Adicione um jogo pelo App e "
        "re-rode o pf_setup em instantes para criar a view games_current."
    )

# COMMAND ----------

# MAGIC %md ## Grants de UC ao service principal do App

# COMMAND ----------

# GRANT é idempotente; sp já resolvido acima. Falha alto se algo der errado.
for stmt in [
    f"GRANT USE CATALOG ON CATALOG `{catalog}` TO `{sp}`",
    f"GRANT USE SCHEMA, SELECT ON SCHEMA `{catalog}`.`{schema}` TO `{sp}`",
    f"GRANT READ VOLUME ON VOLUME `{catalog}`.`{schema}`.`{VOLUME}` TO `{sp}`",
]:
    spark.sql(stmt)
print(f"Grants de UC aplicados ao SP do App ({sp}).")

# COMMAND ----------

# MAGIC %md ## Publica o AI/BI Dashboard
# MAGIC O bundle cria o dashboard como rascunho; o embed no App exige a versão publicada.

# COMMAND ----------

# Publica por ID (vem do bundle: ${resources.dashboards.pf_dashboard.dashboard_id}). Sem lógica de nome.
# publish é idempotente (re-publicar é ok); falha alto se o id não veio.
if not dashboard_id:
    raise RuntimeError(
        "dashboard_id vazio — o pf_setup deve ser rodado pelo bundle "
        "(passa ${resources.dashboards.pf_dashboard.dashboard_id})."
    )
w.lakeview.publish(dashboard_id, embed_credentials=True, warehouse_id=warehouse_id or None)
print(f"Dashboard publicado ({dashboard_id}).")

# COMMAND ----------

print("Setup concluído.")
