-- Smart Money League: wallets a logged-in user follows.
create table if not exists followed_wallets (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null,
  wallet text not null,
  label text default '',
  created_at timestamptz default now(),
  unique (user_id, wallet)
);

create index if not exists followed_wallets_user_idx on followed_wallets (user_id);
