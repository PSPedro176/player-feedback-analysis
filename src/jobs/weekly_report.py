# Databricks notebook source
# MAGIC %md
# MAGIC # Relatório semanal por jogo
# MAGIC
# MAGIC Para cada jogo, amostra aleatória de ~700 comentários dos últimos 7 dias e
# MAGIC gera um relatório textual consolidado (20-30 linhas) via `ai_query`.
# MAGIC
# MAGIC - `grade` (green/yellow/red) é calculado **deterministicamente** a partir de
# MAGIC   agregados (nota média + taxa de bug + toxicidade), não pelo LLM.
# MAGIC - Saída em `weekly_reports`.

# COMMAND ----------

dbutils.widgets.text("catalog", "player_feedback_catalog")
dbutils.widgets.text("schema", "player_feedback")
dbutils.widgets.text("ai_model", "databricks-meta-llama-3-3-70b-instruct")
dbutils.widgets.text("sample_size", "700")
dbutils.widgets.text("report_window_days", "7")

catalog = dbutils.widgets.get("catalog")
schema = dbutils.widgets.get("schema")
ai_model = dbutils.widgets.get("ai_model")
sample_size = int(dbutils.widgets.get("sample_size"))
window_days = int(dbutils.widgets.get("report_window_days"))

enriched = f"`{catalog}`.`{schema}`.reviews_enriched"
reports = f"`{catalog}`.`{schema}`.weekly_reports"

# COMMAND ----------

from pyspark.sql import functions as F
from datetime import date, timedelta

# Segunda-feira da semana atual (ISO) como chave do relatório.
today = date.today()
report_week = today - timedelta(days=today.weekday())
print(f"report_week = {report_week} | janela = últimos {window_days} dias")

# COMMAND ----------

# MAGIC %md ## Agregados determinísticos por jogo (janela de 7 dias)

# COMMAND ----------

agg = spark.sql(f"""
    WITH win AS (
        SELECT *
        FROM {enriched}
        WHERE at >= current_timestamp() - INTERVAL {window_days} DAYS
          AND content IS NOT NULL
    )
    SELECT
        game,
        COUNT(*)                                         AS n_reviews,
        AVG(score)                                       AS avg_score,
        DATE(MIN(at))                                    AS window_start,
        DATE(MAX(at))                                    AS window_end,
        AVG(CASE WHEN bug_report THEN 1.0 ELSE 0.0 END)  AS bug_rate,
        AVG(CASE WHEN toxicity  THEN 1.0 ELSE 0.0 END)   AS tox_rate,
        AVG(CASE WHEN lower(sentiment) = 'negative' THEN 1.0 ELSE 0.0 END) AS neg_rate
    FROM win
    GROUP BY game
""")
display(agg)

# COMMAND ----------

def grade_of(avg_score, bug_rate, neg_rate):
    """Regra determinística de nota (não usa LLM)."""
    if avg_score is None:
        return "yellow"
    if avg_score >= 4.0 and bug_rate < 0.15 and neg_rate < 0.30:
        return "green"
    if avg_score < 3.0 or bug_rate >= 0.35 or neg_rate >= 0.55:
        return "red"
    return "yellow"

# COMMAND ----------

# MAGIC %md ## Amostra + geração do relatório textual por jogo

# COMMAND ----------

agg_rows = {r["game"]: r for r in agg.collect()}
out_rows = []

for game, a in agg_rows.items():
    # Amostra aleatória de até `sample_size` comentários da janela.
    sample = spark.sql(f"""
        SELECT content, score, sentiment,
               bug_report, pricing, game_balance, opinion,
               community, toxicity, visuals
        FROM {enriched}
        WHERE game = '{game}'
          AND at >= current_timestamp() - INTERVAL {window_days} DAYS
          AND content IS NOT NULL
        ORDER BY rand()
        LIMIT {sample_size}
    """)

    # Concatena os comentários amostrados num único blob para o prompt.
    blob = "\n".join(
        f"- ({r['score']}/5, {r['sentiment']}) {r['content']}"
        for r in sample.collect()
    )

    period = f"{a['window_start']} to {a['window_end']}"
    prompt = (
        f"You are a product analyst. Below is a random sample "
        f"of player reviews for the game '{game}' collected in the last {window_days} "
        f"days (period covered: {period}). "
        f"Write a consolidated report in Brazilian Portuguese, between 20 and 30 lines, "
        f"covering: overall sentiment, top reported bugs, pricing/monetization feedback, "
        f"game balance and matchmaking, community/social remarks, toxicity signals, and "
        f"visuals. Start by stating the period covered ({period}) and the number of "
        f"reviews analyzed ({int(a['n_reviews'])}). "
        f"End with a section titled 'Principais tópicos da semana' containing 2 to 4 "
        f"bullet points with the most relevant themes that actually stood out in this "
        f"week's reviews. Only include a bullet if there is a real recurring signal — "
        f"if nothing notable stood out, write a single line saying the week was stable "
        f"without notable topics. Do NOT invent topics and do NOT give recommendations. "
        f"Be specific and cite recurring themes. Reviews:\n{blob}"
    )
    # Escapa aspas simples para embutir no SQL.
    prompt_sql = prompt.replace("'", "''")

    report_text = spark.sql(
        f"SELECT ai_query('{ai_model}', '{prompt_sql}') AS r"
    ).collect()[0]["r"]

    grade = grade_of(a["avg_score"], a["bug_rate"], a["neg_rate"])

    out_rows.append({
        "report_week": report_week,
        "game": game,
        "grade": grade,
        "report": report_text,
        "window_start": a["window_start"],
        "window_end": a["window_end"],
        "n_reviews": int(a["n_reviews"]),
        "avg_score": float(a["avg_score"]) if a["avg_score"] is not None else None,
    })
    print(f"  {game:14s} → grade={grade} | n={a['n_reviews']} "
          f"| {a['window_start']}→{a['window_end']}")

# COMMAND ----------

# MAGIC %md ## Grava em weekly_reports (idempotente por report_week+game)

# COMMAND ----------

if not out_rows:
    print("Nenhum jogo com reviews na janela. Nada a gravar.")
    dbutils.notebook.exit("sem dados")

from pyspark.sql.types import (
    StructType, StructField, DateType, StringType, IntegerType, DoubleType,
)

out_schema = StructType([
    StructField("report_week", DateType()),
    StructField("game", StringType()),
    StructField("grade", StringType()),
    StructField("report", StringType()),
    StructField("window_start", DateType()),
    StructField("window_end", DateType()),
    StructField("n_reviews", IntegerType()),
    StructField("avg_score", DoubleType()),
])

df = (spark.createDataFrame(out_rows, schema=out_schema)
      .withColumn("_generated_at", F.current_timestamp()))
df.createOrReplaceTempView("new_reports")

# MERGE: reexecutar na mesma semana substitui o relatório do jogo.
spark.sql(f"""
    MERGE INTO {reports} AS t
    USING new_reports AS s
    ON t.report_week = s.report_week AND t.game = s.game
    WHEN MATCHED THEN UPDATE SET *
    WHEN NOT MATCHED THEN INSERT *
""")

print(f"Gravados {len(out_rows)} relatórios para a semana {report_week}.")
display(spark.sql(
    f"SELECT report_week, game, grade, window_start, window_end, n_reviews, avg_score "
    f"FROM {reports} WHERE report_week = '{report_week}' ORDER BY game"
))
