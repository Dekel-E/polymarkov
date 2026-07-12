-- Autonomy: the agent's own to-do list, filled by the sentinel job and
-- worked highest-priority-first by the agenda worker.
create table if not exists agenda (
  id uuid primary key default gen_random_uuid(),
  market_id text not null,
  reason text not null,
  priority numeric not null default 0,
  status text not null default 'pending' check (status in ('pending', 'done', 'skipped')),
  outcome text,
  created_at timestamptz default now(),
  handled_at timestamptz
);

-- one pending item per market at a time
create unique index if not exists agenda_pending_uidx on agenda (market_id) where status = 'pending';
create index if not exists agenda_status_idx on agenda (status, priority desc);

-- Morning briefings the agent writes about its own book.
create table if not exists briefings (
  id uuid primary key default gen_random_uuid(),
  content text not null,
  facts jsonb,
  created_at timestamptz default now()
);
