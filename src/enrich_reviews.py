# ---------------------------------------------------------------------------
# SDP — Enriquecimento de reviews com AI functions
#
# A tabela intermediária materializa cada chamada ao modelo uma única vez. Dela
# derivam a tabela de reviews enriquecidos e o log governado de inferências.
# ---------------------------------------------------------------------------
import dlt
from pyspark.sql import functions as F
from pyspark.sql.types import (
    BooleanType,
    IntegerType,
    StringType,
    StructField,
    StructType,
    TimestampType,
)

CATALOG = spark.conf.get("pf.catalog")
SCHEMA = spark.conf.get("pf.schema")
AI_MODEL = spark.conf.get("pf.ai_model")

SOURCE = f"`{CATALOG}`.`{SCHEMA}`.reviews_raw"
PROMPT_VERSION = "enrichment_dimensions_v1"

DIMENSIONS = [
    "bug_report", "pricing", "game_balance",
    "opinion", "community", "toxicity", "visuals",
]

_props = ",".join(f'\\"{dimension}\\":{{\\"type\\":\\"boolean\\"}}' for dimension in DIMENSIONS)
_RESPONSE_FORMAT = (
    '{\\"type\\":\\"json_schema\\",\\"json_schema\\":{\\"name\\":\\"dims\\",'
    '\\"strict\\":true,\\"schema\\":{\\"type\\":\\"object\\",\\"properties\\":{'
    + _props
    + '},\\"required\\":['
    + ",".join(f'\\"{dimension}\\"' for dimension in DIMENSIONS)
    + ']}}}'
)

