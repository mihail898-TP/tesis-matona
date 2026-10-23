"""The Odds API v4 — cuotas de casas de apuestas tradicionales.

GET /v4/sports/{sport}/odds
Costo: (nº de markets) x (nº de regions) créditos por request.

Se hacen dos llamadas separadas para controlar el gasto:
  1. línea de dinero en us+eu  -> 2 créditos (la región europea trae Pinnacle,
     que es la referencia de la literatura por su bajo margen)
  2. spread y total solo en us -> 2 créditos
Total 4 por captura, unos 11.500 al mes con capturas cada 15 minutos.
Los headers x-requests-remaining / x-requests-used informan el saldo.
"""
from __future__ import annotations

import common
import config

TIPO = {"h2h": "moneyline", "spreads": "spread", "totals": "total"}


def _pedir(markets: str, regions: str, storage_ts: str) -> list[dict]:
    url = f"{config.ODDS_API_BASE}/sports/{config.LEAGUE}/odds"
    data = common.get_json(url, params={
        "apiKey": config.ODDS_API_KEY,
        "regions": regions,
        "markets": markets,
        "oddsFormat": "decimal",
        "dateFormat": "iso",
    })
    if not data:
        return []

    filas = []
    for ev in data:
        home, away = ev.get("home_team"), ev.get("away_team")
        ekey = common.event_key(config.LEAGUE, ev.get("commence_time"),
                                home, away)
        for bk in ev.get("bookmakers", []):
            if config.BOOKS_FILTER and bk.get("key") not in config.BOOKS_FILTER:
                continue
            for mk in bk.get("markets", []):
                tipo = TIPO.get(mk.get("key"))
                if not tipo:
                    continue
                for out in mk.get("outcomes", []):
                    precio = out.get("price")
                    if not precio:
                        continue
                    filas.append({
                        "captured_at": storage_ts,
                        "source": "odds_api",
                        "book": bk.get("key"),
                        "league": config.LEAGUE,
                        "market_type": tipo,
                        "line": out.get("point"),
                        "event_key": ekey,
                        "source_event_id": ev.get("id"),
                        "commence_time": ev.get("commence_time"),
                        "home_team": home,
                        "away_team": away,
                        "outcome": out.get("name"),
                        "price_decimal": precio,
                        # Probabilidad SIN normalizar: los dos lados suman más
                        # de 1 y ese exceso es el margen de la casa. Se remueve
                        # en el análisis, no acá, para poder después probar
                        # distintos métodos y reportar la sensibilidad.
                        "prob_raw": 1.0 / precio,
                        "best_bid": None, "best_ask": None, "mid": None,
                        "volume": None,
                        "raw": {"book_update": bk.get("last_update")},
                    })
    return filas


def fetch(storage_ts: str) -> list[dict]:
    if not config.ODDS_API_KEY:
        print("  [odds_api] sin ODDS_API_KEY, se omite")
        return []

    filas = _pedir("h2h", config.ODDS_REGIONS_H2H, storage_ts)
    if config.ODDS_EXTRA_MARKETS:
        filas += _pedir(config.ODDS_EXTRA_MARKETS,
                        config.ODDS_REGIONS_EXTRA, storage_ts)

    libros = {f["book"] for f in filas}
    print(f"  [odds_api] {len(filas)} filas, {len(libros)} casas")
    return filas
