# Conversas com o Genie — evidências (2026-11-04)

Space: `Player Feedback — Genie` (`01f1d862100c1ba9a04bd2ea86919279`) — https://fevm-perdomo-demos.cloud.databricks.com/genie/rooms/01f1d862100c1ba9a04bd2ea86919279

Todas as perguntas foram feitas pelo endpoint do App `POST /api/genie/ask` + polling `GET /api/genie/conversations/{c}/messages/{m}` (mesmo código do App implantado, executado localmente com o perfil CLI do usuário — ver `deploy_log.md`, seção *Autenticação no App*). `current_date()` no warehouse = 2026-11-04, logo "semana passada" = semana ISO 2026-10-26 a 2026-11-01.

Cada resposta foi conferida com uma consulta SQL independente (escrita à mão, lendo direto de `reviews_enriched` / `weekly_reports` / tabelas de log, sem reutilizar a view que o Genie usou).

## Ajustes feitos no Genie space durante o teste

| Rodada | Problema observado | Mudança em `src/genie/player_feedback.geniespace.json` |
|---|---|---|
| 1 → 2 | "Temas mais citados nos negativos" ranqueava o rótulo genérico `opinion` em 1º para todos os jogos (resposta pouco útil). | Instrução *Temas / Topics*: não incluir `opinion` em rankings de temas; SQL confiável do tema sem `opinion`. |
| 1 → 2 | `avg_score` vinha sem arredondamento (3.576725…). | Instrução: `round(avg_score, 2)`. |
| 1 → 2 | Free Fire tinha só 172 reviews na semana passada (teto de backfill da demo) e era comparado sem ressalva. | Instrução: avisar volume baixo (< 300 reviews no período). |
| 2 → 3 | "Mostre os 10 reviews mais recentes com bug report" selecionava `user_name` e `review_id`. | Instrução de privacidade: nunca selecionar `user_name`/`review_id`; texto truncado em 300 caracteres. |

Após cada mudança: `databricks bundle deploy` + `databricks bundle run pf_genie_setup` (runs 219841343678515 e 1085601146256060) e nova rodada de perguntas.

## Resultado final (rodada 2; pergunta 8 = rodada 3)

### 1. Quais jogos tiveram mais bug reports na semana passada?
- Status: `COMPLETED` em 17.7 s · linhas: 3
- **Conferência vs SQL direto: CORRETO** — SQL direto: Clash Royale 186/1942 (9,6%), Candy Crush Saga 88/1612 (5,5%), Free Fire 22/172 (12,8%) — idêntico. Na rodada 2 o Genie passou a ressalvar o volume baixo de Free Fire.

**SQL gerado pelo Genie**

```sql
WITH ranked_games AS (
  SELECT
    `game`,
    `week_start`,
    `n_bug_reports`,
    `n_reviews`,
    ROUND(`bug_report_rate` * 100, 1) AS `bug_report_pct`,
    RANK() OVER (ORDER BY `n_bug_reports` DESC) AS `bug_report_rank`
  FROM `perdomo_demos_catalog`.`febar_player_feedback`.`weekly_game_summary`
  WHERE `week_start` = date_sub(CAST(date_trunc('WEEK', current_date()) AS DATE), 7)
    AND `game` IS NOT NULL
)
SELECT
  `game`,
  `week_start`,
  `n_bug_reports`,
  `n_reviews`,
  `bug_report_pct`
FROM ranked_games
ORDER BY `bug_report_rank`, `game`
```

**Resultado (top 10)**

| game | week_start | n_bug_reports | n_reviews | bug_report_pct |
|---|---|---|---|---|
| Clash Royale | 2026-10-26 | 186 | 1942 | 9.6 |
| Candy Crush Saga | 2026-10-26 | 88 | 1612 | 5.5 |
| Free Fire | 2026-10-26 | 22 | 172 | 12.8 |

**Resposta do Genie**

> Na semana passada (início em **2026-10-26**), os jogos com mais bug reports foram:
> - **Clash Royale** — **186** bug reports em **1.942** reviews (**9,6%**)
> - **Candy Crush Saga** — **88** bug reports em **1.612** reviews (**5,5%**)
> - **Free Fire** — **22** bug reports em **172** reviews (**12,8%**)
> Entre os 3 jogos retornados, **Clash Royale** lidera em volume absoluto de bug reports, enquanto **Free Fire** tem a maior taxa proporcional, mas com volume baixo de reviews, o que torna a comparação menos confiável.

