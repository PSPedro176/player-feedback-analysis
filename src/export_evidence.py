# Databricks notebook source
# MAGIC %md
# MAGIC # Export de evidências FE Bar
# MAGIC
# MAGIC Gera um pacote imutável por execução em um UC Volume, com arquivos Markdown,
# MAGIC CSV e JSON cobrindo dados, inferências, jobs, pipeline e expectations.

# COMMAND ----------

dbutils.widgets.text("catalog", "perdomo_demos_catalog")
dbutils.widgets.text("schema", "febar_player_feedback")
dbutils.widgets.text("pipeline_id", "")
dbutils.widgets.text("job_ids", "{}")
dbutils.widgets.text("genie_setup_job_id", "")

catalog = dbutils.widgets.get("catalog")
schema = dbutils.widgets.get("schema")
pipeline_id = dbutils.widgets.get("pipeline_id")

# COMMAND ----------

import csv
import json
import os
from datetime import date, datetime
from decimal import Decimal
from itertools import islice

from databricks.sdk import WorkspaceClient

w = WorkspaceClient()
job_ids = json.loads(dbutils.widgets.get("job_ids"))
genie_setup_job_id = dbutils.widgets.get("genie_setup_job_id").strip()
if genie_setup_job_id:
    job_ids["pf_febar_genie_setup"] = genie_setup_job_id
run_ts = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
evidence_dir = f"/Volumes/{catalog}/{schema}/evidence/{run_ts}"
os.makedirs(evidence_dir, exist_ok=True)


# COMMAND ----------


