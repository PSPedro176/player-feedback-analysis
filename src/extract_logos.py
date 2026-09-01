# Databricks notebook source
# MAGIC %md
# MAGIC # Coleta de logos dos jogos
# MAGIC Para cada jogo em `games_current`, baixa o ícone da Play Store (via `google-play-scraper`)
# MAGIC e grava/atualiza em `/Volumes/{catalog}/{schema}/game_logos/{package}.png`.
# MAGIC Idempotente — cobre jogos novos e troca de arte. O App serve os logos desse Volume.

# COMMAND ----------

# MAGIC %pip install google-play-scraper
# MAGIC %restart_python

# COMMAND ----------

import os
import requests
from google_play_scraper import app as gp_app

dbutils.widgets.text("catalog", "player_feedback_catalog")
dbutils.widgets.text("schema", "player_feedback")

catalog = dbutils.widgets.get("catalog")
schema = dbutils.widgets.get("schema")

games_current = f"`{catalog}`.`{schema}`.games_current"
volume_dir = f"/Volumes/{catalog}/{schema}/game_logos"
os.makedirs(volume_dir, exist_ok=True)

# COMMAND ----------

games = spark.sql(
    f"SELECT game, package_name FROM {games_current} WHERE active"
).collect()

if not games:
    print("Nenhum jogo cadastrado. Nada a coletar.")
    dbutils.notebook.exit("sem jogos")

for row in games:
    package = row["package_name"]
    try:
        meta = gp_app(package)
        icon_url = meta["icon"]
        content = requests.get(icon_url, timeout=30).content
        dest = f"{volume_dir}/{package}.png"
        with open(dest, "wb") as f:
            f.write(content)
        print(f"  {row['game']:16s} → {dest} ({len(content)} bytes)")
    except Exception as e:
        print(f"  {row['game']:16s} [{package}] FALHOU: {e}")

print("Coleta de logos concluída.")