**SQL de conferência**

```sql
SELECT game, count_if(bug_report) bugs, count(*) n, round(100*count_if(bug_report)/count(*),1) pct
FROM reviews_enriched WHERE at >= '2026-10-26' AND at < '2026-11-02'
GROUP BY game ORDER BY bugs DESC
```

### 2. Como evoluiu o sentimento negativo de cada jogo nas últimas 4 semanas?
- Status: `COMPLETED` em 17.5 s · linhas: 7
- **Conferência vs SQL direto: CORRETO** — 7 linhas (jogo × semana) idênticas: ex. Clash Royale 210/591 (35,5%) → 650/1942 (33,5%); Candy Crush 26/218, 23/246, 38/533, 191/1612. Jogos sem reviews em semanas antigas (teto de backfill) simplesmente não aparecem.

**SQL gerado pelo Genie**

```sql
SELECT
  `game`,
  `week_start`,
  `n_negative`,
  `n_reviews`,
  round(`negative_rate` * 100, 1) AS `negative_pct`
FROM `perdomo_demos_catalog`.`febar_player_feedback`.`weekly_game_summary`
WHERE `week_start` IS NOT NULL
  AND `game` IS NOT NULL
  AND `week_start` >= date_sub(CAST(date_trunc('WEEK', current_date()) AS DATE), 28)
  AND `week_start` < CAST(date_trunc('WEEK', current_date()) AS DATE)
ORDER BY `game`, `week_start`
```

**Resultado (top 10)**

| game | week_start | n_negative | n_reviews | negative_pct |
|---|---|---|---|---|
| Candy Crush Saga | 2026-10-05 | 26 | 218 | 11.9 |
| Candy Crush Saga | 2026-10-12 | 23 | 246 | 9.3 |
| Candy Crush Saga | 2026-10-19 | 38 | 533 | 7.1 |
| Candy Crush Saga | 2026-10-26 | 191 | 1612 | 11.8 |
| Clash Royale | 2026-10-19 | 210 | 591 | 35.5 |
| Clash Royale | 2026-10-26 | 650 | 1942 | 33.5 |
| Free Fire | 2026-10-26 | 38 | 172 | 22.1 |

**Resposta do Genie**

> Nas últimas 4 semanas completas, o sentimento negativo variou por jogo nos **7 registros retornados**: **Candy Crush Saga** caiu de **11,9%** (2026-10-05) para **9,3%** e **7,1%**, mas voltou a **11,8%** em 2026-10-26; **Clash Royale** recuou levemente de **35,5%** para **33,5%** entre 2026-10-19 e 2026-10-26; **Free Fire** aparece apenas em 2026-10-26 com **22,1%**. Como insight, entre os dados exibidos o **Clash Royale** teve as maiores taxas negativas, enquanto o **Candy Crush Saga** mostrou oscilação com pico recente de volume (**1.612 reviews** na última semana mostrada).

**SQL de conferência**

```sql
SELECT game, CAST(date_trunc('WEEK', at) AS DATE) wk, count_if(lower(sentiment)='negative') neg, count(*) n
FROM reviews_enriched WHERE at >= '2026-10-05' AND at < '2026-11-02'
GROUP BY ALL ORDER BY 1, 2
```

### 3. Qual a nota do último relatório semanal de cada jogo?
- Status: `COMPLETED` em 17.6 s · linhas: 3
- **Conferência vs SQL direto: CORRETO** — weekly_reports: Candy Crush green 4,39 (1574), Clash Royale yellow 3,59 (1889), Free Fire green 4,34 (3014), report_week 2026-11-02 — idêntico.

**SQL gerado pelo Genie**

```sql
SELECT
  `game`,
  `report_week`,
  `grade`,
  round(`avg_score`, 2) AS `avg_score`,
  `n_reviews`,
  round(`bug_report_rate` * 100, 1) AS `bug_report_pct`,
  round(`negative_rate` * 100, 1) AS `negative_pct`
FROM `perdomo_demos_catalog`.`febar_player_feedback`.`weekly_reports`
QUALIFY row_number() OVER (PARTITION BY `game` ORDER BY `report_week` DESC) = 1
ORDER BY `game`
```

**Resultado (top 10)**

