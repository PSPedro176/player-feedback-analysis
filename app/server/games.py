"""Metadados dos 4 jogos monitorados (Wildlife Studios).

Os ícones são as URLs oficiais da Play Store, obtidas via google-play-scraper
(campo `icon` de app(package_name)). São servidas direto do CDN do Google.
"""

GAMES = [
    {
        "name": "Sniper 3D",
        "package": "com.fungames.sniper3d",
        "icon": "https://play-lh.googleusercontent.com/seWyOBcAUUgzE8USqm7I5W9qZ2McX6USk8aRBSQ7HJLLwjPyjnrJV9rf66ZD2icbwKUXcBnB3fCchLqXGtGEEKY",
        "accent": "#FF4D6D",
    },
    {
        "name": "Tennis Clash",
        "package": "com.tfgco.games.sports.free.tennis.clash",
        "icon": "https://play-lh.googleusercontent.com/b3yRWP2AEJEKVLUxbL7FIW-bzmI9Nnw3I0CGFehV2VMLoacEzFpRwbYzNOxsvk4gTRdMRj90GPuDZ6nEczSR",
        "accent": "#4DD0FF",
    },
    {
        "name": "Zooba",
        "package": "com.wildlife.games.battle.royale.free.zooba",
        "icon": "https://play-lh.googleusercontent.com/BE45SsFAltu5ZQnshQiMtFwbNttP-jqeN1t9_k6_E394mXNZQpkeTKtllmWBNiAf1n31oaoY1m6p4EW2sav3Hw",
        "accent": "#FFB84D",
    },
    {
        "name": "Soccer Clash",
        "package": "com.wildlifestudios.soccer",
        "icon": "https://play-lh.googleusercontent.com/4bm7JXa9P4JJTn09I2bTsZGUJe1VSCGoUQsuuO-_aCU_ziNMO9rb51BBu84191gsuUQN8kHtuue55FT6xkTL",
        "accent": "#7CFF4D",
    },
]

GAME_NAMES = [g["name"] for g in GAMES]
