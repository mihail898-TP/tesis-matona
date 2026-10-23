"""Polymarket — exchange on-chain. API pública Gamma, sin credenciales.

Dos cosas verificadas contra la API el 2026-10-02:

1. El filtro tag_slug SOLO funciona en /events. En /markets se ignora y
   devuelve cualquier cosa (política, cripto). Por eso hay que entrar por
   eventos y recorrer los mercados que cuelgan de cada uno.

2. Los precios vienen dentro del propio mercado: bestBid, bestAsk,
   lastTradePrice y outcomePrices. No hace falta llamar al CLOB por cada
   contrato, lo que reduce muchísimo el número de requests.

Se capturan dos clases de mercado:
  - de partido (moneyline, spread, total): núcleo del análisis.
  - de futuros de resolución corta (traspasos, agencia libre): solo los que
    calzan con POLY_FUTURES_KEYWORDS, para la extensión de movimiento
    informado. Los de temporada completa (campeón, novato del año) se dejan
    fuera: no resuelven dentro del semestre.
"""
from __future__ import annotations

import datetime as dt
import json
import re

import common
import config

RE_VS = re.compile(r"(.+?)\s+(?:vs\.?|at|@)\s+(.+?)(?:\s*[\(\|]|$)", re.I)
RE_LINEA = re.compile(r"([+-]?\d+(?:\.\d+)?)")
RE_FECHA = re.compile(r"(20\d{2}-\d{2}-\d{2})")


def _jload(x, default):
    """Gamma entrega listas como texto JSON ('[\"Yes\", \"No\"]')."""
    if isinstance(x, list):
        return x
    try:
        return json.loads(x) if x else default
    except (ValueError, TypeError):
        return default


def _clasificar(texto: str) -> str:
    """OJO: no se usa el slug, porque trae la fecha ('nba-min-ind-2026-10-07')
    y el '-2026' se confunde con una línea de spread."""
    t = (texto or "").lower()
    if "spread" in t or re.search(r"[+-]\d{1,2}(\.\d)?(\s|$)", t):
        return "spread"
    if any(k in t for k in ("total", "over", "under", "o/u")):
        return "total"
    return "moneyline"


def _es_futuro_util(slug: str) -> bool:
    s = (slug or "").lower()
    return any(k in s for k in config.POLY_FUTURES_KEYWORDS)


def _libro(token_id: str) -> dict:
    """Libro de órdenes de un contrato, desde el CLOB.

    Devuelve los N mejores niveles de cada lado y la suma de contratos
    ofrecidos. Es el dato que no aparece en ningún histórico: las velas
    guardan el precio de la última transacción, no cuánto había ofrecido.
    """
    b = common.get_json(f"{config.CLOB_BASE}/book", params={"token_id": token_id})
    if not b:
        return {}
    n = config.POLY_DEPTH_NIVELES

    def niveles(lado, mejor_primero):
        xs = []
        for x in (b.get(lado) or []):
            pr, sz = common.num(x.get("price")), common.num(x.get("size"))
            if pr is not None and sz is not None:
                xs.append((pr, sz))
        xs.sort(key=lambda t: t[0], reverse=mejor_primero)
        return xs[:n]

    bids = niveles("bids", True)    # compras: el mejor es el más alto
    asks = niveles("asks", False)   # ventas: el mejor es el más bajo
    return {
        "depth_bid": round(sum(s for _, s in bids), 2) if bids else None,
        "depth_ask": round(sum(s for _, s in asks), 2) if asks else None,
        "niveles": {"bids": bids, "asks": asks},
    }


def _principales(markets: list) -> list:
    """Deja todos los moneyline y, de spread y total, solo la línea principal:
    la más cercana a 50/50. Polymarket publica decenas de líneas alternativas
    por partido (over 210.5, 211.5, 212.5...), que eran el 80% de las filas
    y llenaban la base en un día."""
    mejores: dict[str, tuple] = {}
    salida = []
    for m in markets:
        etiqueta = " ".join(filter(None, [m.get("groupItemTitle"), m.get("question")]))
        tipo = _clasificar(etiqueta)
        if tipo == "moneyline":
            salida.append(m)
            continue
        precios = _jload(m.get("outcomePrices"), [])
        p = common.num(precios[0]) if precios else None
        if p is None:
            continue
        dist = abs(p - 0.5)
        if tipo not in mejores or dist < mejores[tipo][0]:
            mejores[tipo] = (dist, m)
    return salida + [m for _, m in mejores.values()]


