-- Market making: simulated resting limit orders awaiting fill settlement.
create table if not exists mm_quotes (
  id uuid primary key default gen_random_uuid(),
  market_id text not null,
  yes_token_id text not null,
  category text default 'other',
  bid numeric not null,
  ask numeric not null,
  size_usd numeric not null,
  status text not null default 'pending' check (status in ('pending', 'settled')),
  fills text, -- e.g. 'bid', 'ask', 'bid+ask'
  placed_at timestamptz default now(),
  settled_at timestamptz
);

create index if not exists mm_quotes_status_idx on mm_quotes (status);

-- Correlation graph: logical relations between markets, LLM-classified once,
-- then checked mechanically for pricing violations on every arb scan.
create table if not exists market_relations (
  id uuid primary key default gen_random_uuid(),
  relation text not null check (relation in ('implies', 'excludes')),
  a_slug text not null, -- implies: A -> B (P(A) must be <= P(B))
  b_slug text not null,
  a_question text default '',
  b_question text default '',
  a_yes_token text default '',
  a_no_token text default '',
  b_yes_token text default '',
  b_no_token text default '',
  confidence numeric default 0,
  rationale text default '',
  created_at timestamptz default now(),
  unique (relation, a_slug, b_slug)
);
