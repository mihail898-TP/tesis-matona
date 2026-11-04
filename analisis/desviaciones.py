"""Primer cálculo de desviaciones de la ley de un precio (moneyline NBA).

Uso:  python analisis/desviaciones.py captures.csv [salida_dir]

Compara, partido a partido y captura a captura, la probabilidad implícita
de un mismo resultado en Kalshi, Polymarket y las casas de Odds API.

- Kalshi / Polymarket: punto medio bid-ask (mid).
- Casas: 1/cuota decimal, sin margen (normalizando los dos lados a 1).
- Equipo de referencia: el primero en orden alfabético del event_key, para
  que todas las fuentes miren el mismo lado.
- Solo capturas previas al inicio del partido.
- Arbitraje ejecutable K-P: comprar A en una plataforma y B en la otra a los
  mejores ask; hay arbitraje bruto si la suma es < 1 (antes de comisiones).
- Ganador: se infiere del último precio de Kalshi/Polymarket ya terminado el
  partido (> 0.9).
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import common  # noqa: E402

ruta = sys.argv[1] if len(sys.argv) > 1 else "captures.csv"
out = sys.argv[2] if len(sys.argv) > 2 else "analisis/salida"
os.makedirs(out, exist_ok=True)

cols = ["captured_at", "source", "book", "market_type", "event_key",
        "commence_time", "outcome", "price_decimal", "best_bid", "best_ask",
        "mid"]
d = pd.read_csv(ruta, usecols=cols)
d = d[(d.market_type == "moneyline") & ~d.event_key.str.contains("margin")]
d["ts"] = pd.to_datetime(d.captured_at, format="ISO8601")
d["ct"] = pd.to_datetime(d.commence_time, format="ISO8601")
# Kalshi guarda en commence_time el cierre esperado del contrato (~2h50 después
# del salto inicial), no el inicio. El inicio del partido se toma de Polymarket
# u Odds API (la más temprana); sin ellas, la de Kalshi menos 3 h.
ini = (d[d.source != "kalshi"].groupby("event_key").ct.min()
       .combine_first(d[d.source == "kalshi"].groupby("event_key").ct.min()
                      - pd.Timedelta(hours=3)))
d["ct"] = d.event_key.map(ini)
d["run"] = d.ts.dt.floor("15min")
d["team"] = d.outcome.map(common.team_key)
d["ref"] = d.event_key.str.split("|").str[2].str.split("-").str[0]
# el apodo "trail blazers" queda con espacio en la llave
d.loc[d.event_key.str.contains("|trail blazers-", regex=False), "ref"] = "trail blazers"

# --- ganador, desde los precios posteriores al partido ----------------------
post = d[(d.source.isin(["kalshi", "polymarket"]))
         & (d.ts > d.ct + pd.Timedelta(hours=3))]
ult = post.sort_values("ts").groupby(["event_key", "team"]).mid.last().reset_index()
gan = ult[ult.mid > 0.9].drop_duplicates("event_key").set_index("event_key").team

pre = d[d.ts < d.ct].copy()

# --- probabilidades del equipo de referencia por fuente ---------------------
pm = pre[pre.source.isin(["kalshi", "polymarket"]) & (pre.team == pre.ref)]
pm = pm.groupby(["event_key", "run", "source"]).agg(
    mid=("mid", "last"), ask=("best_ask", "last"), bid=("best_bid", "last"),
    ct=("ct", "first")).reset_index()

# Polymarket guarda bid/ask solo en el primer token; el ask del otro lado es
# 1 - bid del primero. Para Kalshi cada equipo tiene su propio libro.
lado = pre[pre.source.isin(["kalshi", "polymarket"])]
otro = lado[lado.team != lado.ref].groupby(["event_key", "run", "source"]).agg(
    ask_o=("best_ask", "last"), bid_o=("best_bid", "last")).reset_index()
pm = pm.merge(otro, on=["event_key", "run", "source"], how="left")
pm["ask_o"] = pm.ask_o.fillna(1 - pm.bid)          # Polymarket, lado B
pm["ask"] = pm.ask.fillna(1 - pm.bid_o)            # Polymarket, si A no tenía

oa = pre[pre.source == "odds_api"].copy()
oa["p"] = 1 / oa.price_decimal
oa["suma"] = oa.groupby(["event_key", "run", "book"]).p.transform("sum")
oa = oa[oa.team == oa.ref]
oa["p_nv"] = oa.p / oa.suma                         # sin margen
casas = oa.pivot_table(index=["event_key", "run"], columns="book",
                       values="p_nv", aggfunc="last")
casas["consenso"] = casas.median(axis=1)

ancho = pm.pivot_table(index=["event_key", "run"], columns="source",
                       values=["mid", "ask", "ask_o"], aggfunc="last")
ancho.columns = [f"{a}_{b}" for a, b in ancho.columns]
ancho = ancho.join(pm.groupby(["event_key", "run"]).ct.first())
ancho = ancho.join(casas, how="left").reset_index()
ancho["h_antes"] = (ancho.ct - ancho.run).dt.total_seconds() / 3600

tres = set(d.groupby("event_key").source.nunique().loc[lambda s: s == 3].index)
jugados = set(gan.index) & tres
ancho = ancho[ancho.event_key.isin(jugados)]

# --- 1. Kalshi vs Polymarket, todas las capturas ----------------------------
kp = ancho.dropna(subset=["mid_kalshi", "mid_polymarket"]).copy()
kp["dif"] = kp.mid_kalshi - kp.mid_polymarket
kp["absdif"] = kp.dif.abs()
kp["arb1"] = kp.ask_kalshi + kp.ask_o_polymarket   # A en K, B en P
kp["arb2"] = kp.ask_polymarket + kp.ask_o_kalshi   # A en P, B en K
kp["arb"] = kp[["arb1", "arb2"]].min(axis=1)
kp["tramo"] = pd.cut(kp.h_antes, [0, 1, 3, 6, 12, 24, 48, 1e9],
                     labels=["<1h", "1-3h", "3-6h", "6-12h", "12-24h",
                             "24-48h", ">48h"])

# --- 2. Casas vs mercados de predicción (solo corridas con Odds API) --------
cb = ancho.dropna(subset=["consenso"]).copy()
for s in ("kalshi", "polymarket"):
    cb[f"dif_{s}"] = cb[f"mid_{s}"] - cb.consenso
if "pinnacle" in cb:
    cb["dif_pin_k"] = cb.mid_kalshi - cb.pinnacle

# --- 3. Cierre y precisión (Brier) ------------------------------------------
cierre = ancho.sort_values("run").groupby("event_key").last()
cierre["y"] = (gan.reindex(cierre.index) == cierre.index.str.split("|").str[2]
               .str.split("-").str[0]).astype(float)
brier = {}
for c in ["mid_kalshi", "mid_polymarket", "consenso", "pinnacle"]:
    if c in cierre:
        x = cierre.dropna(subset=[c])
        brier[c] = (len(x), ((x[c] - x.y) ** 2).mean())

# --- resumen -----------------------------------------------------------------
L = []
p = L.append
p(f"Partidos jugados con las tres fuentes y ganador identificado: {len(jugados)}")
p(f"Capturas previas al partido con Kalshi y Polymarket a la vez: {len(kp)}\n")
p("1) |Kalshi - Polymarket| (puntos de probabilidad, mid vs mid)")
p(kp.absdif.describe(percentiles=[.5, .9, .99]).round(4).to_string())
p(f"   > 2 pp: {(kp.absdif > .02).mean():.1%}   > 5 pp: {(kp.absdif > .05).mean():.1%}")
p(f"   Kalshi más alto en promedio: {kp.dif.mean():+.4f}")
p("\n   Por horas antes del inicio (mediana |dif| y n):")
p(kp.groupby("tramo", observed=True).absdif.agg(["median", "mean", "count"])
  .round(4).to_string())
p("\n   Arbitraje bruto ejecutable (suma de asks < 1, antes de comisiones):")
p(f"   capturas: {(kp.arb < 1).sum()} de {kp.arb.notna().sum()}"
  f"  | partidos con al menos una: {kp[kp.arb < 1].event_key.nunique()}")
if (kp.arb < 1).any():
    p(f"   margen mediano cuando existe: {(1 - kp.arb[kp.arb < 1]).median():.4f}")
p(f"   suma de asks mediana: {kp.arb.median():.4f}")

p("\n2) Mercados de predicción vs consenso de casas (sin margen)")
p(cb[[c for c in cb if c.startswith("dif_")]].abs()
  .describe(percentiles=[.5, .9]).round(4).to_string())

p("\n3) Precisión al cierre (Brier, menor es mejor)")
for k, (n, b) in brier.items():
    p(f"   {k:16s} n={n:3d}  Brier={b:.4f}")

txt = "\n".join(L)
print(txt)
open(os.path.join(out, "resumen.txt"), "w").write(txt)
kp.to_csv(os.path.join(out, "kalshi_vs_poly.csv"), index=False)
cb.to_csv(os.path.join(out, "casas_vs_mercados.csv"), index=False)
cierre.to_csv(os.path.join(out, "cierre.csv"))
