# Databricks notebook source
# MAGIC %md
# MAGIC # Relatório semanal por jogo
# MAGIC
# MAGIC Gera relatório por jogo sobre uma janela móvel configurável e registra cada
# MAGIC chamada `ai_query` em uma tabela Delta de auditoria governada.

# COMMAND ----------

dbutils.widgets.text("catalog", "perdomo_demos_catalog")
dbutils.widgets.text("schema", "febar_player_feedback")
dbutils.widgets.text("ai_model", "databricks-meta-llama-3-3-70b-instruct")
dbutils.widgets.text("sample_size", "700")
dbutils.widgets.text("report_window_days", "7")

catalog = dbutils.widgets.get("catalog")
schema = dbutils.widgets.get("schema")
ai_model = dbutils.widgets.get("ai_model")
sample_size = int(dbutils.widgets.get("sample_size"))
window_days = int(dbutils.widgets.get("report_window_days"))

if sample_size <= 0 or window_days <= 0:
    raise ValueError("sample_size e report_window_days devem ser positivos")

enriched = f"`{catalog}`.`{schema}`.reviews_enriched"
reports = f"`{catalog}`.`{schema}`.weekly_reports"
audit_reports = f"`{catalog}`.`{schema}`.ai_inference_log_reports"
PROMPT_VERSION = "weekly_report_v1"

# COMMAND ----------

import re
from datetime import date, datetime, timedelta
from pyspark.sql import functions as F
from pyspark.sql.types import (
    DateType,
    DoubleType,
    IntegerType,
    LongType,
    StringType,
    StructField,
    StructType,
    TimestampType,
)

if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,254}", ai_model):
    raise ValueError("ai_model contém caracteres inválidos para um endpoint")
escaped_ai_model = ai_model.replace("'", "''")

# Segunda-feira da semana atual (ISO) como chave idempotente do relatório.
today = date.today()
report_week = today - timedelta(days=today.weekday())
print(f"report_week = {report_week} | janela móvel = últimos {window_days} dias")

# COMMAND ----------

# MAGIC %md ## Agregados determinísticos por jogo

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
        AVG(CASE WHEN toxicity THEN 1.0 ELSE 0.0 END)    AS tox_rate,
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

# MAGIC %md ## Amostra, inferência e audit trail

# COMMAND ----------

agg_rows = {row["game"]: row for row in agg.collect()}
out_rows = []
audit_rows = []

