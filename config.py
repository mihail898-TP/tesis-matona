"""Configuración central del capturador.

Todo lo sensible (API keys, URL de la base) va por variables de entorno.
Nunca escribas una key dentro de este archivo: si lo subes a GitHub queda
pública.
"""
import os

# --- Liga a capturar -------------------------------------------------------
LEAGUE = os.getenv("LEAGUE", "basketball_nba")

# --- The Odds API (casas de apuestas tradicionales) ------------------------
ODDS_API_KEY = os.getenv("ODDS_API_KEY", "")
ODDS_API_BASE = "https://api.the-odds-api.com/v4"

# Dos llamadas para controlar el gasto de créditos (ver sources/odds_api.py).
# Línea de dinero en las dos regiones: la europea es la que trae Pinnacle.
ODDS_REGIONS_H2H = os.getenv("ODDS_REGIONS_H2H", "us,eu")
# Spread y total solo en la estadounidense. Dejar vacío para no pedirlos.
ODDS_EXTRA_MARKETS = os.getenv("ODDS_EXTRA_MARKETS", "spreads,totals")
ODDS_REGIONS_EXTRA = os.getenv("ODDS_REGIONS_EXTRA", "us")

# Casas que interesan. Lista vacía = guardar todas las que devuelva la API.
BOOKS_FILTER = [b for b in os.getenv(
    "BOOKS_FILTER", "pinnacle,draftkings,fanduel,betmgm").split(",") if b]

# --- Kalshi (exchange regulado, lectura pública sin API key) ---------------
KALSHI_BASE = os.getenv(
    "KALSHI_BASE", "https://api.elections.kalshi.com/trade-api/v2"
)
KALSHI_SERIES = [s for s in os.getenv("KALSHI_SERIES", "KXNBAGAME").split(",") if s]

# --- Polymarket (exchange on-chain, lectura pública) ----------------------
GAMMA_BASE = "https://gamma-api.polymarket.com"
CLOB_BASE = "https://clob.polymarket.com"
POLY_TAG = os.getenv("POLY_TAG", "nba")
POLY_PAGINAS = int(os.getenv("POLY_PAGINAS", "3"))  # 100 eventos por página

# Futuros que SÍ se capturan: los que resuelven dentro del semestre y tienen
# hora de anuncio conocida, que son los útiles para el análisis de movimiento
# informado previo. Los de temporada completa (campeón, novato) se excluyen
# porque no alcanzan a resolverse.
POLY_FUTURES_KEYWORDS = [k for k in os.getenv(
    "POLY_FUTURES_KEYWORDS",
    "next-team,to-leave,traded,trade,sign-with,retire,waived,coach"
).split(",") if k]

# Profundidad del libro de órdenes. Es el único dato que NO existe en ningún
# histórico: las velas guardan precio de transacción, no cuántos contratos
# había ofrecidos en cada nivel. Cuesta una consulta extra por mercado, así
# que se limita a los mercados de partido y con un tope por captura.
POLY_DEPTH = os.getenv("POLY_DEPTH", "1") not in ("0", "false", "False")
POLY_DEPTH_NIVELES = int(os.getenv("POLY_DEPTH_NIVELES", "5"))
POLY_DEPTH_MAX = int(os.getenv("POLY_DEPTH_MAX", "150"))

# Ventana de captura fina. Los partidos que empiezan dentro de CERCA_HORAS se
# capturan en cada corrida (cada 15 min). Los más lejanos y los futuros, solo
# una vez cada LEJOS_CADA_HORAS horas: cambian poco y eran la mayor parte del
# volumen de la base.
CERCA_HORAS = float(os.getenv("CERCA_HORAS", "48"))
LEJOS_CADA_HORAS = int(os.getenv("LEJOS_CADA_HORAS", "3"))

# --- Almacenamiento --------------------------------------------------------
DATABASE_URL = os.getenv("DATABASE_URL", "")
CSV_DIR = os.getenv("CSV_DIR", "data")

# --- Red -------------------------------------------------------------------
TIMEOUT = 20
RETRIES = 3
USER_AGENT = "tesis-apuestas/0.2 (investigacion academica)"
