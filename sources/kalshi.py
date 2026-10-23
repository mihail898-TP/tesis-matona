"""Kalshi — exchange regulado por la CFTC. Lectura pública, sin API key.

Estructura real (verificada contra la API el 2026-10-02):
  event_ticker : KXNBAGAME-26OCT07MININD   <- fecha ET + los dos equipos
  ticker       : KXNBAGAME-26OCT07MININD-MIN  <- el sufijo es el lado YES
  precios      : campos *_dollars, como TEXTO ("0.7000"), no en centavos

Cada partido genera dos mercados, uno por equipo. Ambos comparten event_ticker.
Si no vienen yes_bid/yes_ask se derivan del lado NO: comprar YES a p equivale
a vender NO a 1-p, así que yes_bid = 1 - no_ask y yes_ask = 1 - no_bid.
"""
from __future__ import annotations

import re

import common
import config

MESES = {"JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
         "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12}

# KXNBAGAME-26OCT07MININD  ->  (26, OCT, 07, MIN, IND)
RE_EVENTO = re.compile(r"-(\d{2})([A-Z]{3})(\d{2})([A-Z]{2,4})([A-Z]{3})$")


def _parse_evento(event_ticker: str):
    """Devuelve (fecha_iso, equipo_a, equipo_b) o None si no calza."""
    m = RE_EVENTO.search(event_ticker or "")
    if not m:
        return None
    yy, mon, dd, t1, t2 = m.groups()
    if mon not in MESES:
        return None
    fecha = f"20{yy}-{MESES[mon]:02d}-{int(dd):02d}"
    return fecha, t1, t2


def fetch(storage_ts: str) -> list[dict]:
    filas, sin_parsear = [], 0
    for serie in config.KALSHI_SERIES:
        data = common.get_json(
            f"{config.KALSHI_BASE}/markets",
            params={"series_ticker": serie, "status": "open", "limit": 500},
        )
        if not data:
            continue
        for m in data.get("markets", []):
            ev = _parse_evento(m.get("event_ticker", ""))
            if not ev:
                sin_parsear += 1
                continue
            fecha, t1, t2 = ev

            # Lado YES: el sufijo del ticker. Si falta, cae al subtítulo.
            tk = m.get("ticker") or ""
            lado = tk.rsplit("-", 1)[-1] if "-" in tk else ""
            yes_team = common.team_key(lado) or common.team_key(
                m.get("yes_sub_title") or "")

            # Precios: campos *_dollars en texto.
            yb = common.num(m.get("yes_bid_dollars"))
            ya = common.num(m.get("yes_ask_dollars"))
            nb = common.num(m.get("no_bid_dollars"))
            na = common.num(m.get("no_ask_dollars"))
            if yb is None and na is not None:
                yb = round(1.0 - na, 4)
            if ya is None and nb is not None:
                ya = round(1.0 - nb, 4)
            last = common.num(m.get("last_price_dollars"))
            mid = (yb + ya) / 2 if (yb is not None and ya is not None) else last

            filas.append({
                "captured_at": storage_ts,
                "source": "kalshi",
                "book": None,
                "league": config.LEAGUE,
                "market_type": "moneyline",
                "line": None,
                "event_key": common.event_key(
                    config.LEAGUE, None, t1, t2, fecha=fecha),
                "source_event_id": m.get("ticker"),
                "commence_time": m.get("occurrence_datetime")
                                 or m.get("expected_expiration_time"),
                "home_team": t2,     # en el ticker el segundo es el local
                "away_team": t1,
                "outcome": yes_team,
                "price_decimal": None,
                "prob_raw": mid,
                "best_bid": yb,
                "best_ask": ya,
                "mid": mid,
                "volume": m.get("volume"),
                "raw": {"last": last,
                        "open_interest": m.get("open_interest_fp"),
                        "event_ticker": m.get("event_ticker"),
                        "title": m.get("title")},
            })
    extra = f" ({sin_parsear} sin parsear)" if sin_parsear else ""
    print(f"  [kalshi] {len(filas)} filas{extra}")
    return filas
