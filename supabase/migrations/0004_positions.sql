create table if not exists positions (
  id uuid primary key default gen_random_uuid(),
  market_id text not null,
  side text not null check (side in ('BUY_YES', 'BUY_NO')),
  entry_price numeric not null,
  size_usd numeric not null,
  fee_paid numeric default 0,
  slippage_bps numeric default 0,
  fair_prob_at_entry numeric,
  opened_at timestamptz default now(),
  status text default 'open' check (status in ('open', 'resolved')),
  resolved_outcome text,
  pnl numeric
);

create index if not exists positions_status_idx on positions (status);
