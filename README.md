# Player Feedback Analysis

Análise de reviews de jogos mobile da Google Play Store via Databricks. Coleta, enriquecimento com **AI Functions**, geração de relatórios semanais e visualização via **AI/BI Dashboard** (com Genie integrado) e **Databricks App** (FastAPI + React).

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
- **App** (`app/`) — FastAPI + React/Vite/Tailwind; design minimalista, KPIs ao vivo, relatórios por jogo, dashboard AI/BI embeddado.

## Ambiente

- Workspace: `TODO-preencher-com-seu-workspace`
- Catálogo / schema: `player_feedback_catalog.player_feedback`
- SQL Warehouse serverless: `TODO-preencher-com-seu-warehouse-id`
- Modelo: `databricks-meta-llama-3-3-70b-instruct`
- Jogos monitorados: configure no `databricks.yml` (veja "Como usar" abaixo)

## Como usar

### 1. Pré-requisitos

- Databricks workspace (AWS / Azure / GCP)
- SQL Warehouse (serverless ou provisioned)
- CLI Databricks configurada com um profile (veja [Databricks CLI Setup](https://docs.databricks.com/en/dev-tools/cli/))
- Python 3.11+, npm/node (para a app frontend)

### 2. Configurar o projeto

1. Clone este repositório:
   ```bash
   git clone https://github.com/PSPedro176/player-feedback-analysis.git
   cd player-feedback-analysis
   ```

2. Edite `databricks.yml` e substitua os placeholders:
   - `TODO-preencher-com-seu-workspace` → seu workspace host (ex: `https://adb-1234567890.azuredatabricks.net`)
   - `TODO-preencher-com-seu-email@empresa.com` → seu email Databricks
   - `TODO-preencher-com-seu-warehouse-id` → warehouse ID (serverless ou provisioned)
   - `TODO-preencher-com-seu-profile-cli` → seu profile da CLI Databricks (ex: `DEFAULT`)
   - `player_feedback_catalog` → catálogo existente no seu workspace (ou `main` se quiser usar o catálogo padrão)
   - **Jogos monitorados**: edite a variável `games` com seus jogos. Exemplo:
     ```yaml
     games:
       description: Mapa jogo→package name (JSON)
       default: '{"Meu Jogo": "com.example.mygame", "Outro Jogo": "com.example.other"}'
     ```
     Os package names devem ser IDs válidos da Play Store (testados com `google-play-scraper`).

3. Atualize `app/app.yaml` com os mesmos valores:
   - `SQL_WAREHOUSE_ID`
   - `DASHBOARD_ID` (você preencherá após deploy do dashboard)
   - `GENIE_SPACE_ID` (você preencherá após criar um Genie space)
   - `CATALOG` e `SCHEMA`

### 3. Deploy e execução

```bash
# Buildar o frontend da app (OBRIGATÓRIO antes do deploy).
# O Databricks App serve o build estático de app/frontend/dist, e o
# `bundle deploy` só envia esse diretório se ele existir localmente.
cd app/frontend && npm install && npm run build && cd ../..

# Apontar o dashboard AI/BI para o SEU catálogo/schema (OBRIGATÓRIO antes do
# deploy). O JSON do dashboard usa os placeholders __CATALOG__ e __SCHEMA__ nas
# 12 queries; substitua-os pelos mesmos valores de `catalog`/`schema` do
# databricks.yml (senão os widgets da aba AI/BI falham com TABLE_OR_VIEW_NOT_FOUND).
sed -i '' 's/__CATALOG__/SEU_CATALOGO/g; s/__SCHEMA__/SEU_SCHEMA/g' src/dashboard/player_feedback.lvdash.json
# (Linux: use `sed -i` sem as aspas vazias.)

# Validar o bundle
databricks bundle validate -t dev -p <seu-profile>

# Deploy dos componentes
databricks bundle deploy -t dev -p <seu-profile>

# Rodar setup (cria schema + tabelas)
databricks bundle run pf_setup -t dev -p <seu-profile>

# Rodar extração + enriquecimento (primeira execução pode levar alguns minutos)
databricks bundle run pf_ingest_and_enrich -t dev -p <seu-profile>

# Gerar relatório semanal
databricks bundle run pf_weekly_report -t dev -p <seu-profile>

# Deploy da app
databricks bundle run pf_app -t dev -p <seu-profile>
```

4. Após deploy:
   - Copie o `dashboard_id` do dashboard criado (`src/dashboard/player_feedback.lvdash.json`) e preencha `DASHBOARD_ID` em `app/app.yaml`
   - Se usar Genie, copie o `genie_space_id` e preencha em `app/app.yaml`

## Deploy

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
