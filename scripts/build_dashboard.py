#!/usr/bin/env python3
"""Gera o serialized_dashboard do AI/BI de Player Feedback e cria/atualiza via API.

⚠️ DEFASADO — NÃO USE PARA SOBRESCREVER O DASHBOARD.
A versão final do dashboard foi editada diretamente no workspace e é a fonte de
verdade em src/dashboard/player_feedback.lvdash.json (puxada via API). Este script
gera uma versão ANTIGA; rodar --write/--deploy REGRIDE o dashboard. Mantido só
como referência histórica dos helpers/aprendizados do Lakeview JSON.
"""
_LEGACY = """Doc original abaixo:

Uso:
    python3 scripts/build_dashboard.py            # imprime o JSON (valida)
    python3 scripts/build_dashboard.py --deploy   # cria/atualiza no workspace
    python3 scripts/build_dashboard.py --write PATH  # grava o .lvdash.json

FILOSOFIA (monitor de desempenho de jogos, mentalidade lead DS):
- Objetivo = acompanhar DESEMPENHO INDIVIDUAL de cada jogo ao longo do tempo.
- TENDÊNCIA é sinal; número bruto é ruído (sempre há gente elogiando/reclamando
  nos grandes números). Todos os gráficos temporais usam TAXAS móveis 7d, não
  contagens absolutas.
- Big numbers existem como contexto rápido, sempre com Δ vs. período anterior
  (o delta é o que dá significado ao número).
- Filtros GLOBAIS (nível dashboard): Jogo, Idioma, Período.

Bugs conhecidos do Lakeview JSON tratados aqui:
- query DEVE ter "name": "main_query" (senão "Select fields to visualize").
- counter com agregação complexa falha: PRÉ-AGREGAR em dataset e referenciar
  a coluna crua com disaggregated=True.
"""
import argparse
import json
import subprocess
import uuid

PROFILE = "fe-vm-wildlife-s2s"
WAREHOUSE_ID = "ae8786c45629ac32"
PARENT_PATH = "/Users/pedro.perdomo@databricks.com"
NAME = "Wildlife — Player Feedback Analysis"
CATALOG = "wildlife_s2s_catalog"
SCHEMA = "player_feedback"
ENRICHED = f"{CATALOG}.{SCHEMA}.reviews_enriched"

# Temas (coluna boolean -> rótulo). Ordenados por relevância de negócio.
THEMES = {
    "bug_report": "Bugs",
    "pricing": "Preços",
    "game_balance": "Balanceamento",
    "toxicity": "Toxicidade",
    "community": "Comunidade",
    "visuals": "Visual",
}

# Paleta oficial Databricks para AI/BI. Laranja Databricks (#FF3621) primário.
# Sem pretos/cinzas editoriais — só as cores padrão da plataforma.
DBX = ["#FF3621", "#FFAB00", "#00A972", "#2272B4", "#8BCAE7",
       "#AB4057", "#99DDB4", "#FCA4A1", "#919191", "#BF7080"]
PRIMARY = "#FF3621"
# Séries de tema (6 temas) — cores distintas da paleta Databricks.
SERIES = ["#FF3621", "#FFAB00", "#00A972", "#2272B4", "#AB4057", "#8BCAE7"]
# Sentimento -> cor fixa: positive=verde, neutral=azul, mixed=amarelo, negative=vermelho.
SENTIMENT_MAP = [
    {"value": "positive", "color": "#00A972"},
    {"value": "neutral", "color": "#8BCAE7"},
    {"value": "mixed", "color": "#FFAB00"},
    {"value": "negative", "color": "#FF3621"},
]

# Datasets que carregam TODOS os parâmetros globais (game/language/tipo/período).
# Um filtro-parâmetro escreve o valor e TODOS estes datasets recomputam.
PARAM_DATASETS = ["kpis", "trend_themes", "trend_themes_abs", "trend_sentiment",
                  "trend_score", "trend_vol", "reader"]


def uid() -> str:
    return uuid.uuid4().hex[:8]


def theme_case_array():
    parts = ", ".join(f"CASE WHEN {c} THEN '{l}' END" for c, l in THEMES.items())
    return f"filter(array({parts}), x -> x IS NOT NULL)"


