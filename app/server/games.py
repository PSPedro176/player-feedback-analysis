"""Metadados dos jogos monitorados.

Os ícones são as URLs oficiais da Play Store, obtidas via google-play-scraper
(campo `icon` de app(package_name)). São servidas direto do CDN do Google.

IMPORTANTE: Os jogos são configurados na variável `games` de databricks.yml
e passados via base_parameters dos jobs. Este arquivo fornece um fallback
com exemplos genéricos. Para adicionar novos jogos, edite databricks.yml.
"""

# Fallback genérico com exemplos (os jogos reais vêm do databricks.yml)
GAMES = [
    {
        "name": "Exemplo 1",
        "package": "com.example.game1",
        "icon": "https://play-lh.googleusercontent.com/placeholder-icon-1",
        "accent": "#FF4D6D",
    },
    {
        "name": "Exemplo 2",
        "package": "com.example.game2",
        "icon": "https://play-lh.googleusercontent.com/placeholder-icon-2",
        "accent": "#4DD0FF",
    },
]

GAME_NAMES = [g["name"] for g in GAMES]
