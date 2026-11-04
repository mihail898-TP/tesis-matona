-- Corrección de datos históricos (noviembre 2026).
-- Correr en Supabase > SQL Editor. Cada bloque es independiente.

-- 1) Hora de inicio en las filas de Kalshi.
--    Kalshi guardaba el cierre esperado del contrato (~2h50 después del
--    salto). Se reemplaza por la hora más temprana que reportan Polymarket u
--    Odds API para el mismo partido. La original se conserva en raw.
--    Revisar primero cuántas filas cambia:
select count(*) as filas_a_corregir
from captures k
where k.source = 'kalshi'
  and exists (select 1 from captures o
              where o.event_key = k.event_key and o.source <> 'kalshi'
                and o.commence_time is not null);

update captures k
set commence_time = o.inicio,
    raw = coalesce(k.raw, '{}'::jsonb)
          || jsonb_build_object('expiracion_esperada', k.commence_time)
from (select event_key, min(commence_time) as inicio
      from captures
      where source <> 'kalshi' and commence_time is not null
        and event_key not like 'futures|%'
      group by event_key) o
where k.source = 'kalshi'
  and k.event_key = o.event_key
  and k.commence_time is distinct from o.inicio
  and not (k.raw ? 'expiracion_esperada');   -- no tocar filas ya corregidas

-- 2) (Opcional) Filas basura de "Exact Margin" que se colaron como moneyline
--    el 23-oct, antes del filtro. Son ~152. El análisis ya las ignora, así que
--    borrarlas solo ordena la base. Revisar antes:
select count(*), min(captured_at), max(captured_at)
from captures
where source = 'polymarket' and event_key like '%margin%';

-- delete from captures
-- where source = 'polymarket' and event_key like '%margin%';
