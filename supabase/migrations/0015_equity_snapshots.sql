-- Daily equity snapshots: one row per UTC day, upserted by jobs/manage_risk
-- (every 4h — the last write of the day wins). Gives the portfolio page a
-- real equity curve instead of a client-side reconstruction from resolved
-- trades only.
create table if not exists equity_snapshots (
  day date primary key,
  equity_usd double precision not null,
  balance_usd double precision not null,
  open_exposure_usd double precision not null default 0,
  unrealized_pnl_usd double precision not null default 0,
  realized_pnl_usd double precision not null default 0,
  open_positions integer not null default 0,
  created_at timestamptz not null default now()
);

create index if not exists equity_snapshots_day_idx on equity_snapshots (day desc);
