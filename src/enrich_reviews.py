# ---------------------------------------------------------------------------
# SDP — Enriquecimento de reviews com AI functions
#
# Streaming table lendo o bronze append-only (reviews_raw) e classificando cada
# comentário em 7 dimensões + sentimento. Por ser streaming, só processa linhas
# novas: cada review é enriquecido uma única vez (AI function é cara).
#
# As dimensões são classificadas em UMA chamada ai_query com saída estruturada
# (responseFormat json_schema) — mais barato que 7 ai_classify separados.
# O sentimento usa ai_analyze_sentiment (função nativa dedicada).
# ---------------------------------------------------------------------------
import dlt
from pyspark.sql import functions as F

CATALOG = spark.conf.get("pf.catalog")
SCHEMA = spark.conf.get("pf.schema")
AI_MODEL = "databricks-meta-llama-3-3-70b-instruct"

SOURCE = f"`{CATALOG}`.`{SCHEMA}`.reviews_raw"

DIMENSIONS = [
    "bug_report", "pricing", "game_balance",
    "opinion", "community", "toxicity", "visuals",
]

# Schema JSON forçado na resposta do LLM: um booleano por dimensão.
_props = ",".join(f'\\"{d}\\":{{\\"type\\":\\"boolean\\"}}' for d in DIMENSIONS)
_RESPONSE_FORMAT = (
    '{\\"type\\":\\"json_schema\\",\\"json_schema\\":{\\"name\\":\\"dims\\",'
    '\\"strict\\":true,\\"schema\\":{\\"type\\":\\"object\\",\\"properties\\":{'
    + _props +
    '},\\"required\\":[' + ",".join(f'\\"{d}\\"' for d in DIMENSIONS) + ']}}}'
)

_PROMPT = (
    "You are analyzing a mobile game review. Decide, for each dimension, whether "
    "the review is about it (true/false). Dimensions: "
    "bug_report (crashes, errors, technical issues), "
    "pricing (cost, in-app purchases, refunds, value for money), "
    "game_balance (difficulty, fairness, matchmaking, pay-to-win), "
    "opinion (general like/dislike without specifics), "
    "community (players, chat, teams, social features), "
    "toxicity (offensive, abusive or hateful language), "
    "visuals (graphics, art, UI, animations). Review: "
)


@dlt.table(
    name=f"{CATALOG}.{SCHEMA}.reviews_enriched",
    comment=(
        "Reviews enriquecidos com AI functions: 7 dimensões booleanas + "
        "sentimento. Streaming table incremental (uma inferência por review)."
    ),
    table_properties={"quality": "silver"},
)
def reviews_enriched():
    src = spark.readStream.table(SOURCE)

    # Só classifica reviews com texto. Reviews sem content passam com flags nulas.
    has_text = F.col("content").isNotNull() & (F.length(F.trim(F.col("content"))) > 0)

    # ai_query com saída estruturada → STRING JSON; parseamos em struct.
    dims_json = F.expr(
        f"ai_query('{AI_MODEL}', concat('{_PROMPT}', content), "
        f"responseFormat => '{_RESPONSE_FORMAT}')"
    )

    dims_schema = "struct<" + ",".join(f"{d}:boolean" for d in DIMENSIONS) + ">"

    enriched = (
        src
        .withColumn(
            "_dims_json",
            F.when(has_text, dims_json).otherwise(F.lit(None)),
        )
        .withColumn("_dims", F.from_json(F.col("_dims_json"), dims_schema))
        .withColumn(
            "sentiment",
            F.when(has_text, F.expr("ai_analyze_sentiment(content)")).otherwise(F.lit(None)),
        )
    )

    # Explode a struct de dimensões em colunas booleanas de topo.
    for d in DIMENSIONS:
        enriched = enriched.withColumn(d, F.col(f"_dims.{d}"))

    return (
        enriched
        .withColumn("_enriched_at", F.current_timestamp())
        .drop("_dims_json", "_dims")
    )
