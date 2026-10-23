"""Utilidades compartidas: HTTP con reintentos, normalización de equipos y
construcción de la llave canónica de partido."""
from __future__ import annotations

import datetime as dt
import re
import time
import unicodedata
from zoneinfo import ZoneInfo

import requests

import config

_session = requests.Session()
_session.headers.update({"User-Agent": config.USER_AGENT})

# La NBA programa por fecha del este de EE.UU. Un partido que empieza a las
# 22:00 de Nueva York es 02:00 UTC del día siguiente: si cada fuente usa una
# zona distinta, el mismo partido queda con dos fechas y no se empareja nunca.
ET = ZoneInfo("America/New_York")


def get_json(url: str, params: dict | None = None, headers: dict | None = None):
    """GET con reintentos y backoff. Devuelve None si falla definitivamente."""
    last = None
    for intento in range(config.RETRIES):
        try:
            r = _session.get(
                url, params=params, headers=headers, timeout=config.TIMEOUT
            )
            if r.status_code == 429:  # rate limit
                time.sleep(2 ** intento * 3)
                continue
            r.raise_for_status()
            return r.json()
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(2 ** intento)
    print(f"  [error] {url} -> {last}")
    return None


def now_utc() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def iso(ts) -> str | None:
    if ts is None:
        return None
    if isinstance(ts, dt.datetime):
        return ts.astimezone(dt.timezone.utc).isoformat()
    return str(ts)


def num(x) -> float | None:
    """Kalshi entrega los precios como texto ('0.7000'). Convierte a float."""
    if x is None or x == "":
        return None
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def fecha_et(ts_iso: str | None) -> str:
    """Fecha del partido en hora del este de EE.UU., formato YYYY-MM-DD."""
    if not ts_iso:
        return ""
    try:
        s = str(ts_iso).replace("Z", "+00:00")
        d = dt.datetime.fromisoformat(s)
        if d.tzinfo is None:
            d = d.replace(tzinfo=dt.timezone.utc)
        return d.astimezone(ET).date().isoformat()
    except (ValueError, TypeError):
        return str(ts_iso)[:10]


# --------------------------------------------------------------------------
# Normalización de nombres de equipo
# --------------------------------------------------------------------------
# Cada fuente nombra distinto: "Los Angeles Lakers" (Odds API), "LAL" (Kalshi),
# "Lakers" (Polymarket). Todo se reduce al apodo en minúscula.

NBA_ALIAS = {
    "atl": "hawks", "bos": "celtics", "bkn": "nets", "bro": "nets",
    "cha": "hornets", "chi": "bulls", "cle": "cavaliers", "dal": "mavericks",
    "den": "nuggets", "det": "pistons", "gsw": "warriors", "gs": "warriors",
    "hou": "rockets", "ind": "pacers", "lac": "clippers", "lal": "lakers",
    "mem": "grizzlies", "mia": "heat", "mil": "bucks", "min": "timberwolves",
    "nop": "pelicans", "no": "pelicans", "nyk": "knicks", "ny": "knicks",
    "okc": "thunder", "orl": "magic", "phi": "76ers", "phx": "suns",
    "pho": "suns", "por": "trail blazers", "sac": "kings", "sas": "spurs",
    "sa": "spurs", "tor": "raptors", "uta": "jazz", "utah": "jazz",
    "was": "wizards", "wsh": "wizards",
    # nombres de ciudad truncados que aparecen en los títulos de Kalshi
    "los angeles l": "lakers", "golden state": "warriors",
    "oklahoma city": "thunder", "new orleans": "pelicans",
    "san antonio": "spurs", "new york": "knicks", "portland": "trail blazers",
    "minnesota": "timberwolves", "indiana": "pacers", "utah": "jazz",
    "denver": "nuggets", "miami": "heat", "toronto": "raptors",
    "philadelphia": "76ers", "phoenix": "suns", "sacramento": "kings",
    "boston": "celtics", "brooklyn": "nets", "charlotte": "hornets",
    "chicago": "bulls", "cleveland": "cavaliers", "dallas": "mavericks",
    "detroit": "pistons", "houston": "rockets", "memphis": "grizzlies",
    "milwaukee": "bucks", "orlando": "magic", "atlanta": "hawks",
    "washington": "wizards",
}

MULTIWORD = ["trail blazers"]


def slug(texto: str) -> str:
    """minúsculas, sin acentos, sin puntuación."""
    if not texto:
        return ""
    t = unicodedata.normalize("NFKD", str(texto))
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = t.lower().strip()
    t = re.sub(r"[^a-z0-9 ]+", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def team_key(nombre: str) -> str:
    """Devuelve el apodo canónico del equipo a partir de cualquier variante."""
    s = slug(nombre)
    if not s:
        return ""
    s = re.sub(r"\s+wins$", "", s)        # "Minnesota wins" -> "minnesota"
    if s in NBA_ALIAS:
        return NBA_ALIAS[s]
    for m in MULTIWORD:
        if m in s:
            return m
    partes = s.split()
    if partes and partes[-1] in NBA_ALIAS:
        return NBA_ALIAS[partes[-1]]
    return partes[-1] if partes else s


def event_key(league: str, commence_iso: str | None,
              home: str, away: str, fecha: str | None = None) -> str:
    """Llave canónica: liga + fecha (hora del este) + equipos ordenados.

    Se ordenan alfabéticamente para no depender de que cada fuente respete la
    convención local/visita, que no todas respetan.
    """
    f = fecha or fecha_et(commence_iso)
    a, b = sorted([team_key(home), team_key(away)])
    return f"{league}|{f}|{a}-{b}"
