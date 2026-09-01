# Databricks notebook source
# MAGIC %md
# MAGIC # Extração de reviews da Play Store
# MAGIC
# MAGIC Coleta reviews dos jogos **cadastrados** (lidos de `games_current`) em todos os idiomas via
# MAGIC `google-play-scraper`, paginando com `continuation_token` (200/página, `Sort.NEWEST`).
# MAGIC
# MAGIC **Dedup e filtro NA FONTE:**
# MAGIC - Watermark por jogo = `last_comment = MAX(at)` em `reviews_raw`.
# MAGIC - **Jogo já existente** → coleta incremental: para ao alcançar `at < last_comment`.
# MAGIC - **Jogo novo** (sem reviews ainda) → backfill por DATA: watermark = `hoje - backfill_months`,
# MAGIC   com teto de segurança de páginas (`backfill_max_per_game`). Para na data OU no teto.
# MAGIC - Deduplica por `review_id` (no run e contra a tabela).
# MAGIC
# MAGIC Ao final, sinaliza via taskValue `new_games` quantos jogos ainda não têm relatório — o job
# MAGIC usa isso para, condicionalmente, disparar o relatório semanal (que também coleta os logos).

# COMMAND ----------

# MAGIC %pip install google-play-scraper
# MAGIC %restart_python

# COMMAND ----------

import json
import time
from datetime import datetime, timedelta

from google_play_scraper import reviews, Sort
from pyspark.sql import functions as F
from pyspark.sql.types import (
    StructType, StructField, StringType, IntegerType, TimestampType,
)

# COMMAND ----------

dbutils.widgets.text("catalog", "player_feedback_catalog")
dbutils.widgets.text("schema", "player_feedback")
dbutils.widgets.text("languages", '["pt", "en", "es"]')
dbutils.widgets.text("country", "br")
dbutils.widgets.text("page_count", "200")
dbutils.widgets.text("sleep_ms", "300")
dbutils.widgets.text("backfill_months", "3")
dbutils.widgets.text("backfill_max_per_game", "3000")

catalog = dbutils.widgets.get("catalog")
schema = dbutils.widgets.get("schema")
country = dbutils.widgets.get("country")
page_count = int(dbutils.widgets.get("page_count"))
sleep_s = int(dbutils.widgets.get("sleep_ms")) / 1000.0
backfill_months = int(dbutils.widgets.get("backfill_months"))
backfill_max = int(dbutils.widgets.get("backfill_max_per_game"))

languages = json.loads(dbutils.widgets.get("languages"))

target_table = f"`{catalog}`.`{schema}`.reviews_raw"
games_current = f"`{catalog}`.`{schema}`.games_current"
reports_table = f"`{catalog}`.`{schema}`.weekly_reports"

# Data de corte do backfill de jogos novos (aproxima meses por 30 dias).
backfill_cutoff = datetime.now() - timedelta(days=backfill_months * 30)

