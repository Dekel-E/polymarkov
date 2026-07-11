-- Strategy Desk: GUI-controlled settings that the scheduled jobs obey.
create table if not exists agent_settings (
  key text primary key,
  value jsonb not null,
  updated_at timestamptz default now()
);

-- Attribute every paper trade to the strategy that opened it.
alter table positions add column if not exists strategy text default 'manual';

-- Copy trading: remember which whale positions were already mirrored.
create table if not exists mirrored_trades (
  id uuid primary key default gen_random_uuid(),
  wallet text not null,
  market_id text not null,
  outcome text not null,
  position_id uuid,
  created_at timestamptz default now(),
  unique (wallet, market_id, outcome)
);