| game | report_week | grade | avg_score | n_reviews | bug_report_pct | negative_pct |
|---|---|---|---|---|---|---|
| Candy Crush Saga | 2026-11-02 | green | 4.39 | 1574 | 6.0 | 12.0 |
| Clash Royale | 2026-11-02 | yellow | 3.59 | 1889 | 10.1 | 33.4 |
| Free Fire | 2026-11-02 | green | 4.34 | 3014 | 6.8 | 14.7 |

**Resposta do Genie**

> A nota do último relatório semanal está em **2026-11-02** para os 3 jogos, com **Candy Crush Saga: green**, **Clash Royale: yellow** e **Free Fire: green**.
> 
> Como contexto do relatório, **Clash Royale** é o único em atenção e também tem a menor nota média (**3,59**) e a maior taxa de avaliações negativas (**33,4%**), enquanto os outros dois ficaram em **green**.

**SQL de conferência**

```sql
SELECT game, report_week, grade, round(avg_score,2), n_reviews FROM weekly_reports ORDER BY game
```

### 4. Qual a taxa de erro das chamadas de IA por modelo?
- Status: `COMPLETED` em 13.3 s · linhas: 2
- **Conferência vs SQL direto: CORRETO** — Tabelas de origem: ai_inference_log_enrichment 9014 chamadas / 0 erros; ai_inference_log_reports 3 / 0 — idêntico (0,00%).

**SQL gerado pelo Genie**

```sql
SELECT
  `model`,
  `source`,
  COUNT(*) AS `n_calls`,
  COUNT_IF(`error_message` IS NOT NULL) AS `n_errors`,
  ROUND(try_divide(100.0 * COUNT_IF(`error_message` IS NOT NULL),COUNT(*)), 2) AS `error_pct`
FROM `perdomo_demos_catalog`.`febar_player_feedback`.`ai_inference_log`
WHERE `model` IS NOT NULL
  AND `source` IS NOT NULL
GROUP BY `model`, `source`
ORDER BY `error_pct` DESC
```

**Resultado (top 10)**

| model | source | n_calls | n_errors | error_pct |
|---|---|---|---|---|
| databricks-meta-llama-3-3-70b-instruct | enrichment | 9014 | 0 | 0.00 |
| databricks-meta-llama-3-3-70b-instruct | weekly_report | 3 | 0 | 0.00 |

**Resposta do Genie**

> A taxa de erro das chamadas de IA é **0,0%** para o modelo **databricks-meta-llama-3-3-70b-instruct** nas duas etapas observadas. Foram **0 erros em 9.014 chamadas** de **enrichment** e **0 erros em 3 chamadas** de **weekly_report**; em ambos os casos, não houve falhas registradas.

**SQL de conferência**

```sql
SELECT 'enrichment' s, count(*), count(error_message) FROM ai_inference_log_enrichment
UNION ALL SELECT 'weekly_report', count(*), count(error_message) FROM ai_inference_log_reports
```

### 5. Qual a distribuição de sentimento por jogo?
- Status: `COMPLETED` em 17.6 s · linhas: 12
- **Conferência vs SQL direto: CORRETO** — 12 linhas idênticas (ex. Candy Crush positive 2238 = 74,6%; Clash Royale negative 1028 = 34,3%; Free Fire positive 1840).

**SQL gerado pelo Genie**

```sql
SELECT
  `game`,
  lower(`sentiment`) AS `sentiment`,
  count(*) AS `n_reviews`,
  round(try_divide(100.0 * count(*),sum(count(*)) OVER (PARTITION BY `game`)), 1) AS `pct`
FROM `perdomo_demos_catalog`.`febar_player_feedback`.`reviews_enriched`
WHERE `sentiment` IS NOT NULL
  AND `game` IS NOT NULL
GROUP BY `game`, lower(`sentiment`)
ORDER BY `game`, `n_reviews` DESC
```

**Resultado (top 10)**

| game | sentiment | n_reviews | pct |
|---|---|---|---|
| Candy Crush Saga | positive | 2238 | 74.6 |
| Candy Crush Saga | negative | 324 | 10.8 |
| Candy Crush Saga | neutral | 293 | 9.8 |
| Candy Crush Saga | mixed | 145 | 4.8 |
| Clash Royale | positive | 1329 | 44.3 |
| Clash Royale | negative | 1028 | 34.3 |
| Clash Royale | mixed | 354 | 11.8 |
| Clash Royale | neutral | 289 | 9.6 |
| Free Fire | positive | 1840 | 61.0 |
| Free Fire | neutral | 471 | 15.6 |

