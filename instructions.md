# Handoff — Extração de reviews da Play Store

Biblioteca: `google-play-scraper` (`%pip install google-play-scraper`). Extrair por package name, sem autenticação.

## Duas formas de extrair

**1. `reviews_all` — simples, uma chamada.** Pega todos os reviews de uma vez.
- Usar `sort=Sort.NEWEST` (o default `MOST_RELEVANT` é truncado em poucos milhares).
- Usar `sleep_milliseconds` (~300) para não tomar HTTP 429.
- Limitação: segura tudo em memória e, se cair no meio, perde a extração inteira. Ok para volumes menores.

```python
from google_play_scraper import reviews_all, Sort
result = reviews_all('com.exemplo.jogo', lang='pt', country='br',
                     sort=Sort.NEWEST, sleep_milliseconds=300)
```

**Paginação com `continuation_token` — robusta, recomendada para 10k+.** Pagina de 200 em 200 e permite gravar em Delta em lotes (checkpoint). Se o job cair, o já extraído fica salvo.

```python
import time
from google_play_scraper import reviews, Sort

token, total = None, 0
while True:
    result, token = reviews('com.exemplo.jogo', lang='pt', country='br',
                            sort=Sort.NEWEST, count=200, continuation_token=token)
    # gravar `result` em Delta (append) aqui, em lotes
    total += len(result)
    if token is None:
        break
    time.sleep(0.3)
```

Máx. 200 por página. Reviews são particionados por idioma — para amostra completa, iterar sobre idiomas e deduplicar por `reviewId`.