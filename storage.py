"""Persistencia. Postgres si hay DATABASE_URL; si no, CSV diario en ./data/.

Una fila = una observación de un lado de un partido en una fuente, en un
instante. El colapso a una fila por partido se hace después, en el análisis.
"""
from __future__ import annotations

import csv
import json
import os
import pathlib

import config

CAMPOS = [
    "captured_at",      # UTC, momento exacto de la captura
    "source",           # odds_api | kalshi | polymarket
    "book",             # casa de apuestas (solo odds_api)
    "league",
    "market_type",      # moneyline | spread | total | futures
    "line",             # línea del spread o total (null en moneyline)
    "event_key",        # llave canónica para emparejar entre fuentes
    "source_event_id",  # id interno de la fuente
    "commence_time",    # inicio del partido, UTC
    "home_team",
    "away_team",
    "outcome",          # equipo al que corresponde el precio
    "price_decimal",    # cuota decimal (odds_api)
    "prob_raw",         # probabilidad implícita SIN normalizar margen
    "best_bid",
    "best_ask",
    "mid",
    "depth_bid",        # contratos ofrecidos en los N mejores niveles de compra
    "depth_ask",        # idem del lado de venta
    "volume",
    "raw",              # json original, por si cambia el esquema de la fuente
]


class Storage:
    def __init__(self):
        self.conn = None
        if config.DATABASE_URL:
            try:
                import psycopg2  # noqa: PLC0415
                self.conn = psycopg2.connect(config.DATABASE_URL)
                self.conn.autocommit = True
                print("  [storage] Postgres conectado")
            except Exception as e:  # noqa: BLE001
                print(f"  [storage] Postgres falló ({e}); se usa CSV")
        if self.conn is None:
            pathlib.Path(config.CSV_DIR).mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    def guardar(self, filas: list[dict]) -> int:
        if not filas:
            return 0
        for f in filas:
            if isinstance(f.get("raw"), (dict, list)):
                f["raw"] = json.dumps(f["raw"], ensure_ascii=False)
        return self._pg(filas) if self.conn else self._csv(filas)

    def _pg(self, filas):
        cols = ",".join(CAMPOS)
        ph = ",".join(["%s"] * len(CAMPOS))
        sql = f"insert into captures ({cols}) values ({ph})"
        datos = [tuple(f.get(c) for c in CAMPOS) for f in filas]
        with self.conn.cursor() as cur:
            cur.executemany(sql, datos)
        return len(datos)

    def _csv(self, filas):
        dia = filas[0]["captured_at"][:10]
        ruta = os.path.join(config.CSV_DIR, f"captures_{dia}.csv")
        nuevo = not os.path.exists(ruta)
        with open(ruta, "a", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=CAMPOS, extrasaction="ignore")
            if nuevo:
                w.writeheader()
            w.writerows(filas)
        return len(filas)

    # ------------------------------------------------------------------
    def log_run(self, ok: bool, n: int, detalle: str = ""):
        """Registro de cada corrida: sin esto, un fallo silencioso pasa
        semanas sin que te enteres."""
        if not self.conn:
            return
        try:
            with self.conn.cursor() as cur:
                cur.execute(
                    "insert into runs (ok, n_rows, detail) values (%s,%s,%s)",
                    (ok, n, detalle[:2000]),
                )
        except Exception:  # noqa: BLE001, S110
            pass
