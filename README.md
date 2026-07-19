# Player Feedback Analysis — Wildlife

Demo Databricks inspirada no case público **Devsisters / Second Dinner / SEGA — "Player Feedback
Analysis"**, adaptada para os jogos mobile da **Wildlife Studios**. Coleta reviews da Google Play
Store, enriquece com **AI Functions**, gera relatórios semanais e serve tudo via **AI/BI Dashboard
(com Genie integrado)** e um **Databricks App**.

Tudo provisionado via **Databricks Asset Bundles (DABs)**.

## Arquitetura

```
Google Play Store ──(google-play-scraper)──▶ reviews_raw (bronze, append-only, dedup na fonte)
                                                    │
                                          SDP + AI Functions (incremental)
                                                    ▼
                                        reviews_enriched (7 dimensões + sentimento)
                                          │                         │
                              relatório semanal (ai_query)     AI/BI Dashboard + Genie
                                          ▼                         │
                                   weekly_reports            Databricks App (FastAPI + React)
```

- **Extração** (`src/jobs/extract_reviews.py`) — Job Python; paginação com `continuation_token`,
  dedup + filtro incremental **na fonte** (watermark `last_comment` por jogo), dedup por `review_id`.
  Modo `backfill_mode` para puxar histórico profundo.
- **Enriquecimento** (`src/pipeline/enrich_reviews.py`) — SDP streaming table; classifica cada review
  em 7 dimensões (bug, preço, balanceamento, opinião, comunidade, toxicidade, visual) + sentimento,
  via `ai_query` / `ai_classify` / `ai_analyze_sentiment`. Incremental (uma inferência por review).
- **Relatório semanal** (`src/jobs/weekly_report.py`) — Job; amostra por jogo dos últimos 7 dias,
  `ai_query` gera resumo consolidado + "Principais tópicos da semana"; `grade` determinístico.
- **AI/BI Dashboard** (`src/dashboard/player_feedback.lvdash.json`) — Lakeview; filtros globais
  (jogo/idioma/período/tipo), tendências de temas (share e absoluto móvel 7d), sentimento, nota,
  volume + %negativos, leitura de comentários. Genie nativo integrado.
- **App** (`app/`) — FastAPI + React/Vite/Tailwind; identidade visual Wildlife (editorial
  preto/branco), KPIs ao vivo, relatórios por jogo, dashboard AI/BI embeddado.

## Ambiente (FEVM)

- Workspace: `fe-vm-wildlife-s2s`
- Catálogo / schema: `wildlife_s2s_catalog.player_feedback`
- SQL Warehouse serverless: `ae8786c45629ac32`
- Modelo: `databricks-meta-llama-3-3-70b-instruct`
- Jogos monitorados: Sniper 3D, Tennis Clash, Zooba, Soccer Clash (~74k reviews, 13 idiomas)

## Deploy

```bash
databricks bundle validate -t dev -p fe-vm-wildlife-s2s
databricks bundle deploy   -t dev -p fe-vm-wildlife-s2s

# rodar componentes
databricks bundle run pf_setup             -t dev -p fe-vm-wildlife-s2s   # schema + tabelas
databricks bundle run pf_ingest_and_enrich -t dev -p fe-vm-wildlife-s2s   # extração + enriquecimento
databricks bundle run pf_weekly_report     -t dev -p fe-vm-wildlife-s2s   # relatório semanal
databricks bundle run pf_app               -t dev -p fe-vm-wildlife-s2s   # app
```

O **dashboard** é versionado em `src/dashboard/player_feedback.lvdash.json` (fonte de verdade,
referenciado por `resources/pf_dashboard.yml`). O gerador `scripts/build_dashboard.py` está defasado
e não deve ser usado para regenerar o JSON.

## Estrutura

```
player_feedback/
├── databricks.yml            # bundle + variáveis + target dev
├── resources/                # pf_jobs, pf_pipeline, pf_dashboard, pf_app
├── src/
│   ├── setup/                # 00_setup_schema.py
│   ├── jobs/                 # extract_reviews.py, weekly_report.py
│   ├── pipeline/             # enrich_reviews.py (SDP)
│   └── dashboard/            # player_feedback.lvdash.json
├── app/                      # FastAPI + React (Databricks App)
└── scripts/                  # build_dashboard.py (defasado — referência)
```

## Roadmap (v2)

- Coluna `translated_content` via `ai_translate` para análise cross-idioma consistente.
