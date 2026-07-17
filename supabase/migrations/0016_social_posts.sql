-- Indexed social chatter (RedditIndexer job): posts scraped per tracked
-- market, tagged with market slugs, embedded into the Pinecone `social`
-- namespace on the same pass. SocialScanner and MarketChat read these as a
-- warm cache alongside live scrapes.
create table if not exists social_posts (
  id uuid primary key default gen_random_uuid(),
  url text not null unique,
  text text not null,
  source text not null default 'reddit',
  subreddit text default '',
  score integer default 0,
  posted_at timestamptz,
  entities jsonb not null default '[]',
  embedded boolean not null default false,
  indexed_at timestamptz not null default now()
);

create index if not exists social_posts_entities_idx on social_posts using gin (entities);
create index if not exists social_posts_posted_idx on social_posts (posted_at desc);
create index if not exists social_posts_embedded_idx on social_posts (embedded) where not embedded;
