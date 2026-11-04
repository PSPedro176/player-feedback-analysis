# Databricks notebook source
# MAGIC %md
# MAGIC # Setup — Player Feedback Analysis
# MAGIC Idempotente. Cria:
# MAGIC - schema, volumes `game_logos`/`evidence` e tabelas base/auditoria;
# MAGIC - o projeto **Lakebase Autoscaling** (project/branch/endpoint/database) + a tabela Postgres
# MAGIC   `public.games` + `REPLICA IDENTITY FULL` + role do SP do App;
# MAGIC - a **CDF config** (materializa `lb_games_history` no UC);
# MAGIC - a view **`games_current`** (estado atual dos jogos, a partir do histórico do CDF);
# MAGIC - os **grants de UC** ao service principal do App.
# MAGIC
# MAGIC `reviews_enriched` NÃO é criada aqui — é a streaming table gerenciada pelo pipeline SDP.

# COMMAND ----------

# MAGIC %pip install -U "databricks-sdk>=0.133.0" psycopg2-binary
# MAGIC %restart_python

# COMMAND ----------

dbutils.widgets.text("catalog", "perdomo_demos_catalog")
dbutils.widgets.text("schema", "febar_player_feedback")
dbutils.widgets.text("app_name", "febar-player-feedback")
dbutils.widgets.text("dashboard_id", "")
dbutils.widgets.text("warehouse_id", "")
dbutils.widgets.text("refresh_views_only", "false")
# Lakebase Autoscaling — só o project_id é escolhido; branch (`production`), database
# (`databricks_postgres`) e endpoint são AUTO-CRIADOS ao criar o projeto (o endpoint tem
# id auto-gerado e é descoberto via list_endpoints).
dbutils.widgets.text("pg_project", "febar-pf-games")
dbutils.widgets.text("pg_branch", "production")
dbutils.widgets.text("pg_database", "databricks_postgres")

catalog = dbutils.widgets.get("catalog")
schema = dbutils.widgets.get("schema")
app_name = dbutils.widgets.get("app_name")
dashboard_id = dbutils.widgets.get("dashboard_id")
warehouse_id = dbutils.widgets.get("warehouse_id")
refresh_views_only = dbutils.widgets.get("refresh_views_only").lower() == "true"
pg_project = dbutils.widgets.get("pg_project")
pg_branch = dbutils.widgets.get("pg_branch")
pg_database = dbutils.widgets.get("pg_database")

