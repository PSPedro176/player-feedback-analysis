# Deploy log — FE Bar Player Feedback (2026-11-04)

- Workspace: https://fevm-perdomo-demos.cloud.databricks.com (workspace id `7474652474621326`)
- Bundle: `febar_player_feedback`, target `dev` (`mode: development`), Databricks CLI v1.22.1, perfil `DEFAULT`
- Destino: `perdomo_demos_catalog.febar_player_feedback` · Lakebase Autoscaling project `febar-pf-games`
- Branch: `polly/febar-integration` = `origin/febar` (20335a4) + merge `polly/data-foundation` (3bd8030) + merge `polly/genie-agent` (7f88d7e) + as correções abaixo
- O deploy anterior do bundle `player_feedback` (app `player-feedback-analysis`, jobs `[dev pedro_perdomo] pf_*`, schema `player_feedback`) **não foi tocado**.
- Todos os horários estão em UTC.

## Recursos implantados

| Recurso | Nome | ID / URL |
|---|---|---|
| App | `febar-player-feedback` | https://febar-player-feedback-7474652474621326.aws.databricksapps.com (RUNNING, deployment `01f1d85cdea71fbbbf874c47ee245d47` SUCCEEDED; SP `c22b0dd8-1805-4dcc-af61-759f8091587b`) |
| SQL Warehouse | `[dev pedro_perdomo] pf_febar_warehouse` | `860f44e86926735a` |
| Dashboard | `[dev pedro_perdomo] Player Feedback Analysis` | `01f1d85bf7c31182b432ad8be51908b8` (publicado pelo pf_setup) |
| Pipeline SDP | `[dev pedro_perdomo] pf_febar_enrichment` | `86793067-7fa7-43da-9254-07bd4056e2fd` |
| Job | `pf_febar_setup` | `161339661441696` |
| Job | `pf_febar_ingest_and_enrich` | `393200720689535` |
| Job | `pf_febar_weekly_report` | `531289192588016` |
| Job | `pf_febar_genie_setup` | `859725293764059` |
| Job | `pf_febar_export_evidence` | `215832393233353` |
| Genie space | `Player Feedback — Genie` | `01f1d862100c1ba9a04bd2ea86919279` — https://fevm-perdomo-demos.cloud.databricks.com/genie/rooms/01f1d862100c1ba9a04bd2ea86919279 (SP do App com `CAN_RUN`) |

## Sequência executada

Todos os comandos `bundle` foram rodados com `--var backfill_max_per_game=1000`. Esse override limita a carga da demo a 1000 reviews por jogo/idioma (o default é 3000), para manter o custo de LLM baixo.