**Resposta do Genie**

> A distribuição de sentimento varia entre **3 jogos** e, em todos eles, o sentimento **positivo** é o mais frequente. Exemplos incluem:
> - **Candy Crush Saga**: **74,6% positivo** (2.238 reviews), **10,8% negativo** (324), **9,8% neutro** (293) e **4,8% misto** (145)
> - **Clash Royale**: **44,3% positivo** (1.329 reviews), **34,3% negativo** (1.028), **11,8% misto** (354) e **9,6% neutro** (289)
> - **Free Fire**: **61,0% positivo** (1.840 reviews), **15,6% neutro** (471), **14,7% negativo** (443) e **8,6% misto** (260)
> 
> Entre os jogos mostrados, **Candy Crush Saga** tem a maior fatia de avaliações positivas, enquanto **Clash Royale** concentra a maior proporção de avaliações negativas.

**SQL de conferência**

```sql
SELECT game, sentiment, count(*) FROM reviews_enriched GROUP BY ALL ORDER BY 1, 3 DESC
```

### 6. Qual jogo teve a maior taxa de toxicidade na semana passada?
- Status: `COMPLETED` em 22.0 s · linhas: 1
- **Conferência vs SQL direto: CORRETO** — SQL direto: Clash Royale 304/1942 = 15,7% (Free Fire 10,5%, Candy Crush 3,1%).

**SQL gerado pelo Genie**

```sql
WITH ranked_games AS (
  SELECT
    `game`,
    `week_start`,
    `toxicity_rate`,
    `n_reviews`,
    `n_toxicity`,
    RANK() OVER (ORDER BY `toxicity_rate` DESC) AS `toxicity_rank`
  FROM `perdomo_demos_catalog`.`febar_player_feedback`.`weekly_game_summary`
  WHERE `week_start` = date_sub(CAST(date_trunc('WEEK', current_date()) AS DATE), 7)
    AND `game` IS NOT NULL
    AND `toxicity_rate` IS NOT NULL
)
SELECT
  `game`,
  `week_start`,
  `n_toxicity`,
  `n_reviews`,
  round(`toxicity_rate` * 100, 1) AS `toxicity_pct`
FROM ranked_games
WHERE `toxicity_rank` = 1
ORDER BY `game`
```

**Resultado (top 10)**

| game | week_start | n_toxicity | n_reviews | toxicity_pct |
|---|---|---|---|---|
| Clash Royale | 2026-10-26 | 304 | 1942 | 15.7 |

**Resposta do Genie**

> Na semana passada, o jogo com a maior taxa de toxicidade foi **Clash Royale**, com **15,7%** de reviews tóxicos na semana de **2026-10-26**. Em **Clash Royale**, isso correspondeu a **304** reviews tóxicos entre **1.942** reviews no total.

**SQL de conferência**

```sql
SELECT game, count_if(toxicity) t, count(*) n, round(100*count_if(toxicity)/count(*),1) pct
FROM reviews_enriched WHERE at >= '2026-10-26' AND at < '2026-11-02'
GROUP BY game ORDER BY pct DESC
```

### 7. Quais são os temas mais citados nos reviews negativos de cada jogo?
- Status: `COMPLETED` em 17.5 s · linhas: 18
- **Conferência vs SQL direto: CORRETO** — Contagens idênticas: Candy Crush bug_report 120 > pricing 104; Clash Royale game_balance 555 > pricing 278; Free Fire toxicity 151 > bug_report 148.

**SQL gerado pelo Genie**

```sql
SELECT `game`, `topic`, `n_reviews`
FROM (
  SELECT
    `game`,
    count_if(`bug_report`) AS `bug_report`,
    count_if(`pricing`) AS `pricing`,
    count_if(`game_balance`) AS `game_balance`,
    count_if(`community`) AS `community`,
    count_if(`toxicity`) AS `toxicity`,
    count_if(`visuals`) AS `visuals`
  FROM `perdomo_demos_catalog`.`febar_player_feedback`.`reviews_enriched`
  WHERE `game` IS NOT NULL
    AND `sentiment` IS NOT NULL
    AND lower(`sentiment`) = 'negative'
  GROUP BY `game`
)
UNPIVOT (`n_reviews` FOR `topic` IN (`bug_report`, `pricing`, `game_balance`, `community`, `toxicity`, `visuals`))
WHERE `topic` IS NOT NULL
ORDER BY `game`, `n_reviews` DESC
```

