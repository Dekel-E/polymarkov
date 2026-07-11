-- Cached dossiers: one fresh analysis per market, replacing 7 LLM calls
-- for repeat requests within the TTL (checked in code, not here).
create table if not exists intel_cache (
  market_id text primary key,
  payload jsonb not null,
  created_at timestamptz default now()
);