for game, aggregates in agg_rows.items():
    sample = spark.sql(
        f"""
        SELECT content, score, sentiment,
               bug_report, pricing, game_balance, opinion,
               community, toxicity, visuals
        FROM {enriched}
        WHERE game = :game
          AND at >= current_timestamp() - INTERVAL {window_days} DAYS
          AND content IS NOT NULL
        ORDER BY rand()
        LIMIT {sample_size}
        """,
        args={"game": game},
    )
    sampled_rows = sample.collect()

    blob = "\n".join(
        f"- ({row['score']}/5, {row['sentiment']}) {row['content']}"
        for row in sampled_rows
    )
    period = f"{aggregates['window_start']} to {aggregates['window_end']}"
    prompt = (
        f"You are a product analyst at a mobile game studio. Below is a random sample "
        f"of player reviews for the game '{game}' collected in the last {window_days} "
        f"days (period covered: {period}). "
        f"Write a consolidated report in Brazilian Portuguese, between 20 and 30 lines, "
        f"covering: overall sentiment, top reported bugs, pricing/monetization feedback, "
        f"game balance and matchmaking, community/social remarks, toxicity signals, and "
        f"visuals. Start by stating the period covered ({period}), the total reviews in "
        f"the window ({int(aggregates['n_reviews'])}), and the sampled reviews used "
        f"({len(sampled_rows)}). End with a section titled 'Principais tópicos da semana' "
        f"containing 2 to 4 bullet points with recurring themes. Do not invent topics or "
        f"give recommendations. Reviews:\n{blob}"
    )

    inference = spark.sql(
        f"SELECT ai_query('{escaped_ai_model}', :prompt, failOnError => false) AS result",
        args={"prompt": prompt},
    ).collect()[0]["result"]
    report_text = inference["result"]
    error_message = inference["errorMessage"]
    inferred_at = datetime.utcnow()

    audit_rows.append({
        "report_week": report_week,
        "game": game,
        "source": "weekly_report",
        "model": ai_model,
        "prompt_version": PROMPT_VERSION,
        "prompt_text": prompt,
        "n_sampled": len(sampled_rows),
        "raw_response": report_text,
        "error_message": error_message,
        "inferred_at": inferred_at,
    })

    if error_message is not None or report_text is None:
        print(
            f"  {game:14s} → inferência falhou; auditoria gravada e relatório anterior preservado"
        )
        continue

    grade = grade_of(
        aggregates["avg_score"], aggregates["bug_rate"], aggregates["neg_rate"]
    )
    out_rows.append({
        "report_week": report_week,
        "game": game,
        "grade": grade,
        "report": report_text,
        "window_start": aggregates["window_start"],
        "window_end": aggregates["window_end"],
        "n_reviews": int(aggregates["n_reviews"]),
        "avg_score": (
            float(aggregates["avg_score"])
            if aggregates["avg_score"] is not None
            else None
        ),
        "bug_report_rate": float(aggregates["bug_rate"] or 0.0),
        "negative_rate": float(aggregates["neg_rate"] or 0.0),
        "toxicity_rate": float(aggregates["tox_rate"] or 0.0),
    })
    print(
        f"  {game:14s} → grade={grade} | total={aggregates['n_reviews']} "
        f"| sample={len(sampled_rows)} | erro={bool(error_message)}"
    )

# COMMAND ----------

# MAGIC %md ## Grava auditoria append-only e relatório idempotente

# COMMAND ----------

audit_schema = StructType([
    StructField("report_week", DateType()),
    StructField("game", StringType()),
    StructField("source", StringType()),
    StructField("model", StringType()),
    StructField("prompt_version", StringType()),
    StructField("prompt_text", StringType()),
    StructField("n_sampled", LongType()),
    StructField("raw_response", StringType()),
    StructField("error_message", StringType()),
    StructField("inferred_at", TimestampType()),
])
if audit_rows:
    spark.createDataFrame(audit_rows, schema=audit_schema).write.mode("append").saveAsTable(
        audit_reports
    )

if not out_rows:
    print("Nenhum relatório novo válido; auditoria registrada e dados existentes preservados.")
    dbutils.notebook.exit("sem relatórios válidos")

report_schema = StructType([
    StructField("report_week", DateType()),
    StructField("game", StringType()),
    StructField("grade", StringType()),
    StructField("report", StringType()),
    StructField("window_start", DateType()),
    StructField("window_end", DateType()),
    StructField("n_reviews", IntegerType()),
    StructField("avg_score", DoubleType()),
    StructField("bug_report_rate", DoubleType()),
    StructField("negative_rate", DoubleType()),
    StructField("toxicity_rate", DoubleType()),
])

report_df = (
    spark.createDataFrame(out_rows, schema=report_schema)
    .withColumn("_generated_at", F.current_timestamp())
)
report_df.createOrReplaceTempView("new_reports")

spark.sql(f"""
    MERGE INTO {reports} AS target
    USING new_reports AS source
    ON target.report_week = source.report_week AND target.game = source.game
    WHEN MATCHED THEN UPDATE SET *
    WHEN NOT MATCHED THEN INSERT *
""")

print(f"Gravados {len(out_rows)} relatórios para a semana {report_week}.")
display(spark.sql(
    f"""
    SELECT report_week, game, grade, window_start, window_end, n_reviews,
           avg_score, bug_report_rate, negative_rate, toxicity_rate
    FROM {reports}
    WHERE report_week = :report_week
    ORDER BY game
    """,
    args={"report_week": report_week},
))