# ---- Parâmetros globais (modelagem cross-dataset) --------------------------
# Field filters NÃO cruzam datasets no Lakeview (só afetam widgets do MESMO
# dataset). Os datasets de série são pré-agregados (GROUP BY dia) e não expõem
# game/language, então um field filter jamais os alcançaria — e a média móvel
# precisa ser recalculada sobre o subconjunto filtrado. Por isso usamos
# DASHBOARD PARAMETERS (:game, :language, :tipo, :dt_start, :dt_end): cada
# dataset declara os parâmetros e um widget de filtro escreve o valor em TODOS
# eles de uma vez. Assim um filtro afeta TODAS as vizes de AMBAS as páginas.

def pdecl(keyword, dtype, default):
    return {"displayName": keyword, "keyword": keyword, "dataType": dtype,
            "defaultSelection": {"values": {"dataType": dtype,
                                             "values": [{"value": default}]}}}


# Declarações de parâmetro por dataset (mesma lista pra todos os PARAM_DATASETS).
# dt_start/dt_end são STRING (não DATE) de propósito: o date-range-picker envia
# string vazia ('') quando não há data selecionada (preset "All" ou default),
# e uma string vazia num parâmetro DATE faz a query FALHAR
# (INVALID_VALUE_FOR_DATA_TYPE). Com STRING + try_to_date(nullif(...,'')) a
# query tolera '' (= sem filtro) e datas reais.
GLOBAL_PARAMS = [
    pdecl("game", "STRING", "Todos"),
    pdecl("language", "STRING", "Todos"),
    pdecl("tipo", "STRING", "Todos"),
    pdecl("dt_start", "STRING", ""),
    pdecl("dt_end", "STRING", ""),
]

# WHERE aplicado no nível de linha (game/language/período). 'Todos' = sentinela.
# Datas: '' (vazio) = sem filtro naquele lado (não zera o dashboard).
WHERE_ROW = """(:game = 'Todos' OR game = :game)
    AND (:language = 'Todos' OR language = :language)
    AND (try_to_date(nullif(:dt_start, '')) IS NULL OR DATE(at) >= try_to_date(:dt_start))
    AND (try_to_date(nullif(:dt_end, '')) IS NULL OR DATE(at) <= try_to_date(:dt_end))"""


def base_subquery():
    """Subquery (sem WITH) das linhas filtradas por game/language/período E tipo."""
    return f"""(
  SELECT * FROM (
    SELECT *, {theme_case_array()} AS temas
    FROM {ENRICHED}
    WHERE {WHERE_ROW}
  ) WHERE (:tipo = 'Todos' OR array_contains(temas, :tipo))
)"""


def base_cte():
    """CTE 'f': linhas filtradas por game/language/período E tipo (via temas)."""
    return f"WITH f AS {base_subquery()}"


class Dash:
    def __init__(self, name):
        self.name = name
        self.datasets = []
        self.pages = []

    def dataset(self, name, display, query, params=None):
        # queryLines como UMA string (formato que renderiza no Lakeview);
        # split por linha quebra o carregamento do schema do dataset.
        ds = {"name": name, "displayName": display, "queryLines": [query]}
        if params:
            ds["parameters"] = params
        self.datasets.append(ds)
        return name

    def page(self, display):
        p = {"name": uid(), "displayName": display, "pageType": "PAGE_TYPE_CANVAS", "layout": []}
        self.pages.append(p)
        return p

    def to_json(self):
        return json.dumps({"datasets": self.datasets, "pages": self.pages,
                           "uiSettings": {"theme": {"widgetHeaderAlignment": "ALIGNMENT_UNSPECIFIED"}}},
                          indent=2)


def add(page, widget, x, y, w, h):
    page["layout"].append({"widget": widget, "position": {"x": x, "y": y, "width": w, "height": h}})


def q(dataset, fields, disaggregated=False):
    return [{"name": "main_query", "query": {
        "datasetName": dataset,
        "fields": [{"name": n, "expression": e} for n, e in fields],
        "disaggregated": disaggregated}}]


