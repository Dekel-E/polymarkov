-- Positions can belong to a logged-in user (Supabase Auth). NULL = the
-- agent's own book (autonomous runs / anonymous GUI trades).
alter table positions add column if not exists user_id uuid;

create index if not exists positions_user_idx on positions (user_id);
