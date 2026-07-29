# Databricks notebook source
# MAGIC %md
# MAGIC # Extração de reviews da Play Store
# MAGIC
# MAGIC Coleta reviews de todos os jogos em todos os idiomas via `google-play-scraper`,
# MAGIC paginando com `continuation_token` (200/página, `Sort.NEWEST`).
# MAGIC
# MAGIC **Dedup e filtro NA FONTE** (o ponto central desta demo):
# MAGIC - Mantém-se o último comentário por jogo (`last_comment = MAX(at)` em `reviews_raw`).
# MAGIC - Ao paginar cada jogo, PARA assim que alcança reviews com `at < last_comment`.
# MAGIC - Inclui apenas reviews onde `at >= last_comment`.
# MAGIC - Deduplica por `review_id` (dentro do run e contra o que já existe na tabela).
# MAGIC
# MAGIC Assim o bronze recebe só dado novo e limpo — nada de jogar lixo pra limpar depois.

# COMMAND ----------

# MAGIC %pip install google-play-scraper
# MAGIC %restart_python

# COMMAND ----------

import json
import time

from google_play_scraper import reviews, Sort
from pyspark.sql import functions as F
from pyspark.sql.types import (
    StructType, StructField, StringType, IntegerType, TimestampType,
)

# COMMAND ----------

dbutils.widgets.text("catalog", "player_feedback_catalog")
dbutils.widgets.text("schema", "player_feedback")
dbutils.widgets.text("games", '{"Exemplo 1": "com.example.game1", "Exemplo 2": "com.example.game2"}')
dbutils.widgets.text("languages", '["pt", "en", "es"]')
dbutils.widgets.text("country", "br")
dbutils.widgets.text("page_count", "200")
dbutils.widgets.text("sleep_ms", "300")
dbutils.widgets.text("backfill_max_per_game", "3000")
# Modo backfill: ignora o watermark last_comment e pagina fundo em TODAS as
# combinações (não só na primeira carga) para maximizar o histórico coletado.
# O dedup por anti-join (review_id) garante que nada duplica mesmo re-rodando.
dbutils.widgets.text("backfill_mode", "false")

catalog = dbutils.widgets.get("catalog")
schema = dbutils.widgets.get("schema")
country = dbutils.widgets.get("country")
page_count = int(dbutils.widgets.get("page_count"))
sleep_s = int(dbutils.widgets.get("sleep_ms")) / 1000.0
backfill_max = int(dbutils.widgets.get("backfill_max_per_game"))
backfill_mode = dbutils.widgets.get("backfill_mode").lower() == "true"


# base_parameters do tipo complex chegam como JSON string; parse explícito.
def _parse(widget_value):
    return json.loads(widget_value)


games = _parse(dbutils.widgets.get("games"))            # {nome: package_name}
languages = _parse(dbutils.widgets.get("languages"))    # [idioma, ...]

target_table = f"`{catalog}`.`{schema}`.reviews_raw"

print(f"Destino: {target_table}")
print(f"Jogos: {games}")
print(f"Idiomas: {languages} | país: {country}")

# COMMAND ----------

# MAGIC %md ## Watermark por jogo — `last_comment = MAX(at)`

# COMMAND ----------

# Se a tabela já tem dados, pegamos o último comentário (at) por jogo.
# Primeira carga (tabela vazia) → dict vazio → aplica-se o teto de backfill.
last_comment = {}
existing = spark.sql(
    f"SELECT game, MAX(at) AS last_at FROM {target_table} GROUP BY game"
).collect()
for row in existing:
    if row["last_at"] is not None:
        last_comment[row["game"]] = row["last_at"]

is_first_load = len(last_comment) == 0
print(f"Primeira carga? {is_first_load}")
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
    """Grava um lote em Delta (append), deduplicando por review_id contra a tabela.

    Checkpoint incremental: se o job cair no meio, o que já foi gravado permanece.
    Retorna quantas linhas foram efetivamente gravadas (pós-dedup).
    """
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
    """Pagina reviews de um jogo/idioma, cortando no last_comment do jogo, e
    gravando em Delta a cada página (checkpoint). Retorna o total gravado.
    """
    # Em backfill_mode ignoramos o watermark p/ puxar histórico fundo.
    watermark = None if backfill_mode else last_comment.get(game)
    token = None
    stop = False
    page = 0
    written = 0
    buffer = []

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

        for r in result:
            at = r["at"]  # datetime
            # Corte na fonte: como a ordenação é NEWEST, assim que alcançamos um
            # review com at < watermark, todo o resto é mais antigo → paramos.
            # O review de fronteira (at == watermark) é mantido aqui e depois
            # removido pela dedup por review_id na gravação.
            if watermark is not None and at < watermark:
                stop = True
                break
            # Acesso explícito por chave (não .get()): os campos do
            # google-play-scraper são estáveis; se a API mudar, estoura KeyError
            # na hora em vez de gravar None silencioso.
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

        # Grava o buffer a cada página (checkpoint incremental).
        written += flush(buffer)
        buffer = []

        # Trava dura de páginas na primeira carga OU em backfill_mode: evita
        # puxar centenas de milhares (jogos grandes têm 100k+). max_pages = ceil(backfill/200).
        if (is_first_load or backfill_mode) and page >= max_pages:
            stop = True

        if token is None:
            stop = True

        if not stop:
            time.sleep(sleep_s)

    return written

# COMMAND ----------

# Trava de páginas por combinação (primeira carga ou backfill_mode).
max_pages = max(1, (backfill_max + page_count - 1) // page_count)
print(f"backfill_mode={backfill_mode} | máx {max_pages} páginas/combinação "
      f"(~{max_pages*page_count} reviews) | idiomas: {languages}")

total_written = 0
for game, package_name in games.items():
    for lang in languages:
        n = collect_game_language(game, package_name, lang)
        print(f"  {game:14s} [{lang}] → {n} reviews gravados")
        total_written += n

print(f"\nTotal gravado (pós-dedup): {total_written}")

# COMMAND ----------

display(spark.sql(
    f"SELECT game, COUNT(*) AS n, MIN(at) AS oldest, MAX(at) AS newest "
    f"FROM {target_table} GROUP BY game ORDER BY game"
))