_PROMPT_TEMPLATE = (
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

_ESCAPED_MODEL = AI_MODEL.replace("'", "''")
_ESCAPED_RESPONSE_FORMAT = _RESPONSE_FORMAT.replace("'", "''")
_DIMS_SCHEMA = "struct<" + ",".join(f"{dimension}:boolean" for dimension in DIMENSIONS) + ">"


def commented_field(name, data_type, comment):
    return StructField(name, data_type, True, {"comment": comment})


REVIEWS_ENRICHED_SCHEMA = StructType([
    commented_field("review_id", StringType(), "Identificador único do review na Play Store."),
    commented_field("game", StringType(), "Nome canônico do jogo cadastrado."),
    commented_field("package_name", StringType(), "Package name do jogo na Play Store."),
    commented_field("language", StringType(), "Idioma usado na coleta do review."),
    commented_field("user_name", StringType(), "Nome público do autor na Play Store."),
    commented_field("content", StringType(), "Texto público do review usado na classificação."),
    commented_field("score", IntegerType(), "Nota de 1 a 5 atribuída pelo jogador."),
    commented_field("thumbs_up_count", IntegerType(), "Quantidade de votos úteis do review."),
    commented_field("review_created_version", StringType(), "Versão do jogo informada no review."),
    commented_field("at", TimestampType(), "Data e hora de publicação; base das semanas ISO."),
    commented_field("reply_content", StringType(), "Resposta pública do desenvolvedor."),
    commented_field("replied_at", TimestampType(), "Data e hora da resposta do desenvolvedor."),
    commented_field("app_version", StringType(), "Versão atual do aplicativo observada na coleta."),
    commented_field("_ingested_at", TimestampType(), "Momento em que o review foi ingerido."),
    commented_field("sentiment", StringType(), "Sentimento inferido: positive, negative, neutral ou mixed."),
    commented_field("bug_report", BooleanType(), "Indica menção a crash, erro ou problema técnico."),
    commented_field("pricing", BooleanType(), "Indica feedback sobre preço, compra, reembolso ou monetização."),
    commented_field("game_balance", BooleanType(), "Indica feedback sobre dificuldade, justiça, matchmaking ou pay-to-win."),
    commented_field("opinion", BooleanType(), "Indica opinião geral sem tema específico predominante."),
    commented_field("community", BooleanType(), "Indica feedback sobre jogadores, chat, times ou recursos sociais."),
    commented_field("toxicity", BooleanType(), "Indica linguagem ofensiva, abusiva ou de ódio."),
    commented_field("visuals", BooleanType(), "Indica feedback sobre gráficos, arte, UI ou animações."),
    commented_field("_enriched_at", TimestampType(), "Momento em que a inferência foi materializada."),
])

AI_LOG_SCHEMA = StructType([
    commented_field("review_id", StringType(), "Identificador do review associado à chamada."),
    commented_field("game", StringType(), "Jogo associado à chamada."),
    commented_field("source", StringType(), "Origem fixa enrichment."),
    commented_field("model", StringType(), "Serving endpoint usado pelo ai_query."),
    commented_field("prompt_version", StringType(), "Versão controlada do template de prompt."),
    commented_field("prompt_text", StringType(), "Prompt completo enviado ao modelo."),
    commented_field("raw_response", StringType(), "Resposta bruta retornada pelo modelo."),
    commented_field("error_message", StringType(), "Erro retornado com failOnError=false."),
    commented_field("inferred_at", TimestampType(), "Momento da chamada ao modelo."),
])


@dlt.table(
    name=f"{CATALOG}.{SCHEMA}.reviews_enrichment_inference",
    comment=(
        "Materialização interna das chamadas ai_query de enriquecimento, incluindo "
        "resposta bruta e erro para evitar inferências duplicadas nos consumidores."
    ),
    table_properties={"quality": "silver"},
)
def reviews_enrichment_inference():
    source = spark.readStream.table(SOURCE)
    has_text = F.col("content").isNotNull() & (F.length(F.trim(F.col("content"))) > 0)

    prompt_text = F.concat(F.lit(_PROMPT_TEMPLATE), F.col("content"))
    ai_result = F.expr(
        f"ai_query('{_ESCAPED_MODEL}', _prompt_text, failOnError => false, "
        f"responseFormat => '{_ESCAPED_RESPONSE_FORMAT}')"
    )

    return (
        source
        .withColumn("_prompt_text", F.when(has_text, prompt_text))
        .withColumn("_ai_result", F.when(has_text, ai_result))
        .withColumn("_raw_response", F.col("_ai_result.response"))
        .withColumn("_error_message", F.col("_ai_result.errorMessage"))
        .withColumn("_dims", F.from_json(F.col("_raw_response"), _DIMS_SCHEMA))
        .withColumn(
            "sentiment",
            F.when(has_text, F.expr("ai_analyze_sentiment(content)")),
        )
        .withColumn("_model", F.lit(AI_MODEL))
        .withColumn("_prompt_version", F.lit(PROMPT_VERSION))
        .withColumn("_inferred_at", F.current_timestamp())
    )


_REVIEW_EXPECTATIONS = {
    "review_id_not_null": "review_id IS NOT NULL",
    "review_text_not_blank": "content IS NOT NULL AND length(trim(content)) > 0",
    "score_between_1_and_5": "score BETWEEN 1 AND 5",
    "valid_sentiment": "sentiment IS NULL OR lower(sentiment) IN ('positive', 'negative', 'neutral', 'mixed')",
}


@dlt.table(
    name=f"{CATALOG}.{SCHEMA}.reviews_enriched",
    comment=(
        "Silver: reviews da Play Store enriquecidos por AI com sentimento e sete "
        "rótulos temáticos booleanos."
    ),
    schema=REVIEWS_ENRICHED_SCHEMA,
    table_properties={"quality": "silver"},
)
@dlt.expect_all(_REVIEW_EXPECTATIONS)
def reviews_enriched():
    enriched = spark.readStream.table(
        f"`{CATALOG}`.`{SCHEMA}`.reviews_enrichment_inference"
    )

    for dimension in DIMENSIONS:
        enriched = enriched.withColumn(dimension, F.col(f"_dims.{dimension}"))

    return (
        enriched
        .withColumn("_enriched_at", F.col("_inferred_at"))
        .drop(
            "_prompt_text",
            "_ai_result",
            "_raw_response",
            "_error_message",
            "_dims",
            "_model",
            "_prompt_version",
            "_inferred_at",
        )
    )


@dlt.table(
    name=f"{CATALOG}.{SCHEMA}.ai_inference_log_enrichment",
    comment=(
        "Audit trail governado das chamadas ai_query de classificação de reviews, "
        "incluindo prompt, resposta bruta e mensagem de erro."
    ),
    schema=AI_LOG_SCHEMA,
    table_properties={"quality": "silver"},
)
def ai_inference_log_enrichment():
    return (
        spark.readStream.table(
            f"`{CATALOG}`.`{SCHEMA}`.reviews_enrichment_inference"
        )
        .where(F.col("_prompt_text").isNotNull())
        .select(
            "review_id",
            "game",
            F.lit("enrichment").alias("source"),
            F.col("_model").alias("model"),
            F.col("_prompt_version").alias("prompt_version"),
            F.col("_prompt_text").alias("prompt_text"),
            F.col("_raw_response").alias("raw_response"),
            F.col("_error_message").alias("error_message"),
            F.col("_inferred_at").alias("inferred_at"),
        )
    )
