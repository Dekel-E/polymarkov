create table if not exists runs (
  id uuid primary key default gen_random_uuid(),
  prompt text,
  verdict text,
  fair_prob numeric,
  mid_at_run numeric,
  tokens_in int default 0,
  tokens_out int default 0,
  latency_ms int,
  created_at timestamptz default now()
);
