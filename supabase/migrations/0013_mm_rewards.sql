-- Market making: track the mid at placement (drift requotes) and the
-- simulated Polymarket liquidity-rewards score earned while resting.
alter table mm_quotes add column if not exists mid_at_placement numeric;
alter table mm_quotes add column if not exists reward_score numeric default 0;