| # | Horário | Comando / ação | Resultado |
|---|---|---|---|
| 1 | antes de 14:28 | `git merge --no-ff origin/polly/data-foundation` e `origin/polly/genie-agent` | sem conflitos |
| 2 | antes de 14:28 | gates: `python3 -m py_compile app/**/*.py src/*.py`, `cd app/frontend && npm ci && npm run build`, `databricks bundle validate -t dev` | OK (o build gerou um `dist` idêntico ao versionado) |
| 3 | 14:28 | `databricks bundle deploy -t dev` | 9 recursos criados (35 s) |
| 4 | 14:28 | `databricks bundle run pf_setup -t dev` | run [494770918040839](https://fevm-perdomo-demos.cloud.databricks.com/jobs/161339661441696/runs/494770918040839) **SUCCESS** (2 min 36 s) |
| 5 | 14:31 | `databricks bundle run pf_app -t dev` | **falhou**: `Must specify environment variable source using either value or valueFrom` → correção 2 |
| 6 | ~14:36 | redeploy + `bundle run pf_app` | App **RUNNING** |
| 7 | ~14:40 | `POST /api/games` com Free Fire (`com.dts.freefireth`), Clash Royale (`com.supercell.clashroyale`) e Candy Crush Saga (`com.king.candycrushsaga`) | `{"added":3}`; o CDF replicou em `games_current` em menos de 45 s |
| 8 | 14:42 | `POST /api/jobs/collect/run` (fluxo de coleta do App) | run [898704961810297](https://fevm-perdomo-demos.cloud.databricks.com/jobs/393200720689535/runs/898704961810297): `extract` SUCCESS (9.000 reviews), `enrich` **FAILED** (`FIELD_NOT_FOUND`, ver correção 3). O pipeline falhou na análise, antes de qualquer chamada de LLM. |
| 9 | 14:59 | redeploy + `POST /api/jobs/collect/run` | run [737083062175851](https://fevm-perdomo-demos.cloud.databricks.com/jobs/393200720689535/runs/737083062175851) **SUCCESS** (11 min 20 s): extract 69 s (+14 reviews incrementais) · enrich 435 s (update de pipeline `f484fbe5-e6dc-4e8a-9229-513b403a56d7` COMPLETED) · refresh_governed_views 50 s · has_new_games = 3 · trigger_weekly_report 172 s |
| 10 | 15:08 | (disparado pela task `trigger_weekly_report`) | `pf_febar_weekly_report` run [897115454802566](https://fevm-perdomo-demos.cloud.databricks.com/jobs/531289192588016/runs/897115454802566) **SUCCESS** (2 min 51 s): 3 relatórios + logos |
| 11 | 15:11 | `databricks bundle run pf_genie_setup -t dev` | run [656270156433182](https://fevm-perdomo-demos.cloud.databricks.com/jobs/859725293764059/runs/656270156433182) **SUCCESS**: space criado e `CAN_RUN` concedido ao SP do App |
| 12 | ~15:13 | Genie, rodada 1: 9 perguntas via `/api/genie/ask` | 9/9 COMPLETED, todas conferidas com SQL direto → ajustes de instruções (ver `genie_conversations.md`) |
| 13 | 15:18 | redeploy + `bundle run pf_genie_setup` | run [219841343678515](https://fevm-perdomo-demos.cloud.databricks.com/jobs/859725293764059/runs/219841343678515) **SUCCESS**; rodada 2: 10/10 COMPLETED |
| 14 | 15:22 | redeploy + `bundle run pf_genie_setup` (instrução de privacidade) | run [1085601146256060](https://fevm-perdomo-demos.cloud.databricks.com/jobs/859725293764059/runs/1085601146256060) **SUCCESS**; rodada 3 da pergunta de listagem de reviews |
| 15 | 15:23 | `databricks bundle run pf_export_evidence -t dev` | run [997082702893834](https://fevm-perdomo-demos.cloud.databricks.com/jobs/215832393233353/runs/997082702893834) SUCCESS, mas exportou hashes de review_id → correção 5 |
| 16 | 15:25 | redeploy + `bundle run pf_export_evidence` | run [864111896672931](https://fevm-perdomo-demos.cloud.databricks.com/jobs/215832393233353/runs/864111896672931) SUCCESS, mas com `duration_ms` = 0 → correção 6 |
| 17 | 15:27 | redeploy + `bundle run pf_export_evidence` | run [788830310215180](https://fevm-perdomo-demos.cloud.databricks.com/jobs/215832393233353/runs/788830310215180) **SUCCESS** (51 s) → `/Volumes/perdomo_demos_catalog/febar_player_feedback/evidence/20261104T152706Z` |
| 18 | 15:28 | `databricks fs cp -r dbfs:/Volumes/perdomo_demos_catalog/febar_player_feedback/evidence/20261104T152706Z …` | copiado para [`docs/evidence/2026-11-04/`](2026-11-04/) |

As durações vêm de `run_duration` (ver `2026-11-04/job_run_history.csv`). As 6 tentativas falhas do pipeline (update `31f60da3…` e 5 `RETRY_ON_FAILURE` automáticos do modo dev) são todas do run 8.

## Contagens de linhas (após a execução)

Fonte: [`2026-11-04/row_counts.csv`](2026-11-04/row_counts.csv)

| Objeto | Linhas |
|---|---|
| `reviews_raw` | 9014 |
| `reviews_enrichment_inference` | 9014 |
| `reviews_enriched` | 9014 (Free Fire 3014, Clash Royale 3000, Candy Crush Saga 3000) |
| `ai_inference_log_enrichment` | 9014 (0 erros) |
| `ai_inference_log_reports` | 3 (0 erros) |
| `ai_inference_log` (view) | 9017 |
| `weekly_reports` | 3 (report_week 2026-11-02: Candy Crush green, Clash Royale yellow, Free Fire green) |
| `weekly_game_summary` (view) | 10 (jogo × semana ISO) |
| `lb_games_history` / `games_current` | 3 / 3 |

Expectations do SDP (`reviews_enriched`): `review_id_not_null`, `review_text_not_blank`, `score_between_1_and_5` e `valid_sentiment` passaram em 9014 de 9014 registros, com 0 descartados (`2026-11-04/pipeline_expectation_results.csv`).

## Problemas encontrados e correções (um commit cada)

1. **Revisão: o App vazava texto de exceção** (`app/server/routes/api.py`, `app/server/genie.py`). Os erros do SDK e do Genie agora vão só para o log do servidor; o cliente recebe uma mensagem genérica. A pergunta do Genie ficou limitada a `max_length=1000` (e `conversation_id` a 200): uma pergunta de 1001 caracteres retorna HTTP 422 (`app_api_samples/genie_ask_question_too_long.json`). O `pf_export_evidence` passou a receber `genie_setup_job_id: ${resources.jobs.pf_genie_setup.id}`. Removido o `development: true` depreciado do pipeline (o `mode: development` já cobre isso).
2. **`bundle run pf_app` rejeitado pela API de Apps.** Na CLI 1.22, `${resources.dashboards.pf_dashboard.dashboard_id}` era resolvido como vazio na config do App, então a env `DASHBOARD_ID` ia sem valor. A correção foi usar `${resources.dashboards.pf_dashboard.id}` (mesmo ID). Trocar `value_from` por `valueFrom` não funciona: a CLI ignora a chave.
3. **Pipeline falhava com `FIELD_NOT_FOUND: No such struct field response in result, errorMessage`.** `ai_query(..., failOnError => false)` retorna `struct<result, errorMessage>`; o pipeline (`src/enrich_reviews.py`) e o relatório semanal (`src/weekly_report.py`) liam `.response`. Corrigido para `.result` depois de confirmar o tipo no warehouse.
4. **Qualidade do Genie** (`src/genie/player_feedback.geniespace.json`), em dois commits:
   - tirar `opinion` dos rankings de temas, arredondar `avg_score` e avisar quando o volume é baixo;
   - nunca selecionar `user_name`/`review_id`.

   Detalhes em `genie_conversations.md`.
5. **O export de evidências gravava `sha2(review_id)` e `sha2(record_key)`.** São identificadores pseudônimos por review e não são necessários; foram removidos de `src/export_evidence.py`.
6. **O export gravava `duration_ms = 0`.** `execution_duration` é 0 em jobs multi-task; agora usa `run_duration`, com fallback para `end_time - start_time`.

## Autenticação no App (limitação desta execução)

- O perfil CLI `DEFAULT` usa **PAT**: `databricks auth token` falha com `OAuth is not configured for this host`, e o proxy do Databricks Apps recusa PAT (HTTP 401, mesmo para `/api/health`). Não foi possível chamar as APIs da URL implantada de forma programática, nem ler `databricks apps logs`, que também exige OAuth.
- Criar um service principal de teste com segredo OAuth contornaria isso, mas essa ação não foi autorizada para esta tarefa e **não foi feita**.
- Para exercitar o fluxo do App, o **mesmo código** (`app/`, idêntico ao deployment ativo `01f1d85cdea71fbbbf874c47ee245d47`) rodou localmente (`uvicorn app:app --port 8765`) com a mesma configuração do bundle (warehouse, job, Lakebase `febar-pf-games`, catálogo/schema e título do Genie space), autenticado como o usuário via perfil `DEFAULT`. Assim:
  - o cadastro de jogos usou o caminho real do App: `POST /api/games` → `lakebase.add_games` → Postgres `public.games` → CDF → `games_current`;
  - a coleta usou `POST /api/jobs/collect/run`, que espera o CDF e faz `jobs.run_now` no job implantado;
  - o chat usou `/api/genie/*` sobre o space implantado.
- Diferença em relação à URL implantada: as chamadas rodaram com a identidade do **usuário**, não a do SP do App. As permissões do SP foram verificadas à parte:
  - `CAN_RUN` no Genie space (via `permissions get genie`);
  - grants de UC aplicados pelo `pf_setup` e pela task `refresh_governed_views`;
  - bindings do App para warehouse, job e endpoint de modelo.
- Para validar a URL implantada, basta abrir https://febar-player-feedback-7474652474621326.aws.databricksapps.com no navegador (login SSO) e usar a aba do Genie.

## Observações sobre os dados

- O teto de 1000 reviews por idioma corta o backfill de jogos com muito volume. Free Fire cobre só cerca de 1 a 3 de novembro, o que dá apenas 172 reviews na semana ISO passada, contra 1.612 a 1.942 dos outros jogos. As taxas de Free Fire nessa semana são menos confiáveis, e o Genie passou a avisar isso.
- O `at` mais recente coletado é 2026-11-03 14:42 UTC (por volta de 24 h antes da execução), em todos os jogos e idiomas.