# Teto de segurança de páginas por jogo/idioma (para jogos novos).
max_pages = max(1, (backfill_max + page_count - 1) // page_count)

# COMMAND ----------

# MAGIC %md ## Jogos cadastrados (de `games_current`)

# COMMAND ----------

# Fonte de verdade dos jogos: o cadastro gerenciado pelo App (Lakebase → CDF → games_current).
games = {
    r["game"]: r["package_name"]
    for r in spark.sql(
        f"SELECT game, package_name FROM {games_current} WHERE active"
    ).collect()
}

if not games:
    print("Nenhum jogo cadastrado em games_current. Nada a coletar.")
    dbutils.jobs.taskValues.set(key="new_games", value=0)
    dbutils.notebook.exit("sem jogos")

print(f"Jogos: {games}")
print(f"Idiomas: {languages} | país: {country}")
print(f"Backfill (jogos novos): até {backfill_cutoff.date()} | teto {max_pages} págs/idioma")

# COMMAND ----------

# MAGIC %md ## Watermark por jogo — `last_comment = MAX(at)`

# COMMAND ----------

last_comment = {}
existing = spark.sql(
    f"SELECT game, MAX(at) AS last_at FROM {target_table} GROUP BY game"
).collect()
for row in existing:
    if row["last_at"] is not None:
        last_comment[row["game"]] = row["last_at"]

print(f"last_comment por jogo: {last_comment}")

# COMMAND ----------

# MAGIC %md ## Coleta paginada com corte na fonte

# COMMAND ----------

schema_struct = StructType([
    StructField("review_id", StringType()),
    StructField("game", StringType()),
    StructField("package_name", StringType()),
    StructField("language", StringType()),
    StructField("user_name", StringType()),
    StructField("content", StringType()),
    StructField("score", IntegerType()),
    StructField("thumbs_up_count", IntegerType()),
    StructField("review_created_version", StringType()),
    StructField("at", TimestampType()),
    StructField("reply_content", StringType()),
    StructField("replied_at", TimestampType()),
    StructField("app_version", StringType()),
])


def flush(rows):
    """Grava um lote em Delta (append), deduplicando por review_id contra a tabela."""
    if not rows:
        return 0
    df = (spark.createDataFrame(rows, schema=schema_struct)
          .dropDuplicates(["review_id"]))
    existing_ids = spark.sql(f"SELECT review_id FROM {target_table}")
    df_new = df.join(existing_ids, on="review_id", how="left_anti") \
               .withColumn("_ingested_at", F.current_timestamp())
    n = df_new.count()
    if n > 0:
        (df_new.select(
            "review_id", "game", "package_name", "language", "user_name",
            "content", "score", "thumbs_up_count", "review_created_version",
            "at", "reply_content", "replied_at", "app_version", "_ingested_at",
        ).write.mode("append").saveAsTable(target_table))
    return n


def collect_game_language(game, package_name, lang):
    """Pagina reviews de um jogo/idioma cortando no watermark, gravando por página.

    - Jogo novo (não está em last_comment): watermark = backfill_cutoff (por data) +
      teto de páginas (segurança).
    - Jogo existente: watermark = last_comment[game] (incremental, sem teto).
    """
    game_is_new = game not in last_comment
    watermark = backfill_cutoff if game_is_new else last_comment.get(game)

    token = None
    stop = False
    page = 0
    written = 0

    while not stop:
        result, token = reviews(
            package_name,
            lang=lang,
            country=country,
            sort=Sort.NEWEST,     # essencial: default MOST_RELEVANT é truncado
            count=page_count,
            continuation_token=token,
        )
        page += 1
        buffer = []

        for r in result:
            at = r["at"]  # datetime
            # Corte na fonte: como a ordenação é NEWEST, ao alcançar at < watermark
            # todo o resto é mais antigo → paramos. O de fronteira (at == watermark)
            # é mantido e depois removido pela dedup por review_id.
            if watermark is not None and at < watermark:
                stop = True
                break
            buffer.append({
                "review_id": r["reviewId"],
                "game": game,
                "package_name": package_name,
                "language": lang,
                "user_name": r["userName"],
                "content": r["content"],
                "score": r["score"],
                "thumbs_up_count": r["thumbsUpCount"],
                "review_created_version": r["reviewCreatedVersion"],
                "at": at,
                "reply_content": r["replyContent"],
                "replied_at": r["repliedAt"],
                "app_version": r["appVersion"],
            })

        # Checkpoint incremental: grava o buffer a cada página.
        written += flush(buffer)

        # Teto de segurança só para jogos novos (backfill).
        if game_is_new and page >= max_pages:
            stop = True

        if token is None:
            stop = True

        if not stop:
            time.sleep(sleep_s)

    return written

# COMMAND ----------

total_written = 0
for game, package_name in games.items():
    for lang in languages:
        n = collect_game_language(game, package_name, lang)
        print(f"  {game:16s} [{lang}] → {n} reviews gravados")
        total_written += n

print(f"\nTotal gravado (pós-dedup): {total_written}")

# COMMAND ----------

# MAGIC %md ## Sinaliza jogos novos (sem relatório) para a porta condicional do job

# COMMAND ----------

# "Jogo novo" (para disparar o relatório semanal) = cadastrado e ativo, sem nenhuma
# linha em weekly_reports ainda. LEFT ANTI JOIN por game.
new_games = spark.sql(f"""
    SELECT count(*) AS n
    FROM {games_current} g
    WHERE g.active
      AND NOT EXISTS (SELECT 1 FROM {reports_table} w WHERE w.game = g.game)
""").collect()[0]["n"]

print(f"Jogos sem relatório (new_games): {new_games}")
dbutils.jobs.taskValues.set(key="new_games", value=int(new_games))

# COMMAND ----------

display(spark.sql(
    f"SELECT game, COUNT(*) AS n, MIN(at) AS oldest, MAX(at) AS newest "
    f"FROM {target_table} GROUP BY game ORDER BY game"
))
