create table if not exists articles (
  id uuid primary key default gen_random_uuid(),
  url text unique not null,
  title text,
  domain text,
  published_at timestamptz,
  tone numeric,
  entities text[],
  fetched_text text,
  embedded bool default false
);

create index if not exists articles_published_idx on articles (published_at desc);
