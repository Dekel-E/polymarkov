-- Watchlist: markets a logged-in user follows; the refresh job re-analyzes
-- them on schedule.
create table if not exists watchlist (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null,
  market_id text not null,
  created_at timestamptz default now(),
  unique (user_id, market_id)
);

create index if not exists watchlist_market_idx on watchlist (market_id);

-- Verdict history / report card need runs keyed by market.
alter table runs add column if not exists market_id text;
create index if not exists runs_market_idx on runs (market_id);

-- Equity curve needs to know WHEN a position settled.
alter table positions add column if not exists resolved_at timestamptz;