def json_value(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if hasattr(value, "as_dict"):
        return {key: json_value(item) for key, item in value.as_dict().items()}
    if isinstance(value, dict):
        return {key: json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_value(item) for item in value]
    return value


def rows_from_df(dataframe):
    return [json_value(row.asDict(recursive=True)) for row in dataframe.collect()]


def write_json(filename, rows):
    path = os.path.join(evidence_dir, filename)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(rows, handle, ensure_ascii=False, indent=2, default=json_value)
    return path


def write_csv(filename, rows):
    path = os.path.join(evidence_dir, filename)
    fieldnames = []
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        if fieldnames:
            writer.writeheader()
            for row in rows:
                writer.writerow({
                    key: json.dumps(value, ensure_ascii=False)
                    if isinstance(value, (dict, list))
                    else value
                    for key, value in row.items()
                })
    return path


def write_dataset(stem, rows):
    write_csv(f"{stem}.csv", rows)
    write_json(f"{stem}.json", rows)


def enum_value(value):
    if value is None:
        return None
    return getattr(value, "value", str(value))


# COMMAND ----------

# MAGIC %md ## Contagens e distribuições

# COMMAND ----------

objects = spark.sql(f"SHOW TABLES IN `{catalog}`.`{schema}`").collect()
row_counts = []
for obj in objects:
    object_name = obj["tableName"]
    qualified = f"`{catalog}`.`{schema}`.`{object_name}`"
    try:
        count = spark.sql(f"SELECT count(*) AS n FROM {qualified}").collect()[0]["n"]
        row_counts.append({"object_name": object_name, "row_count": int(count), "error": None})
    except Exception as error:
        row_counts.append({"object_name": object_name, "row_count": None, "error": str(error)})
write_dataset("row_counts", row_counts)

classification_distribution = rows_from_df(spark.sql(f"""
    SELECT
        game,
        lower(sentiment) AS sentiment,
        count(*) AS n_reviews,
        sum(CASE WHEN bug_report THEN 1 ELSE 0 END) AS n_bug_reports,
        sum(CASE WHEN pricing THEN 1 ELSE 0 END) AS n_pricing,
        sum(CASE WHEN game_balance THEN 1 ELSE 0 END) AS n_game_balance,
        sum(CASE WHEN toxicity THEN 1 ELSE 0 END) AS n_toxicity,
        sum(CASE WHEN visuals THEN 1 ELSE 0 END) AS n_visuals,
        sum(CASE WHEN community THEN 1 ELSE 0 END) AS n_community,
        sum(CASE WHEN opinion THEN 1 ELSE 0 END) AS n_opinion
    FROM `{catalog}`.`{schema}`.reviews_enriched
    GROUP BY game, lower(sentiment)
    ORDER BY game, sentiment
"""))
write_dataset("classification_distribution", classification_distribution)

sample_reviews = rows_from_df(spark.sql(f"""
    WITH ranked AS (
        SELECT
            sha2(review_id, 256) AS review_id_hash,
            game,
            at,
            score,
            sentiment,
            bug_report,
            pricing,
            game_balance,
            toxicity,
            visuals,
            community,
            opinion,
            substring(content, 1, 300) AS review_text,
            row_number() OVER (PARTITION BY game ORDER BY rand()) AS sample_rank
        FROM `{catalog}`.`{schema}`.reviews_enriched
        WHERE content IS NOT NULL
    )
    SELECT review_id_hash, game, at, score, sentiment,
           bug_report, pricing, game_balance, toxicity, visuals, community, opinion,
           review_text
    FROM ranked
    WHERE sample_rank <= 20
    ORDER BY game, sample_rank
"""))
write_dataset("sample_classified_reviews", sample_reviews)

# COMMAND ----------

# MAGIC %md ## Relatórios e visão semanal

# COMMAND ----------

latest_reports = rows_from_df(spark.sql(f"""
    WITH ranked AS (
        SELECT *, row_number() OVER (
            PARTITION BY game ORDER BY report_week DESC, _generated_at DESC
        ) AS row_number
        FROM `{catalog}`.`{schema}`.weekly_reports
    )
    SELECT report_week, game, grade, report, window_start, window_end, n_reviews,
           avg_score, bug_report_rate, negative_rate, toxicity_rate, _generated_at
    FROM ranked
    WHERE row_number = 1
    ORDER BY game
"""))
write_dataset("latest_weekly_reports", latest_reports)

weekly_summary = rows_from_df(spark.sql(f"""
    WITH ranked_weeks AS (
        SELECT *, dense_rank() OVER (ORDER BY week_start DESC) AS week_rank
        FROM `{catalog}`.`{schema}`.weekly_game_summary
    )
    SELECT game, week_start, week_end, n_reviews, avg_score,
           n_positive, n_negative, n_neutral, n_mixed,
           n_bug_reports, n_pricing, n_game_balance, n_toxicity,
           n_visuals, n_community, n_opinion,
           bug_report_rate, negative_rate, toxicity_rate
    FROM ranked_weeks
    WHERE week_rank <= 4
    ORDER BY week_start DESC, game
"""))
write_dataset("weekly_game_summary_last_4_weeks", weekly_summary)

# COMMAND ----------

# MAGIC %md ## Auditoria de AI

# COMMAND ----------

ai_stats = rows_from_df(spark.sql(f"""
    SELECT
        source,
        model,
        count(*) AS calls,
        sum(CASE WHEN error_message IS NOT NULL THEN 1 ELSE 0 END) AS errors,
        CAST(avg(CASE WHEN error_message IS NOT NULL THEN 1.0 ELSE 0.0 END) AS DOUBLE)
            AS error_rate,
        min(inferred_at) AS first_inference,
        max(inferred_at) AS latest_inference
    FROM `{catalog}`.`{schema}`.ai_inference_log
    GROUP BY source, model
    ORDER BY source, model
"""))
write_dataset("ai_inference_stats", ai_stats)

ai_samples = rows_from_df(spark.sql(f"""
    SELECT source, game, sha2(record_key, 256) AS record_key_hash, model, prompt_version,
           substring(raw_response, 1, 1000) AS raw_response,
           error_message, inferred_at
    FROM `{catalog}`.`{schema}`.ai_inference_log
    ORDER BY rand()
    LIMIT 5
"""))
write_dataset("ai_inference_samples", ai_samples)

# COMMAND ----------

# MAGIC %md ## Histórico operacional do bundle

# COMMAND ----------

job_runs = []
for job_name, job_id in job_ids.items():
    if not job_id:
        job_runs.append({
            "job_name": job_name,
            "job_id": None,
            "run_id": None,
            "state": "JOB_ID_NOT_SUPPLIED",
            "duration_ms": None,
        })
        continue

    runs = w.jobs.list_runs(job_id=int(job_id), limit=10)
    for run in islice(runs, 10):
        duration_ms = run.execution_duration
        if duration_ms is None and run.start_time and run.end_time:
            duration_ms = run.end_time - run.start_time
        job_runs.append({
            "job_name": job_name,
            "job_id": int(job_id),
            "run_id": run.run_id,
            "run_name": run.run_name,
            "state": enum_value(run.state.life_cycle_state) if run.state else None,
            "result_state": enum_value(run.state.result_state) if run.state else None,
            "state_message": run.state.state_message if run.state else None,
            "start_time": run.start_time,
            "end_time": run.end_time,
            "duration_ms": duration_ms,
            "run_page_url": run.run_page_url,
        })
write_dataset("job_run_history", job_runs)

pipeline_updates = []
expectation_events = []
if pipeline_id:
    updates_payload = w.api_client.do(
        "GET",
        f"/api/2.0/pipelines/{pipeline_id}/updates",
        query={"max_results": 10},
    )
    pipeline_updates = json_value(updates_payload.get("updates", []))
    escaped_pipeline_id = pipeline_id.replace("'", "''")
    expectation_events = rows_from_df(spark.sql(f"""
        SELECT timestamp, event_type, origin.update_id AS update_id, details
        FROM event_log('{escaped_pipeline_id}')
        WHERE event_type = 'flow_progress'
          AND details LIKE '%expectations%'
        ORDER BY timestamp DESC
        LIMIT 100
    """))
else:
    pipeline_updates = [{"error": "pipeline_id não informado"}]
    expectation_events = [{"error": "pipeline_id não informado"}]

write_dataset("pipeline_update_history", pipeline_updates)
write_dataset("pipeline_expectation_results", expectation_events)

# COMMAND ----------

# MAGIC %md ## Índice Markdown

# COMMAND ----------

calls = sum(int(row.get("calls") or 0) for row in ai_stats)
errors = sum(int(row.get("errors") or 0) for row in ai_stats)
markdown = f"""# FE Bar — Player Feedback Evidence

- Generated at (UTC): `{run_ts}`
- Catalog/schema: `{catalog}.{schema}`
- Pipeline ID: `{pipeline_id or 'not supplied'}`
- Objects inventoried: `{len(row_counts)}`
- Sample classified reviews: `{len(sample_reviews)}`
- Latest game reports: `{len(latest_reports)}`
- AI calls logged: `{calls}`
- AI errors logged: `{errors}`

## Files

- `row_counts.csv` / `row_counts.json`
- `classification_distribution.csv` / `classification_distribution.json`
- `sample_classified_reviews.csv` / `sample_classified_reviews.json`
- `latest_weekly_reports.csv` / `latest_weekly_reports.json`
- `weekly_game_summary_last_4_weeks.csv` / `weekly_game_summary_last_4_weeks.json`
- `ai_inference_stats.csv` / `ai_inference_stats.json`
- `ai_inference_samples.csv` / `ai_inference_samples.json`
- `job_run_history.csv` / `job_run_history.json`
- `pipeline_update_history.csv` / `pipeline_update_history.json`
- `pipeline_expectation_results.csv` / `pipeline_expectation_results.json`

The weekly report uses a rolling configurable window (7 days by default). The
`weekly_game_summary` view uses Monday-through-Sunday ISO calendar weeks.
"""
with open(os.path.join(evidence_dir, "README.md"), "w", encoding="utf-8") as handle:
    handle.write(markdown)

print(f"Evidence exported to {evidence_dir}")
dbutils.notebook.exit(evidence_dir)
