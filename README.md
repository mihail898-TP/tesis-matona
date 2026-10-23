# Capturador de precios — tesis mercados de apuestas

Captura cada 15 minutos los precios de un mismo partido en tres fuentes y los
guarda con marca temporal. Los precios intradiarios **no son reconstruibles
hacia atrás**: lo que no se capture hoy se pierde para siempre.

| Fuente | Qué entrega | Credenciales |
|---|---|---|
| The Odds API | cuotas de casas de apuestas (Pinnacle, DraftKings…) | API key |
| Kalshi | precios y volumen del exchange regulado | ninguna (lectura pública) |
| Polymarket | precios, libro de órdenes y volumen real | ninguna (lectura pública) |

## Puesta en marcha (unos 30 minutos)

**1. Cuentas**

- The Odds API: registrarse en the-odds-api.com y obtener la key.
- Supabase: crear proyecto gratis, ir al SQL Editor y ejecutar `schema.sql`.
  La cadena de conexión está en Project Settings → Database.

**2. Prueba local**

```bash
pip install -r requirements.txt
cp .env.example .env          # completar ODDS_API_KEY y DATABASE_URL
set -a && source .env && set +a
python capture.py --dry-run   # no escribe nada, solo muestra
```

Lo único que importa en esa salida es la línea `partidos: N | con 2+ fuentes: M`.
Si **M es 0 de forma persistente**, el problema está en los alias de equipo de
`common.py`, no en que falten mercados espejados. Ese es el ajuste manual que
hay que hacer antes de dejarlo corriendo.

**3. Automatización**

Subir el repo a GitHub y en Settings → Secrets and variables → Actions cargar
`ODDS_API_KEY` y `DATABASE_URL`. El workflow corre solo cada 15 minutos.

Primero dispararlo a mano desde la pestaña Actions y revisar el log. Dejarlo
corriendo sin verificar la primera corrida es la forma más común de perder
semanas de datos.

## Qué mercados se capturan

| Tipo | Fuentes | Uso en la tesis |
|---|---|---|
| `moneyline` | las tres | núcleo: calibración y sesgo favorito-outsider |
| `spread` | Odds API, Polymarket | ley de un precio (más contratos emparejables) |
| `total` | Odds API, Polymarket | ley de un precio |
| `futures` | Polymarket | extensión de movimiento informado previo al anuncio |

De los futuros solo entran los que resuelven dentro del semestre y tienen hora
de anuncio conocida: traspasos, agencia libre, salidas de jugadores. Los de
temporada completa (campeón, novato del año) quedan fuera porque no alcanzan a
resolverse y sin resultado observado no hay calibración posible. El filtro está
en `POLY_FUTURES_KEYWORDS`.

## Consumo de créditos de The Odds API

Se hacen dos llamadas por captura: línea de dinero en `us,eu` (2 créditos, la
región europea es la que trae Pinnacle) y spread más total en `us` (2 créditos).
Son 4 por corrida, unos 384 al día y 11.500 al mes, que cabe con holgura en el
plan de 20.000.

El tier gratuito son 500 créditos al mes: alcanza para menos de dos días. Sirve
para probar, no para la temporada. Para gastar menos, dejar
`ODDS_EXTRA_MARKETS` vacío y quedarse solo con línea de dinero.

## Qué se guarda

Una fila por **observación**: fuente, partido, lado, precio e instante. El
colapso a una fila por partido se hace recién en el análisis.

La columna clave es `event_key`: `liga|fecha|equipo-equipo`, con los equipos en
orden alfabético para no depender de que cada fuente respete la convención
local/visita. Es lo que permite cruzar las tres fuentes.

`prob_raw` es la probabilidad implícita **sin normalizar**. En las casas de
apuestas los dos lados suman más de 1; ese exceso es el margen y se remueve en
el análisis, no en la captura. Guardar el dato crudo permite después probar
distintos métodos de normalización y reportar la sensibilidad.

## Salud del proceso

- `runs` registra cada corrida. Revisarla una vez por semana.
- `capture.py` termina con código 1 si no entró ninguna fila, de modo que
  GitHub Actions marque la corrida como fallida y mande correo.
- Respaldar la base fuera de Supabase cada cierto tiempo. Perder tres semanas
  de capturas por un fallo silencioso es el peor escenario.

## Lo que falta (fase de análisis, semana 8 en adelante)

- Llenar `results` con los resultados de los partidos.
- Llenar `announcements` con la hora oficial de los partes de lesionados: es la
  etiqueta temporal del análisis de movimiento informado previo al anuncio.
- Normalización del margen (proporcional y método de Shin).
- Calibración, sesgo favorito-outsider y desviaciones entre plataformas.
