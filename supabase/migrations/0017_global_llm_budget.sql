-- One atomic quota shared by every API instance and background worker.
-- A reservation is made before each provider request (including retries and
-- embedding batches), so concurrent serverless functions cannot overspend it.
create table if not exists llm_budget_daily (
  day date primary key,
  request_count integer not null default 0 check (request_count >= 0),
  chat_requests integer not null default 0 check (chat_requests >= 0),
  embedding_requests integer not null default 0 check (embedding_requests >= 0),
  tokens_in bigint not null default 0 check (tokens_in >= 0),
  tokens_out bigint not null default 0 check (tokens_out >= 0),
  failed_requests integer not null default 0 check (failed_requests >= 0),
  updated_at timestamptz not null default now()
);

alter table llm_budget_daily enable row level security;

create or replace function reserve_llm_budget(p_kind text, p_daily_limit integer)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
  v_day date := (now() at time zone 'utc')::date;
  v_count integer;
begin
  if p_kind not in ('chat', 'embedding') then
    raise exception 'invalid LLM request kind';
  end if;
  if p_daily_limit < 1 then
    raise exception 'daily LLM request limit must be positive';
  end if;

  insert into llm_budget_daily (
    day, request_count, chat_requests, embedding_requests, updated_at
  ) values (
    v_day,
    1,
    case when p_kind = 'chat' then 1 else 0 end,
    case when p_kind = 'embedding' then 1 else 0 end,
    now()
  )
  on conflict (day) do update
  set request_count = llm_budget_daily.request_count + 1,
      chat_requests = llm_budget_daily.chat_requests
        + case when p_kind = 'chat' then 1 else 0 end,
      embedding_requests = llm_budget_daily.embedding_requests
        + case when p_kind = 'embedding' then 1 else 0 end,
      updated_at = now()
  where llm_budget_daily.request_count < p_daily_limit
  returning request_count into v_count;

  if v_count is null then
    select request_count into v_count
    from llm_budget_daily
    where day = v_day;
    return jsonb_build_object(
      'allowed', false,
      'day', v_day,
      'used', coalesce(v_count, p_daily_limit),
      'limit', p_daily_limit
    );
  end if;

  return jsonb_build_object(
    'allowed', true,
    'day', v_day,
    'used', v_count,
    'limit', p_daily_limit
  );
end;
$$;

create or replace function record_llm_usage(
  p_kind text,
  p_tokens_in bigint default 0,
  p_tokens_out bigint default 0,
  p_failed boolean default false
)
returns void
language plpgsql
security definer
set search_path = public
as $$
begin
  if p_kind not in ('chat', 'embedding') then
    raise exception 'invalid LLM request kind';
  end if;

  update llm_budget_daily
  set tokens_in = tokens_in + greatest(coalesce(p_tokens_in, 0), 0),
      tokens_out = tokens_out + greatest(coalesce(p_tokens_out, 0), 0),
      failed_requests = failed_requests + case when p_failed then 1 else 0 end,
      updated_at = now()
  where day = (now() at time zone 'utc')::date;
end;
$$;

create or replace function get_llm_budget_status(p_daily_limit integer)
returns jsonb
language sql
stable
security definer
set search_path = public
as $$
  select jsonb_build_object(
    'day', (now() at time zone 'utc')::date,
    'used', coalesce(b.request_count, 0),
    'remaining', greatest(p_daily_limit - coalesce(b.request_count, 0), 0),
    'limit', p_daily_limit,
    'chat_requests', coalesce(b.chat_requests, 0),
    'embedding_requests', coalesce(b.embedding_requests, 0),
    'tokens_in', coalesce(b.tokens_in, 0),
    'tokens_out', coalesce(b.tokens_out, 0),
    'failed_requests', coalesce(b.failed_requests, 0)
  )
  from (select 1) seed
  left join llm_budget_daily b
    on b.day = (now() at time zone 'utc')::date;
$$;

-- Health is one cheap database round-trip and proves that this migration is
-- present. The application adds configuration checks around this result.
create or replace function deployment_health()
returns jsonb
language sql
stable
security definer
set search_path = public
as $$
  select jsonb_build_object(
    'database', 'ok',
    'schema_version', '0017',
    'checked_at', now()
  );
$$;

revoke all on table llm_budget_daily from public, anon, authenticated;
revoke all on function reserve_llm_budget(text, integer) from public, anon, authenticated;
revoke all on function record_llm_usage(text, bigint, bigint, boolean) from public, anon, authenticated;
revoke all on function get_llm_budget_status(integer) from public, anon, authenticated;
revoke all on function deployment_health() from public, anon, authenticated;

grant select on table llm_budget_daily to service_role;
grant execute on function reserve_llm_budget(text, integer) to service_role;
grant execute on function record_llm_usage(text, bigint, bigint, boolean) to service_role;
grant execute on function get_llm_budget_status(integer) to service_role;
grant execute on function deployment_health() to service_role;