def counter(dataset, col, title, fmt=None):
    value = {"fieldName": col, "displayName": title}
    if fmt:
        value["format"] = fmt
    return {"name": uid(), "queries": q(dataset, [(col, f"`{col}`")], disaggregated=True),
            "spec": {"version": 2, "widgetType": "counter",
                     "encodings": {"value": value},
                     "frame": {"showTitle": True, "title": title}}}


def line(dataset, x, y, title, color=None, color_map=None, y_title="", zero=True):
    fields = [("day", f"`{x}`"), (y, f"`{y}`")]
    enc = {
        "x": {"fieldName": "day", "scale": {"type": "temporal"}, "displayName": "",
              "axis": {"tickFormat": "MMM d"}},
        "y": {"fieldName": y, "scale": {"type": "quantitative", "zeroBaseline": zero},
              "displayName": y_title},
    }
    if color:
        fields.append((color, f"`{color}`"))
        cs = {"type": "categorical"}
        if color_map:
            cs["mappings"] = color_map
        enc["color"] = {"fieldName": color, "scale": cs, "displayName": "Tema"}
    spec = {"version": 3, "widgetType": "line", "encodings": enc,
            "frame": {"showTitle": True, "title": title}}
    if not color:
        spec["mark"] = {"colors": [PRIMARY]}
    else:
        spec["mark"] = {"colors": SERIES}
    return {"name": uid(), "queries": q(dataset, fields), "spec": spec}


def area(dataset, x, y, title, y_title=""):
    fields = [("day", f"`{x}`"), (y, f"`{y}`")]
    return {"name": uid(), "queries": q(dataset, fields),
            "spec": {"version": 3, "widgetType": "area",
                     "encodings": {
                         "x": {"fieldName": "day", "scale": {"type": "temporal"},
                               "displayName": "", "axis": {"tickFormat": "MMM d"}},
                         "y": {"fieldName": y, "scale": {"type": "quantitative"},
                               "displayName": y_title}},
                     "mark": {"colors": ["#8BCAE7"]},
                     "frame": {"showTitle": True, "title": title}}}


def table(dataset, columns, title):
    fields, cols = [], []
    for i, c in enumerate(columns):
        fields.append({"name": c["field"], "expression": f"`{c['field']}`"})
        disp = {"string": "string", "integer": "number", "float": "number",
                "datetime": "datetime", "boolean": "boolean"}[c["type"]]
        col = {"fieldName": c["field"], "type": c["type"], "displayAs": disp,
               "title": c["title"], "order": i,
               "alignContent": "right" if disp in ("number", "datetime") else "left"}
        if c["type"] == "boolean":
            col["booleanValues"] = ["", "●"]
        cols.append(col)
    query = {"datasetName": dataset, "fields": fields, "disaggregated": True}
    return {"name": uid(),
            "queries": [{"name": "main_query", "query": query}],
            "spec": {"version": 1, "widgetType": "table",
                     "encodings": {"columns": cols},
                     "frame": {"showTitle": True, "title": title}}}


def gfilter(widget_type, dataset, field, title):
    qn = f"flt_{uid()}_{field}"
    return {"name": uid(),
            "queries": [{"name": qn, "query": {
                "datasetName": dataset,
                "fields": [{"name": field, "expression": f"`{field}`"},
                           {"name": f"{field}_assoc",
                            "expression": "COUNT_IF(`associative_filter_predicate_group`)"}],
                "disaggregated": False}}],
            "spec": {"version": 2, "widgetType": widget_type,
                     "encodings": {"fields": [{"fieldName": field, "displayName": title, "queryName": qn}]},
                     "frame": {"showTitle": True, "title": title}}}


def _param_query(dataset, keyword):
    """Query que liga um parâmetro do dashboard a UM dataset (escreve o valor)."""
    return {"name": f"prm_{dataset}_{keyword}",
            "query": {"datasetName": dataset,
                      "parameters": [{"name": keyword, "keyword": keyword}],
                      "disaggregated": False}}


