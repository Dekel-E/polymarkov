-- Terminal-grade position management: per-position stop/take price levels
-- (override the global % rules; enforced by the risk manager).
alter table positions add column if not exists sl_price numeric;
alter table positions add column if not exists tp_price numeric;
