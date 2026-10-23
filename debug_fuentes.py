"""Diagnóstico: imprime los datos crudos de Kalshi y Polymarket.

Uso:  python debug_fuentes.py
No guarda nada, solo muestra qué devuelven las APIs para poder ajustar
los parseadores a la estructura real.
"""
import json

import common
import config


def corta(obj, n=1400):
    s = json.dumps(obj, indent=2, ensure_ascii=False)
    return s[:n] + ("\n  ...(cortado)" if len(s) > n else "")


print("=" * 70)
print("KALSHI — series:", config.KALSHI_SERIES)
print("=" * 70)
for serie in config.KALSHI_SERIES:
    d = common.get_json(f"{config.KALSHI_BASE}/markets",
                        params={"series_ticker": serie, "status": "open",
                                "limit": 4})
    if not d:
        print("  sin respuesta")
        continue
    ms = d.get("markets", [])
    print(f"  {len(ms)} mercados devueltos. Primeros dos completos:\n")
    for m in ms[:2]:
        print(corta(m))
        print("-" * 50)
    print("\n  Tickers y títulos de los 4 primeros:")
    for m in ms:
        print("   ticker :", m.get("ticker"))
        print("   event  :", m.get("event_ticker"))
        print("   title  :", m.get("title"))
        print("   yes_sub:", m.get("yes_sub_title"))
        print("   bid/ask:", m.get("yes_bid"), m.get("yes_ask"),
              "| last:", m.get("last_price"), "| vol:", m.get("volume"))
        print()

print()
print("=" * 70)
print("POLYMARKET — probando varias formas de encontrar la NBA")
print("=" * 70)

pruebas = [
    ("markets tag_slug=nba", f"{config.GAMMA_BASE}/markets",
     {"closed": "false", "active": "true", "tag_slug": "nba", "limit": 5}),
    ("events tag_slug=nba", f"{config.GAMMA_BASE}/events",
     {"closed": "false", "active": "true", "tag_slug": "nba", "limit": 5}),
    ("markets sin tag", f"{config.GAMMA_BASE}/markets",
     {"closed": "false", "active": "true", "limit": 5}),
]

for nombre, url, params in pruebas:
    d = common.get_json(url, params=params)
    items = d if isinstance(d, list) else (d or {}).get("data", [])
    print(f"\n--- {nombre}: {len(items)} resultados")
    for it in items[:3]:
        print("   question/title:", it.get("question") or it.get("title"))
        print("   slug          :", it.get("slug"))
        print("   gameStartTime :", it.get("gameStartTime"))
        print("   outcomes      :", it.get("outcomes"))
        print("   clobTokenIds  :", str(it.get("clobTokenIds"))[:90])
        print("   volumeNum     :", it.get("volumeNum"))
        print()

print("\n--- Estructura completa del primer mercado (markets sin tag):")
d = common.get_json(f"{config.GAMMA_BASE}/markets",
                    params={"closed": "false", "active": "true", "limit": 1})
items = d if isinstance(d, list) else (d or {}).get("data", [])
if items:
    print("   claves disponibles:", sorted(items[0].keys()))
