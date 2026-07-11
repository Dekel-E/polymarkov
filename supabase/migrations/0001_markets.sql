create table if not exists markets (
  id text primary key,
  slug text not null,
  question text not null,
  category text default 'other',
  end_date timestamptz,
  resolution_text text,
  yes_token_id text,
  last_mid numeric,
  volume24h numeric,
  active bool default true,
  indexed_at timestamptz default now()
);

create index if not exists markets_slug_idx on markets (slug);
create index if not exists markets_volume_idx on markets (volume24h desc);
