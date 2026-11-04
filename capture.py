"""Punto de entrada. Una corrida = una captura de las tres fuentes.

    python capture.py            # captura y guarda
    python capture.py --dry-run  # captura y solo muestra, no escribe
"""
from __future__ import annotations

import sys
import traceback

import common
import storage as st
from sources import kalshi, odds_api, polymarket

FUENTES = [
    ("odds_api", odds_api.fetch),
    ("kalshi", kalshi.fetch),
    ("polymarket", polymarket.fetch),
]


def completar_inicio(filas: list[dict]) -> None:
    """Kalshi no trae la hora de inicio. Se toma la más temprana que reporten
    las otras fuentes para el mismo partido en esta corrida (Odds API suele ir
    unos minutos atrasada respecto de Polymarket). Si ninguna lo trae, queda
    vacía: mejor nula que equivocada."""
    inicio: dict[str, str] = {}
    for f in filas:
        ct, ek = f.get("commence_time"), f["event_key"]
        if ct and f["source"] != "kalshi" and not ek.startswith("futures|"):
            if ek not in inicio or common.iso_cmp(ct) < common.iso_cmp(inicio[ek]):
                inicio[ek] = ct
    k = [f for f in filas if f["source"] == "kalshi"]
    for f in k:
        if not f.get("commence_time"):
            f["commence_time"] = inicio.get(f["event_key"])
    if k:
        n = sum(1 for f in k if f["commence_time"])
        print(f"  [kalshi] hora de inicio completada en {n} de {len(k)} filas")


def main() -> int:
    dry = "--dry-run" in sys.argv
    ts = common.iso(common.now_utc())
    print(f"=== captura {ts} ===")

    filas, errores = [], []
    for nombre, fn in FUENTES:
        try:
            filas.extend(fn(ts))
        except Exception as e:  # noqa: BLE001
            # Una fuente caída no debe tumbar la captura de las otras.
            errores.append(f"{nombre}: {e}")
            traceback.print_exc()

    completar_inicio(filas)

    # Cuántos partidos quedaron con más de una fuente: es el indicador de
    # salud del emparejamiento. Si es 0 de forma persistente, los alias de
    # equipo están mal, no es que no haya mercados espejados.
    por_evento: dict[str, set] = {}
    tipos: dict[str, int] = {}
    for f in filas:
        if not f["event_key"].startswith("futures|"):
            por_evento.setdefault(f["event_key"], set()).add(f["source"])
        tipos[f.get("market_type") or "?"] = tipos.get(f.get("market_type") or "?", 0) + 1
    emparejados = sum(1 for v in por_evento.values() if len(v) > 1)
    print(f"  partidos: {len(por_evento)} | con 2+ fuentes: {emparejados}")
    print("  por tipo: " + ", ".join(f"{k}={v}" for k, v in sorted(tipos.items())))

    if dry:
        # Llaves por fuente, para ver a simple vista por qué no se cruzan.
        porf: dict[str, list] = {}
        for f in filas:
            if not f["event_key"].startswith("futures|"):
                porf.setdefault(f["source"], [])
                if f["event_key"] not in porf[f["source"]]:
                    porf[f["source"]].append(f["event_key"])
        for src, ks in porf.items():
            print(f"    -- {src}: {len(ks)} partidos")
            for k in sorted(ks)[:6]:
                print("       ", k)
        for ek, src in list(por_evento.items())[:6]:
            if len(src) > 1:
                print("    EMPAREJADO", ek, sorted(src))
        for f in filas[:8]:
            print("   ", f["source"], f["market_type"], f["event_key"],
                  f["outcome"],
                  round(f["prob_raw"], 4) if f["prob_raw"] else None)
        print(f"  [dry-run] {len(filas)} filas NO guardadas")
        return 0

    s = st.Storage()
    n = s.guardar(filas)
    s.log_run(ok=not errores, n=n, detalle="; ".join(errores))
    print(f"  guardadas {n} filas" + (f" | errores: {errores}" if errores else ""))
    # Falla la corrida si no entró nada: así GitHub Actions te avisa por correo.
    return 1 if n == 0 else 0


if __name__ == "__main__":
    sys.exit(main())