def pfilter(widget_type, keyword, title, dim_dataset, dim_field,
            datasets=PARAM_DATASETS):
    """Filtro que escreve UM parâmetro global em TODOS os datasets de uma vez.

    - dim_dataset/dim_field: dataset de dimensão que fornece a LISTA de valores
      selecionáveis (dropdown). Selecionar um valor grava-o no parâmetro.
    - datasets: todos que declaram o parâmetro e devem recomputar ao filtrar.
    """
    dim_q = f"dim_{dim_dataset}_{dim_field}"
    queries = [{"name": dim_q, "query": {
        "datasetName": dim_dataset,
        "fields": [{"name": dim_field, "expression": f"`{dim_field}`"}],
        "disaggregated": False}}]
    fields = [{"fieldName": dim_field, "displayName": title, "queryName": dim_q}]
    for ds in datasets:
        queries.append(_param_query(ds, keyword))
        fields.append({"parameterName": keyword, "queryName": f"prm_{ds}_{keyword}"})
    return {"name": uid(), "queries": queries,
            "spec": {"version": 2, "widgetType": widget_type,
                     "encodings": {"fields": fields},
                     "frame": {"showTitle": True, "title": title}}}


def date_filter(title, datasets=PARAM_DATASETS):
    """Date-range-picker que escreve dt_start/dt_end em todos os datasets."""
    queries, fields = [], []
    for ds in datasets:
        queries.append(_param_query(ds, "dt_start"))
        queries.append(_param_query(ds, "dt_end"))
        fields.append({"parameterName": "dt_start", "queryName": f"prm_{ds}_dt_start"})
        fields.append({"parameterName": "dt_end", "queryName": f"prm_{ds}_dt_end"})
    return {"name": uid(), "queries": queries,
            "spec": {"version": 2, "widgetType": "filter-date-range-picker",
                     "encodings": {"fields": fields},
                     "frame": {"showTitle": True, "title": title}}}


def stacked_bar(dataset, x, y, color, title, color_map=None, y_title="",
                x_temporal=True):
    """Barras empilhadas (contagem por categoria de cor ao longo do tempo)."""
    fields = [(x, f"`{x}`"), (y, f"`{y}`"), (color, f"`{color}`")]
    cs = {"type": "categorical"}
    if color_map:
        cs["mappings"] = color_map
    enc = {
        "x": {"fieldName": x, "scale": {"type": "temporal" if x_temporal else "categorical"},
              "displayName": "", "axis": {"tickFormat": "MMM d"}},
        "y": {"fieldName": y, "scale": {"type": "quantitative"},
              "displayName": y_title, "axis": {"title": y_title}},
        "color": {"fieldName": color, "scale": cs, "displayName": "Sentimento"},
    }
    return {"name": uid(), "queries": q(dataset, fields),
            "spec": {"version": 3, "widgetType": "bar",
                     "encodings": enc, "mark": {"colors": DBX},
                     "frame": {"showTitle": True, "title": title}}}


def combo(dataset, x, area_y, line_y, title, area_title="", line_title=""):
    """Combo dual-axis: barra (volume) no eixo primário + linha (% negativo) no
    eixo secundário. No Lakeview o combo usa y/y2 com LISTA de measures
    (`fields`), não um único fieldName — daí a estrutura abaixo."""
    fields = [(x, f"`{x}`"), (area_y, f"`{area_y}`"), (line_y, f"`{line_y}`")]
    enc = {
        "x": {"fieldName": x, "scale": {"type": "temporal"}, "displayName": "",
              "axis": {"tickFormat": "MMM d"}},
        "y": {"fieldName": area_y, "scale": {"type": "quantitative"},
              "displayName": area_title, "axis": {"title": area_title},
              "mark": {"type": "bar", "colors": ["#8BCAE7"]}},
        "y2": {"fieldName": line_y, "scale": {"type": "quantitative"},
               "displayName": line_title, "axis": {"title": line_title},
               "mark": {"type": "line", "colors": ["#FF3621"]}},
    }
    return {"name": uid(), "queries": q(dataset, fields),
            "spec": {"version": 3, "widgetType": "combo",
                     "encodings": enc,
                     "frame": {"showTitle": True, "title": title}}}