**Resultado (top 10)**

| game | topic | n_reviews |
|---|---|---|
| Candy Crush Saga | bug_report | 120 |
| Candy Crush Saga | pricing | 104 |
| Candy Crush Saga | game_balance | 78 |
| Candy Crush Saga | toxicity | 74 |
| Candy Crush Saga | visuals | 12 |
| Candy Crush Saga | community | 5 |
| Clash Royale | game_balance | 555 |
| Clash Royale | toxicity | 419 |
| Clash Royale | pricing | 278 |
| Clash Royale | bug_report | 245 |

**Resposta do Genie**

> Nos reviews com sentimento **negativo**, o tema mais citado é **bug_report** em **Candy Crush Saga** (**120**), **game_balance** em **Clash Royale** (**555**) e **toxicity** em **Free Fire** (**151**). Como insight, **visuals** é o tema menos citado nos três jogos, variando de **8** a **14** menções.

**SQL de conferência**

```sql
SELECT game, count_if(bug_report) bug, count_if(pricing) pricing, count_if(game_balance) balance,
       count_if(opinion) opinion, count_if(community) community, count_if(toxicity) tox, count_if(visuals) visuals
FROM reviews_enriched WHERE sentiment = 'negative' GROUP BY game ORDER BY game
```

_Rodada 1:_ na rodada 1 o SQL incluía `opinion`, que aparecia em 1º para todos os jogos (Clash Royale 673, Free Fire 275, Candy Crush 229) — números corretos, mas resposta pouco informativa; motivou o ajuste de instruções.

### 8. Mostre os 10 reviews mais recentes com bug report
- Status: `COMPLETED` em 22.2 s · linhas: 10
- **Conferência vs SQL direto: CORRETO (linhas) / texto com contagem imprecisa** — As 10 linhas batem com o SQL direto (mesma ordem jogo/idioma). O resumo em texto do Genie diz 'Free Fire e Clash Royale com 3 cada, Candy Crush com 3' e 'es e pt com 4 cada', mas o correto é Free Fire 4, Candy Crush 3, Clash Royale 3 e es 5, pt 4, en 1 — limitação do resumo em linguagem natural, não da consulta. Após o ajuste de privacidade, o SQL não seleciona mais user_name/review_id.

**SQL gerado pelo Genie**

```sql
SELECT
  `game`,
  `language`,
  `score`,
  `sentiment`,
  `at`,
  substring(`content`, 1, 300) AS `content`
FROM `perdomo_demos_catalog`.`febar_player_feedback`.`reviews_enriched`
WHERE `bug_report` = true
  AND `at` IS NOT NULL
ORDER BY `at` DESC
LIMIT 10
```

**Resultado (top 10)**

| game | language | score | sentiment | at | content |
|---|---|---|---|---|---|
| Free Fire | pt | 5 | mixed | 2026-11-03T14:42:50.000Z | jogo muito bom mais não tá rodando muito bem no redmi 9 |
| Free Fire | es | 1 | negative | 2026-11-03T14:32:06.000Z | El juego no me enlaza con la cuenta ni nada a todo el mundo le pasa esto gue me pasa a mi o es a My solo |
| Candy Crush Saga | pt | 1 | mixed | 2026-11-03T14:22:38.000Z | gosto imenso do jogo mas consta com uma infinitude de bugs que não dá para ignorar e depois de fazer uma compra no jogo para não perder o curso, o jogo trava mais uma vez e até parece de propósito. |
| Candy Crush Saga | pt | 5 | mixed | 2026-11-03T14:21:26.000Z | Agora ta muito top eu amo esse jogo ❤❤❤❤❤❤❤❤😍 observação tá travando muito |
| Clash Royale | es | 1 | negative | 2026-11-03T14:20:40.000Z | Es una completa BASURA este juego, cada que me meto a jugar tocan solo jugadores que usan MK y bruja, literalmente 16 rivales seguidos con MK y bruja, no hay otro mazo en el meta q no sea ese, una partida tras otra mk Evo y bruja Evo, protegen a su bruja con MK Evo, ya aburre, y lo peor es q no soy  |
| Free Fire | es | 5 | mixed | 2026-11-03T14:13:27.000Z | muy lindo pero quisiera que agregaran diamantes gratis a todos pero la verdad muy lindo EXELENTE ya no se cuando pongo para descargar,anda muy lento |
| Candy Crush Saga | en | 2 | negative | 2026-11-03T14:06:10.000Z | The final level of this game has been lost due to a phone reset. Even after logging in via Gmail, the last level is not being restored—despite the fact that payments have been made through Google Pay on several occasions. The developers should provide an option to restore the game to the correct lev |
| Clash Royale | pt | 2 | negative | 2026-11-03T13:59:29.000Z | The matchmaking at clan wars is completely broke. There's no chance. The game always put me against level 16 guys with level 16 troops (im level 14). Besides that, there are a lot of connection problems, even with stable wifi conexion |
| Free Fire | es | 5 | negative | 2026-11-03T13:57:34.000Z | Garena hace 9 años llevas desarrollando el juego pero todavía entran hackers que vuelan y quedan invisibles son imposibles de matar |
| Clash Royale | es | 1 | negative | 2026-11-03T13:40:40.000Z | juego desbalanceado, bugs, agradezcan que le di una estrella porque no me deja darle menos |

