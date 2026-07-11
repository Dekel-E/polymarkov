create table if not exists precedents (
  market_id text primary key,
  question text not null,
  category text default 'other',
  resolution_text text,
  outcome text check (outcome in ('YES', 'NO')),
  final_mid_7d_before numeric,
  resolved_at timestamptz
);

create index if not exists precedents_category_idx on precedents (category);