def build():
    d = Dash(NAME)

    # ============================ DATASETS ============================
    # Datasets de DIMENSÃO para os dropdowns (lista de valores selecionáveis).
    # 'Todos' é a sentinela default (mostra tudo). NÃO levam parâmetros.
    d.dataset("dim_game", "Jogos",
              f"SELECT 'Todos' AS game UNION SELECT DISTINCT game FROM {ENRICHED} ORDER BY game")
    d.dataset("dim_lang", "Idiomas",
              f"SELECT 'Todos' AS language UNION SELECT DISTINCT language FROM {ENRICHED} ORDER BY language")
    themes_union = " UNION ".join(f"SELECT '{l}' AS tipo" for l in THEMES.values())
    d.dataset("dim_tipo", "Tipos de comentário",
              f"SELECT 'Todos' AS tipo UNION {themes_union} ORDER BY tipo")

    # Todos os datasets abaixo declaram GLOBAL_PARAMS e filtram pela CTE 'f'.
    # Assim um filtro-parâmetro afeta TODOS de uma vez (cross-dataset real).

    # KPIs dinâmicos sobre o conjunto filtrado (uma linha; counters usam disaggregated).
    # sent_score = média do score de sentimento (positive=1, neutral/mixed=0, negative=-1).
    d.dataset("kpis", "KPIs (filtrado)", base_cte() + """
SELECT
  ROUND(AVG(score), 2) AS nota,
  COUNT(*) AS volume,
  ROUND(AVG(CASE WHEN lower(sentiment)='positive' THEN 1
                 WHEN lower(sentiment)='negative' THEN -1 ELSE 0 END), 2) AS sent_score
FROM f""".rstrip(), params=GLOBAL_PARAMS)

    # Série: nota média móvel 7d por dia (recomputada sobre o filtro).
    d.dataset("trend_score", "Nota média móvel 7d", base_cte() + """,
daily AS (SELECT DATE(at) AS day, COUNT(*) AS n, SUM(score) AS s FROM f GROUP BY DATE(at))
SELECT day,
  ROUND(SUM(s) OVER (ORDER BY day RANGE BETWEEN INTERVAL 6 DAYS PRECEDING AND CURRENT ROW)
      / NULLIF(SUM(n) OVER (ORDER BY day RANGE BETWEEN INTERVAL 6 DAYS PRECEDING AND CURRENT ROW),0), 2) AS nota_7d
FROM daily ORDER BY day""".rstrip(), params=GLOBAL_PARAMS)

    # Série: SHARE móvel 7d de cada TEMA (%) por dia — o gráfico central.
    d.dataset("trend_themes", "Share de temas móvel 7d", base_cte() + f""",
ex AS (SELECT DATE(at) AS day, t AS tipo_t FROM f
       LATERAL VIEW explode({theme_case_array()}) x AS t),
tot AS (SELECT DATE(at) AS day, COUNT(*) AS n FROM f GROUP BY DATE(at)),
cnt AS (SELECT day, tipo_t, COUNT(*) AS c FROM ex GROUP BY day, tipo_t)
SELECT c.day, c.tipo_t AS tema,
  ROUND(100.0*SUM(c.c) OVER (PARTITION BY c.tipo_t ORDER BY c.day RANGE BETWEEN INTERVAL 6 DAYS PRECEDING AND CURRENT ROW)
      / NULLIF(SUM(t.n) OVER (ORDER BY c.day RANGE BETWEEN INTERVAL 6 DAYS PRECEDING AND CURRENT ROW),0), 1) AS share_7d
FROM cnt c JOIN tot t ON c.day = t.day
ORDER BY c.day, c.tipo_t""".rstrip(), params=GLOBAL_PARAMS)

    # Série: contagem móvel 7d ABSOLUTA de cada TEMA por dia (mesmo gráfico, número).
    d.dataset("trend_themes_abs", "Contagem de temas móvel 7d", base_cte() + f""",
ex AS (SELECT DATE(at) AS day, t AS tipo_t FROM f
       LATERAL VIEW explode({theme_case_array()}) x AS t),
cnt AS (SELECT day, tipo_t, COUNT(*) AS c FROM ex GROUP BY day, tipo_t)
SELECT day, tipo_t AS tema,
  SUM(c) OVER (PARTITION BY tipo_t ORDER BY day RANGE BETWEEN INTERVAL 6 DAYS PRECEDING AND CURRENT ROW) AS cnt_7d
FROM cnt ORDER BY day, tipo_t""".rstrip(), params=GLOBAL_PARAMS)

    # Série: contagem de avaliações por sentimento por semana (barras empilhadas).
    d.dataset("trend_sentiment", "Sentimento por semana", base_cte() + """
SELECT DATE(DATE_TRUNC('WEEK', at)) AS semana, lower(sentiment) AS sentimento, COUNT(*) AS n
FROM f GROUP BY 1, 2 ORDER BY 1, 2""".rstrip(), params=GLOBAL_PARAMS)

    # Série: volume diário + % negativos por dia (combo dual-axis).
    d.dataset("trend_vol", "Volume + % negativo diário", base_cte() + """,
daily AS (SELECT DATE(at) AS day, COUNT(*) AS n,
            SUM(CASE WHEN lower(sentiment)='negative' THEN 1 ELSE 0 END) AS neg
          FROM f GROUP BY DATE(at))
SELECT day, n AS reviews, ROUND(100.0*neg/NULLIF(n,0), 1) AS pct_neg
FROM daily ORDER BY day""".rstrip(), params=GLOBAL_PARAMS)

    # Leitura de comentários (aba operacional) — mesmos filtros globais.
    # Usa base_subquery() (sem leading WITH): o widget de tabela disaggregated
    # encapsula a query do dataset como `SELECT ... FROM (<query>)`, e um CTE
    # `WITH` no início quebra a introspecção de campos do widget ("no fields
    # selected"). Como subquery inline, o wrapper funciona.
    d.dataset("reader", "Leitor de comentários",
              "SELECT at, game AS jogo, language AS idioma, score AS nota, "
              "sentiment AS sentimento, content AS comentario, "
              "bug_report, pricing, game_balance, toxicity, community, visuals "
              f"FROM {base_subquery()} f "
              "WHERE content IS NOT NULL AND length(trim(content)) > 0",
              params=GLOBAL_PARAMS)

    # ==================== PÁGINA 1: MONITOR ====================
    p = d.page("Monitor")

    # --- Filtros GLOBAIS (topo) — cada um escreve UM parâmetro em TODOS os datasets ---
    add(p, pfilter("filter-single-select", "game", "Jogo", "dim_game", "game"), 0, 0, 2, 1)
    add(p, pfilter("filter-single-select", "language", "Idioma", "dim_lang", "language"), 2, 0, 1, 1)
    add(p, pfilter("filter-single-select", "tipo", "Tipo de comentário", "dim_tipo", "tipo"), 3, 0, 1, 1)
    add(p, date_filter("Período"), 4, 0, 2, 1)

    # --- Contadores dinâmicos (recalculam com os filtros) ---
    add(p, counter("kpis", "nota", "Nota média"), 0, 1, 2, 2)
    add(p, counter("kpis", "volume", "Comentários totais"), 2, 1, 2, 2)
    add(p, counter("kpis", "sent_score",
                   "Sentimento médio (positive=+1, negative=−1)"), 4, 1, 2, 2)

    # --- Tendência de temas: share móvel 7d (%) ---
    add(p, line("trend_themes", "day", "share_7d",
                "Tendência de temas — share móvel de 7 dias (% dos reviews)",
                color="tema", y_title="% dos reviews"), 0, 3, 6, 8)

    # --- Mesmo gráfico em NÚMERO ABSOLUTO (contagem móvel 7d por tema) ---
    add(p, line("trend_themes_abs", "day", "cnt_7d",
                "Tendência de temas — contagem móvel de 7 dias (nº de reviews)",
                color="tema", y_title="reviews (7d)"), 0, 11, 6, 8)

    # --- Barras empilhadas de sentimento por semana + Nota na Play Store, lado a lado ---
    add(p, stacked_bar("trend_sentiment", "semana", "n", "sentimento",
                       "Avaliações por sentimento (por semana)",
                       color_map=SENTIMENT_MAP, y_title="nº de avaliações"), 0, 19, 3, 7)
    add(p, line("trend_score", "day", "nota_7d",
                "Nota na Play Store — média móvel 7d", y_title="nota (1–5)", zero=False),
        3, 19, 3, 7)

    # --- Volume diário (área grande) + % negativo (linha) — ambos de trend_vol ---
    # NOTA: combo dual-axis (widgetType 'combo') NÃO renderiza via serialized JSON
    # no Lakeview (testado em 3 formatos de encoding — widget fica vazio, "Ask the
    # assistant"). Fallback documentado: duas vizes empilhadas do MESMO dataset,
    # cada uma com seu eixo Y próprio. Volume grande + % negativo logo abaixo.
    add(p, area("trend_vol", "day", "reviews",
                "Volume diário de reviews", y_title="reviews/dia"), 0, 26, 6, 6)
    add(p, line("trend_vol", "day", "pct_neg",
                "% de reviews negativos por dia", y_title="% negativo", zero=True),
        0, 32, 6, 5)

    # ==================== PÁGINA 2: LER COMENTÁRIOS ====================
    p2 = d.page("Ler comentários")
    # Mesmos filtros globais (escrevem os mesmos parâmetros em todos os datasets).
    add(p2, pfilter("filter-single-select", "game", "Jogo", "dim_game", "game"), 0, 0, 2, 1)
    add(p2, pfilter("filter-single-select", "language", "Idioma", "dim_lang", "language"), 2, 0, 1, 1)
    add(p2, pfilter("filter-single-select", "tipo", "Tipo de comentário", "dim_tipo", "tipo"), 3, 0, 1, 1)
    add(p2, date_filter("Período"), 4, 0, 2, 1)

    # Contador de comentários (total filtrado).
    add(p2, counter("kpis", "volume", "Comentários (filtrados)"), 0, 1, 2, 2)

    # ISOLATION TEST: tabela sobre dataset SEM parâmetros
    d.dataset("reader_np", "Leitor (sem params)",
              f"SELECT at, game AS jogo, language AS idioma, score AS nota, "
              f"sentiment AS sentimento, content AS comentario, "
              f"bug_report, pricing, game_balance, toxicity, community, visuals "
              f"FROM {ENRICHED} WHERE content IS NOT NULL AND length(trim(content)) > 0")
    add(p2, table("reader_np", [
        {"field": "at", "title": "Data", "type": "datetime"},
        {"field": "jogo", "title": "Jogo", "type": "string"},
        {"field": "idioma", "title": "Idioma", "type": "string"},
        {"field": "nota", "title": "Nota", "type": "integer"},
        {"field": "sentimento", "title": "Sentimento", "type": "string"},
        {"field": "bug_report", "title": "Bug", "type": "boolean"},
        {"field": "toxicity", "title": "Tóxico", "type": "boolean"},
        {"field": "comentario", "title": "Comentário", "type": "string"},
    ], "Comentários filtrados"), 0, 3, 6, 10)

    return d