VOLUME = "game_logos"
EVIDENCE_VOLUME = "evidence"

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
spark.sql(f"CREATE VOLUME IF NOT EXISTS `{catalog}`.`{schema}`.`{EVIDENCE_VOLUME}`")

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
    n_reviews    INT    COMMENT 'Nº total de reviews encontrados na janela móvel do relatório',
    avg_score    DOUBLE COMMENT 'Nota média na janela',
    bug_report_rate DOUBLE COMMENT 'Fração de reviews da janela móvel classificados como bug_report',
    negative_rate DOUBLE COMMENT 'Fração de reviews da janela móvel com sentimento negative',
    toxicity_rate DOUBLE COMMENT 'Fração de reviews da janela móvel classificados como toxicity',
    _generated_at TIMESTAMP
)
USING DELTA
COMMENT 'Relatório por jogo gerado sobre uma janela móvel configurável (7 dias por padrão); difere da visão weekly_game_summary, que agrega semanas ISO de calendário.'
""")

spark.sql(f"""
CREATE TABLE IF NOT EXISTS `{catalog}`.`{schema}`.ai_inference_log_reports (
    report_week  DATE      COMMENT 'Semana ISO usada como chave do relatório',
    game         STRING    COMMENT 'Nome do jogo',
    source       STRING    COMMENT 'Origem fixa weekly_report',
    model        STRING    COMMENT 'Serving endpoint passado ao ai_query',
    prompt_version STRING  COMMENT 'Versão controlada do template de prompt',
    prompt_text  STRING    COMMENT 'Prompt completo enviado ao modelo',
    n_sampled    BIGINT    COMMENT 'Quantidade de reviews incluídos no prompt',
    raw_response STRING    COMMENT 'Resposta bruta retornada pelo modelo',
    error_message STRING   COMMENT 'Erro retornado por ai_query com failOnError=false',
    inferred_at  TIMESTAMP COMMENT 'Momento da chamada ao modelo'
)
USING DELTA
COMMENT 'Audit trail governado das chamadas ai_query usadas para gerar relatórios semanais.'
""")


def ensure_columns(table_name, columns):
    existing = {field.name.lower() for field in spark.table(table_name).schema.fields}
    for column_name, column_ddl in columns.items():
        if column_name.lower() not in existing:
            spark.sql(f"ALTER TABLE {table_name} ADD COLUMNS ({column_name} {column_ddl})")


weekly_reports = f"`{catalog}`.`{schema}`.weekly_reports"
ensure_columns(weekly_reports, {
    "bug_report_rate": "DOUBLE COMMENT 'Fração de reviews da janela móvel classificados como bug_report'",
    "negative_rate": "DOUBLE COMMENT 'Fração de reviews da janela móvel com sentimento negative'",
    "toxicity_rate": "DOUBLE COMMENT 'Fração de reviews da janela móvel classificados como toxicity'",
})

# COMMAND ----------

# MAGIC %md ## Views governadas e comentários para Genie

# COMMAND ----------

from databricks.sdk import WorkspaceClient

w = WorkspaceClient()
sp = w.apps.get(name=app_name).service_principal_client_id


def set_column_comments(object_name, comments, object_type="TABLE"):
    for column_name, comment in comments.items():
        escaped_comment = comment.replace("'", "''")
        spark.sql(
            f"ALTER {object_type} {object_name} ALTER COLUMN `{column_name}` "
            f"COMMENT '{escaped_comment}'"
        )


available_objects = {
    row.tableName.lower()
    for row in spark.sql(f"SHOW TABLES IN `{catalog}`.`{schema}`").collect()
}
created_governed_objects = []

if "reviews_enriched" in available_objects:
    reviews_enriched = f"`{catalog}`.`{schema}`.reviews_enriched"
    weekly_summary = f"`{catalog}`.`{schema}`.weekly_game_summary"

    spark.sql(f"""
        CREATE OR REPLACE VIEW {weekly_summary} (
            game COMMENT 'Nome canônico do jogo.',
            week_start COMMENT 'Segunda-feira que inicia a semana ISO de calendário.',
            week_end COMMENT 'Domingo que encerra a semana ISO de calendário.',
            n_reviews COMMENT 'Quantidade total de reviews do jogo na semana de calendário.',
            avg_score COMMENT 'Nota média dos reviews na semana.',
            n_positive COMMENT 'Reviews classificados com sentimento positive.',
            n_negative COMMENT 'Reviews classificados com sentimento negative.',
            n_neutral COMMENT 'Reviews classificados com sentimento neutral.',
            n_mixed COMMENT 'Reviews classificados com sentimento mixed.',
            n_bug_reports COMMENT 'Reviews que mencionam bugs ou problemas técnicos.',
            n_pricing COMMENT 'Reviews que mencionam preço ou monetização.',
            n_game_balance COMMENT 'Reviews que mencionam balanceamento ou matchmaking.',
            n_toxicity COMMENT 'Reviews com sinal de linguagem tóxica.',
            n_visuals COMMENT 'Reviews que mencionam gráficos, arte, UI ou animações.',
            n_community COMMENT 'Reviews que mencionam comunidade ou recursos sociais.',
            n_opinion COMMENT 'Reviews classificados como opinião geral.',
            bug_report_rate COMMENT 'Proporção semanal de reviews classificados como bug_report.',
            negative_rate COMMENT 'Proporção semanal de reviews com sentimento negative.',
            toxicity_rate COMMENT 'Proporção semanal de reviews classificados como toxicity.'
        )
        COMMENT 'Resumo por semana ISO de calendário (segunda a domingo), próprio para consultas no Genie; não é a janela móvel de weekly_reports.'
        AS
        WITH base AS (
            SELECT
                game,
                CAST(date_trunc('WEEK', at) AS DATE) AS week_start,
                score,
                lower(sentiment) AS sentiment,
                coalesce(bug_report, false) AS bug_report,
                coalesce(pricing, false) AS pricing,
                coalesce(game_balance, false) AS game_balance,
                coalesce(toxicity, false) AS toxicity,
                coalesce(visuals, false) AS visuals,
                coalesce(community, false) AS community,
                coalesce(opinion, false) AS opinion
            FROM {reviews_enriched}
            WHERE game IS NOT NULL AND at IS NOT NULL
        )
        SELECT
            game,
            week_start,
            date_add(week_start, 6) AS week_end,
            count(*) AS n_reviews,
            CAST(avg(score) AS DOUBLE) AS avg_score,
            count_if(sentiment = 'positive') AS n_positive,
            count_if(sentiment = 'negative') AS n_negative,
            count_if(sentiment = 'neutral') AS n_neutral,
            count_if(sentiment = 'mixed') AS n_mixed,
            count_if(bug_report) AS n_bug_reports,
            count_if(pricing) AS n_pricing,
            count_if(game_balance) AS n_game_balance,
            count_if(toxicity) AS n_toxicity,
            count_if(visuals) AS n_visuals,
            count_if(community) AS n_community,
            count_if(opinion) AS n_opinion,
            CAST(count_if(bug_report) AS DOUBLE) / count(*) AS bug_report_rate,
            CAST(count_if(sentiment = 'negative') AS DOUBLE) / count(*) AS negative_rate,
            CAST(count_if(toxicity) AS DOUBLE) / count(*) AS toxicity_rate
        FROM base
        GROUP BY game, week_start
    """)
    created_governed_objects.extend([reviews_enriched, weekly_summary])
else:
    print("reviews_enriched ainda não existe; weekly_game_summary será criada após o pipeline.")

spark.sql(
    f"COMMENT ON TABLE {weekly_reports} IS "
    "'Relatórios gerados sobre janela móvel configurável (7 dias por padrão), distinta das semanas ISO da weekly_game_summary.'"
)
set_column_comments(weekly_reports, {
    "report_week": "Segunda-feira ISO usada como chave idempotente do relatório.",
    "game": "Nome canônico do jogo.",
    "grade": "Semáforo determinístico green, yellow ou red.",
    "report": "Texto consolidado gerado por ai_query.",
    "window_start": "Primeira data observada na janela móvel.",
    "window_end": "Última data observada na janela móvel.",
    "n_reviews": "Total de reviews encontrados na janela móvel, antes da amostragem do prompt.",
    "avg_score": "Nota média na janela móvel.",
    "bug_report_rate": "Fração de reviews da janela classificados como bug_report.",
    "negative_rate": "Fração de reviews da janela com sentimento negative.",
    "toxicity_rate": "Fração de reviews da janela classificados como toxicity.",
})
created_governed_objects.append(weekly_reports)

if "ai_inference_log_enrichment" in available_objects:
    ai_log = f"`{catalog}`.`{schema}`.ai_inference_log"
    spark.sql(f"""
        CREATE OR REPLACE VIEW {ai_log} (
            source COMMENT 'Etapa que realizou a inferência: enrichment ou weekly_report.',
            game COMMENT 'Jogo associado à chamada.',
            record_key COMMENT 'Review ID ou chave composta report_week|game.',
            model COMMENT 'Serving endpoint usado pelo ai_query.',
            prompt_version COMMENT 'Versão controlada do template de prompt.',
            raw_response COMMENT 'Resposta bruta retornada pelo modelo.',
            error_message COMMENT 'Mensagem de erro retornada com failOnError=false.',
            inferred_at COMMENT 'Timestamp da chamada ao modelo.'
        )
        COMMENT 'Trilha unificada e governada de chamadas ai_query de enriquecimento e relatórios.'
        AS
        SELECT
            source,
            game,
            CAST(review_id AS STRING) AS record_key,
            model,
            prompt_version,
            raw_response,
            error_message,
            inferred_at
        FROM `{catalog}`.`{schema}`.ai_inference_log_enrichment
        UNION ALL
        SELECT
            source,
            game,
            concat(CAST(report_week AS STRING), '|', game) AS record_key,
            model,
            prompt_version,
            raw_response,
            error_message,
            inferred_at
        FROM `{catalog}`.`{schema}`.ai_inference_log_reports
    """)
    created_governed_objects.append(ai_log)
else:
    print("ai_inference_log_enrichment ainda não existe; ai_inference_log será criada após o pipeline.")

for statement in [
    f"GRANT USE CATALOG ON CATALOG `{catalog}` TO `{sp}`",
    f"GRANT USE SCHEMA, SELECT ON SCHEMA `{catalog}`.`{schema}` TO `{sp}`",
    f"GRANT READ VOLUME ON VOLUME `{catalog}`.`{schema}`.`{VOLUME}` TO `{sp}`",
]:
    spark.sql(statement)
print(f"Views/comentários/grants governados atualizados para o SP do App ({sp}).")

if refresh_views_only:
    dbutils.notebook.exit("views governadas atualizadas")

# COMMAND ----------

# MAGIC %md ## Lakebase Autoscaling — projeto / branch / endpoint / database + role do SP
# MAGIC CDF é exclusivo do tier Autoscaling (`w.postgres`, projects/branches/endpoints).
# MAGIC Provisionamento idempotente (get-before-create); cada op é long-running (`.wait()`).

# COMMAND ----------

import psycopg2
from databricks.sdk.service import postgres as pg
from databricks.sdk.errors import BadRequest, NotFound

project_path = f"projects/{pg_project}"
branch_path = f"{project_path}/branches/{pg_branch}"

# Falha alto se o App ainda não foi implantado (o SP é necessário para role + grants).
run_as_user = w.current_user.me().user_name
print(f"run_as={run_as_user} | SP do App={sp}")

# 1) Projeto — mínimo. Auto-cria branch `production`, database `databricks_postgres` e endpoint.
try:
    w.postgres.get_project(name=project_path)
    print(f"Projeto {pg_project} já existe.")
except NotFound:
    print(f"Criando projeto {pg_project} (Postgres 16)...")
    w.postgres.create_project(
        pg.Project(spec=pg.ProjectSpec(pg_version=16)),
        project_id=pg_project,
    ).wait()
    print("Projeto criado (branch production + database databricks_postgres + endpoint).")

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

# Idempotente por destino: outra config na mesma database não satisfaz este bundle.
def cdf_destination(config):
    spec = getattr(config, "spec", None)
    return (
        getattr(config, "catalog", None) or getattr(spec, "catalog", None),
        getattr(config, "schema", None) or getattr(spec, "schema", None),
    )


existing_cdf = list(w.postgres.list_cdf_configs(parent=db_path))
target_cdf = [
    config for config in existing_cdf
    if cdf_destination(config) == (catalog, schema)
]
if target_cdf:
    print(f"CDF config do destino {catalog}.{schema} já existe ({len(target_cdf)}).")
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
