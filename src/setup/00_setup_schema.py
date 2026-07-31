# Databricks notebook source
# MAGIC %md
# MAGIC # Setup — Player Feedback Analysis
# MAGIC Cria o schema e as tabelas base da demo. Reexecutável (idempotente).
# MAGIC
# MAGIC - `reviews_raw` — bronze append-only, escrito pelo job de extração.
# MAGIC - `weekly_reports` — saída do relatório semanal.
# MAGIC
# MAGIC A tabela `reviews_enriched` NÃO é criada aqui: ela é materializada pelo
# MAGIC pipeline SDP de enriquecimento (é uma streaming table gerenciada pelo pipeline).

# COMMAND ----------

dbutils.widgets.text("catalog", "player_feedback_catalog")
dbutils.widgets.text("schema", "player_feedback")

catalog = dbutils.widgets.get("catalog")
schema = dbutils.widgets.get("schema")

print(f"Catalog: {catalog} | Schema: {schema}")

# COMMAND ----------

spark.sql(f"CREATE SCHEMA IF NOT EXISTS `{catalog}`.`{schema}`")

# COMMAND ----------

# MAGIC %md ## reviews_raw — bronze append-only
# MAGIC Uma linha por review coletado. Deduplicado por `review_id` já na fonte
# MAGIC (no job de extração), então aqui é só append.

# COMMAND ----------

spark.sql(f"""
CREATE TABLE IF NOT EXISTS `{catalog}`.`{schema}`.reviews_raw (
    review_id              STRING    COMMENT 'reviewId da Play Store — chave de dedup',
    game                   STRING    COMMENT 'Nome do jogo (chave do mapa games)',
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

# COMMAND ----------

# MAGIC %md ## games_meta — dimensão de metadados dos jogos
# MAGIC Uma linha por jogo monitorado, com ícone e título oficiais da Play Store.
# MAGIC Populada pelo job de extração (via `google_play_scraper.app`) e lida pelo
# MAGIC App para exibir a logo de cada jogo automaticamente.

# COMMAND ----------

spark.sql(f"""
CREATE TABLE IF NOT EXISTS `{catalog}`.`{schema}`.games_meta (
    game         STRING    COMMENT 'Nome do jogo (chave do mapa games)',
    package_name STRING    COMMENT 'Package name na Play Store',
    icon         STRING    COMMENT 'URL do ícone oficial da Play Store',
    title        STRING    COMMENT 'Título oficial do app na Play Store',
    _updated_at  TIMESTAMP COMMENT 'Momento da última atualização dos metadados'
)
USING DELTA
COMMENT 'Dimensão: metadados (ícone/título) dos jogos monitorados, da Play Store.'
""")

# COMMAND ----------

# MAGIC %md ## games_config — jogos adicionados pela UI do App
# MAGIC Jogos configurados dinamicamente pelo usuário na tela "Gerenciar" do App.
# MAGIC O job de extração une estes jogos com os definidos em `databricks.yml`
# MAGIC (variável `games`), então o App pode adicionar/remover jogos sem editar o
# MAGIC bundle. `source` distingue a origem ('ui' vs 'bundle') para referência.

# COMMAND ----------

spark.sql(f"""
CREATE TABLE IF NOT EXISTS `{catalog}`.`{schema}`.games_config (
    game         STRING    COMMENT 'Nome do jogo (chave do mapa games)',
    package_name STRING    COMMENT 'Package name na Play Store',
    source       STRING    COMMENT "Origem: 'ui' (adicionado pelo App) | 'bundle'",
    _added_at    TIMESTAMP COMMENT 'Momento em que o jogo foi adicionado'
)
USING DELTA
COMMENT 'Jogos monitorados configurados dinamicamente pela UI do App.'
""")

# COMMAND ----------

# MAGIC %md ## weekly_reports — saída do relatório semanal

# COMMAND ----------

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

# Evolução de schema: garante as colunas de janela em tabelas já criadas antes
# desta versão (idempotente).
existing_cols = [c.name for c in spark.table(f"`{catalog}`.`{schema}`.weekly_reports").schema]
if "window_start" not in existing_cols:
    spark.sql(f"""
        ALTER TABLE `{catalog}`.`{schema}`.weekly_reports
        ADD COLUMNS (window_start DATE, window_end DATE)
    """)

# COMMAND ----------

print("Setup concluído.")
for t in ["reviews_raw", "games_meta", "games_config", "weekly_reports"]:
    display(spark.sql(f"DESCRIBE TABLE `{catalog}`.`{schema}`.{t}"))