**Resposta do Genie**

> Aqui estão os **10 reviews mais recentes** marcados como bug report, todos de **2026-11-03**. Há maior presença de **Free Fire** e **Clash Royale** com **3 reviews cada**, enquanto **Candy Crush Saga** aparece com **3** e os idiomas mais frequentes são **es** e **pt** com **4 reviews cada**.

**SQL de conferência**

```sql
SELECT game, language FROM reviews_enriched WHERE bug_report ORDER BY at DESC LIMIT 10
```

### 9. Which game had the lowest average score last week?
- Status: `COMPLETED` em 21.6 s · linhas: 1
- **Conferência vs SQL direto: CORRETO** — SQL direto: Clash Royale 3,577 (1942 reviews) < Free Fire 4,012 (172) < Candy Crush 4,444 (1612). Arredondado para 3.58 na rodada 2.

**SQL gerado pelo Genie**

```sql
WITH ranked_games AS (
  SELECT
    `game`,
    `week_start`,
    ROUND(`avg_score`, 2) AS `avg_score`,
    `n_reviews`,
    RANK() OVER (ORDER BY `avg_score` ASC) AS `score_rank`
  FROM `perdomo_demos_catalog`.`febar_player_feedback`.`weekly_game_summary`
  WHERE `week_start` = date_sub(CAST(date_trunc('WEEK', current_date()) AS DATE), 7)
    AND `game` IS NOT NULL
    AND `avg_score` IS NOT NULL
)
SELECT
  `game`,
  `week_start`,
  `avg_score`,
  `n_reviews`
FROM ranked_games
WHERE `score_rank` = 1
ORDER BY `game`
```

**Resultado (top 10)**

| game | week_start | avg_score | n_reviews |
|---|---|---|---|
| Clash Royale | 2026-10-26 | 3.58 | 1942 |

**Resposta do Genie**

> Last week, **Clash Royale** had the lowest average score, with an average rating of **3.58** for the week starting **2026-10-26**, based on **1,942 reviews**.

**SQL de conferência**

```sql
SELECT game, round(avg(score),3) a, count(*) FROM reviews_enriched
WHERE at >= '2026-10-26' AND at < '2026-11-02' GROUP BY game ORDER BY a
```

_Rodada 1:_ na rodada 1 o valor vinha sem arredondamento (3.576725025746653).

### 10. Quais jogos estão sendo monitorados atualmente?
- Status: `COMPLETED` em 17.8 s · linhas: 3
- **Conferência vs SQL direto: CORRETO** — games_current: 3 jogos ativos (Candy Crush Saga, Clash Royale, Free Fire).

**SQL gerado pelo Genie**

```sql
SELECT DISTINCT
  `game`
FROM `perdomo_demos_catalog`.`febar_player_feedback`.`games_current`
WHERE `active` = true
  AND `game` IS NOT NULL
ORDER BY `game` ASC
```

**Resultado (top 10)**

| game |
|---|
| Candy Crush Saga |
| Clash Royale |
| Free Fire |

**Resposta do Genie**

> Atualmente, **3 jogos** estão sendo monitorados: **Candy Crush Saga**, **Clash Royale** e **Free Fire**. A lista exibida está em ordem alfabética e, nos dados retornados, todos os jogos ativos têm nome preenchido.

**SQL de conferência**

```sql
SELECT game, package_name FROM games_current WHERE active
```