def deploy(dashboard):
    serialized = dashboard.to_json()
    existing = subprocess.run(
        ["databricks", "api", "get", "/api/2.0/lakeview/dashboards", "-p", PROFILE],
        capture_output=True, text=True)
    dash_id = None
    if existing.returncode == 0 and existing.stdout.strip():
        for dsh in json.loads(existing.stdout).get("dashboards", []):
            if dashboard.name in dsh.get("display_name", ""):
                dash_id = dsh["dashboard_id"]
                break
    if dash_id:
        body = {"display_name": dashboard.name, "serialized_dashboard": serialized,
                "warehouse_id": WAREHOUSE_ID}
        r = subprocess.run(
            ["databricks", "api", "patch", f"/api/2.0/lakeview/dashboards/{dash_id}",
             "-p", PROFILE, "--json", json.dumps(body)], capture_output=True, text=True)
        print("PATCH", dash_id, r.returncode, (r.stderr or r.stdout)[:300])
    else:
        payload = {"display_name": dashboard.name, "warehouse_id": WAREHOUSE_ID,
                   "parent_path": PARENT_PATH, "serialized_dashboard": serialized}
        r = subprocess.run(
            ["databricks", "api", "post", "/api/2.0/lakeview/dashboards",
             "-p", PROFILE, "--json", json.dumps(payload)], capture_output=True, text=True)
        print("POST", r.returncode, (r.stderr or r.stdout)[:300])
    return r


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--deploy", action="store_true")
    ap.add_argument("--write", metavar="PATH")
    args = ap.parse_args()
    dash = build()
    if args.write:
        with open(args.write, "w") as f:
            f.write(dash.to_json())
        print(f"escrito em {args.write}")
    elif args.deploy:
        deploy(dash)
    else:
        print(dash.to_json())
