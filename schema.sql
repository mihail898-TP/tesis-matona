-- Esquema de la base de capturas.
-- Ejecutar una vez en Supabase (SQL Editor) o en el Postgres que uses.

create table if not exists captures (
    id              bigserial primary key,
    captured_at     timestamptz not null,
    source          text        not null,
    book            text,
    league          text,
    market_type     text,
    line            double precision,
    event_key       text        not null,
    source_event_id text,
    commence_time   timestamptz,
    home_team       text,
    away_team       text,
    outcome         text,
    price_decimal   double precision,
    prob_raw        double precision,
    best_bid        double precision,
    best_ask        double precision,
    mid             double precision,
    depth_bid       double precision,
    depth_ask       double precision,
    volume          double precision,
    raw             jsonb,
    inserted_at     timestamptz default now()
);

-- El análisis siempre entra por partido y por tiempo.
create index if not exists ix_captures_event on captures (event_key, captured_at);
create index if not exists ix_captures_src   on captures (source, captured_at);

-- Evita duplicados si una corrida se repite (el cron de Actions puede
-- dispararse dos veces en casos raros).
create unique index if not exists ux_captures_dedup
    on captures (captured_at, source, coalesce(book,''), event_key,
                 coalesce(market_type,''), coalesce(line,-999),
                 coalesce(outcome,''));

-- Bitácora de corridas: sin esto un fallo silencioso pasa semanas inadvertido.
create table if not exists runs (
    id        bigserial primary key,
    ran_at    timestamptz default now(),
    ok        boolean,
    n_rows    integer,
    detail    text
);

-- Resultados de los partidos. Se llena después, una vez jugados.
create table if not exists results (
    event_key   text primary key,
    league      text,
    played_at   timestamptz,
    home_team   text,
    away_team   text,
    home_score  integer,
    away_score  integer,
    winner      text
);

-- Anuncios con hora oficial (partes de lesionados, alineaciones).
-- Es la etiqueta temporal para el análisis de movimiento informado previo.
create table if not exists announcements (
    id          bigserial primary key,
    event_key   text,
    announced_at timestamptz not null,
    kind        text,
    detail      text
);