def _horas_hasta(ini, ahora) -> float | None:
    try:
        d = dt.datetime.fromisoformat(str(ini).replace("Z", "+00:00"))
        if d.tzinfo is None:
            d = d.replace(tzinfo=dt.timezone.utc)
        return (d - ahora).total_seconds() / 3600
    except (TypeError, ValueError):
        return None


def fetch(storage_ts: str) -> list[dict]:
    ahora = dt.datetime.fromisoformat(storage_ts)
    # Los partidos lejanos y los futuros cambian poco: se capturan solo en la
    # corrida que cae en el primer cuarto de hora de cada bloque de N horas.
    horaria = (ahora.minute < 15 and ahora.hour % config.LEJOS_CADA_HORAS == 0)
    n_lejos = 0
    eventos = []
    for pagina in range(config.POLY_PAGINAS):
        d = common.get_json(f"{config.GAMMA_BASE}/events", params={
            "tag_slug": config.POLY_TAG,
            "closed": "false", "active": "true",
            "limit": 100, "offset": pagina * 100,
            "order": "startDate", "ascending": "true",
        })
        lote = d if isinstance(d, list) else (d or {}).get("data", [])
        if not lote:
            break
        eventos.extend(lote)

    filas = []
    n_part = n_fut = 0
    origenes: dict[str, int] = {}
    muestra: list = []
    presupuesto = config.POLY_DEPTH_MAX if config.POLY_DEPTH else 0
    n_libros = 0
    for ev in eventos:
        ev_slug = ev.get("slug") or ""
        ev_title = ev.get("title") or ""
        mm = RE_VS.search(ev_title)
        es_partido = bool(mm)

        if not es_partido and not _es_futuro_util(ev_slug):
            continue
        if not es_partido and not horaria:
            continue

        if es_partido:
            home, away = mm.group(2).strip(), mm.group(1).strip()
            # startDate del evento es cuándo se ABRIÓ el mercado, que en los
            # partidos de la NBA ocurre una semana antes. Para la fecha real
            # del partido el orden de preferencia es:
            #   gameStartTime de algún mercado > endDate (cierre = fin del
            #   partido) > fecha incrustada en el slug > startDate
            ini = fecha = None
            origen = "startDate"
            gst = next((m.get("gameStartTime") for m in (ev.get("markets") or [])
                        if m.get("gameStartTime")), None)
            fin = ev.get("endDate") or ev.get("endDateIso") or next(
                (m.get("endDate") for m in (ev.get("markets") or [])
                 if m.get("endDate")), None)
            g = RE_FECHA.search(ev_slug)
            if gst:
                ini, fecha, origen = gst, common.fecha_et(gst), "gameStartTime"
            elif fin:
                ini, fecha, origen = fin, common.fecha_et(fin), "endDate"
            elif g:
                fecha, origen = g.group(1), "slug"
                ini = ev.get("startDate")
            else:
                ini, fecha = ev.get("startDate"), common.fecha_et(ev.get("startDate"))
            origenes[origen] = origenes.get(origen, 0) + 1
            if len(muestra) < 3:
                muestra.append((ev_slug[:40], origen, fecha,
                                str(ev.get("startDate"))[:10],
                                str(fin)[:10], str(gst)[:10]))
            # Cerca = empieza dentro de CERCA_HORAS o empezó hace poco (en
            # juego). Sin hora legible se trata como cercano: mejor guardar
            # de más que perder un partido.
            h = _horas_hasta(ini, ahora)
            cerca = h is None or -6 <= h <= config.CERCA_HORAS
            if not cerca and not horaria:
                n_lejos += 1
                continue
            ekey = common.event_key(config.LEAGUE, ini, home, away, fecha=fecha)
            n_part += 1
        else:
            home = away = None
            ini = ev.get("endDate")
            ekey = f"futures|{ev_slug}"
            n_fut += 1

        mercados = ev.get("markets") or []
        if es_partido:
            mercados = _principales(mercados)
        for m in mercados:
            # El slug queda fuera a propósito (ver _clasificar).
            etiqueta = " ".join(filter(None, [
                m.get("groupItemTitle"), m.get("question")]))
            tipo = _clasificar(etiqueta) if es_partido else "futures"
            linea = None
            if tipo in ("spread", "total"):
                g = RE_LINEA.search(m.get("groupItemTitle") or
                                    m.get("question") or "")
                linea = float(g.group(1)) if g else None

            nombres = _jload(m.get("outcomes"), [])
            precios = _jload(m.get("outcomePrices"), [])
            bid = common.num(m.get("bestBid"))
            ask = common.num(m.get("bestAsk"))
            ini_m = m.get("gameStartTime") or ini

            # Profundidad: una consulta por mercado, solo en partidos y hasta
            # agotar el presupuesto. El libro del token NO es el espejo del
            # YES, así que con uno basta.
            lb = {}
            if es_partido and cerca and presupuesto > 0:
                toks = _jload(m.get("clobTokenIds"), [])
                if toks:
                    lb = _libro(toks[0])
                    presupuesto -= 1
                    if lb:
                        n_libros += 1

            for i, nombre in enumerate(nombres):
                p = common.num(precios[i]) if i < len(precios) else None
                if p is None:
                    continue
                # En spread, total y futuros los resultados se llaman "Yes" y
                # "No", así que sin el groupItemTitle no se sabe a qué lado
                # corresponde el precio.
                if tipo == "moneyline":
                    etiq_out = nombre
                else:
                    etiq_out = " ".join(filter(None, [
                        m.get("groupItemTitle") or m.get("question"), nombre]))
                # bestBid/bestAsk se publican para el primer resultado (YES).
                es_primero = i == 0
                filas.append({
                    "captured_at": storage_ts,
                    "source": "polymarket",
                    "book": None,
                    "league": config.LEAGUE,
                    "market_type": tipo,
                    "line": linea,
                    "event_key": ekey,
                    "source_event_id": m.get("conditionId") or m.get("id"),
                    "commence_time": ini_m,
                    "home_team": home,
                    "away_team": away,
                    "outcome": etiq_out,
                    "price_decimal": None,
                    "prob_raw": p,
                    "best_bid": bid if es_primero else None,
                    "best_ask": ask if es_primero else None,
                    "mid": (bid + ask) / 2 if (es_primero and bid and ask) else p,
                    "depth_bid": lb.get("depth_bid") if es_primero else None,
                    "depth_ask": lb.get("depth_ask") if es_primero else None,
                    # volumen REAL: es lo que no entrega el bookmaker y lo que
                    # permite validar el proxy de movimiento de cuota.
                    "volume": common.num(m.get("volumeNum")),
                    "raw": {"question": m.get("question"),
                            "slug": m.get("slug"),
                            "vol24h": m.get("volume24hr"),
                            "liquidity": m.get("liquidityNum"),
                            "spread": m.get("spread"),
                            "last": m.get("lastTradePrice"),
                            "book": lb.get("niveles") if es_primero else None},
                })

    print(f"  [polymarket] {len(filas)} filas "
          f"({n_part} partidos, {n_fut} futuros, {len(eventos)} eventos, "
          f"{n_libros} libros, {n_lejos} lejanos omitidos"
          f"{', corrida completa' if horaria else ''})")
    if origenes:
        print("    fecha tomada de: " +
              ", ".join(f"{k}={v}" for k, v in origenes.items()))
        for sl, org, fe, sd, fi, gs in muestra:
            print(f"      {sl:42} usa={org:14} -> {fe} "
                  f"(start={sd} end={fi} game={gs})")
    return filas
