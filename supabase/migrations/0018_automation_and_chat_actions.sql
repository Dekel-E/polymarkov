-- GitHub Actions heartbeats for the Strategy Desk and durable, single-use
-- confirmations for state-changing DeskChat actions.

create table if not exists automation_heartbeats (
  workflow text not null,
  job text not null,
  run_id text not null,
  run_attempt integer not null default 1,
  event text not null default 'unknown',
  status text not null check (status in ('running', 'success', 'failure', 'cancelled', 'skipped')),
  started_at timestamptz,
  finished_at timestamptz,
  updated_at timestamptz not null default now(),
  run_url text,
  commit_sha text,
  primary key (workflow, job)
);

create index if not exists automation_heartbeats_updated_idx
  on automation_heartbeats (updated_at desc);

create table if not exists chat_actions (
  token uuid primary key default gen_random_uuid(),
  action_type text not null check (action_type in ('trade', 'close')),
  payload jsonb not null,
  status text not null default 'pending'
    check (status in ('pending', 'processing', 'completed', 'cancelled', 'failed')),
  result jsonb,
  created_at timestamptz not null default now(),
  expires_at timestamptz not null default (now() + interval '10 minutes'),
  claimed_at timestamptz,
  completed_at timestamptz
);

create index if not exists chat_actions_expiry_idx
  on chat_actions (expires_at);

alter table automation_heartbeats enable row level security;
alter table chat_actions enable row level security;

-- Serialize confirmation attempts. Exactly one caller can move a pending
-- action to processing; later retries receive the stored state/result.
create or replace function claim_chat_action(p_token uuid)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
  v_action chat_actions%rowtype;
  v_claimed boolean := false;
begin
  select * into v_action
  from chat_actions
  where token = p_token
  for update;

  if not found then
    return jsonb_build_object('status', 'not_found', 'claimed', false);
  end if;

  if v_action.status = 'pending' and v_action.expires_at <= now() then
    update chat_actions
    set status = 'cancelled',
        result = jsonb_build_object('reason', 'expired'),
        completed_at = now()
    where token = p_token
    returning * into v_action;
  elsif v_action.status = 'pending' then
    update chat_actions
    set status = 'processing', claimed_at = now()
    where token = p_token
    returning * into v_action;
    v_claimed := true;
  end if;

  return to_jsonb(v_action) || jsonb_build_object('claimed', v_claimed);
end;
$$;

-- Keep the health RPC as the single authoritative schema probe.
create or replace function deployment_health()
returns jsonb
language sql
stable
security definer
set search_path = public
as $$
  select jsonb_build_object(
    'database', 'ok',
    'schema_version', '0018',
    'checked_at', now()
  );
$$;

revoke all on table automation_heartbeats from public, anon, authenticated;
revoke all on table chat_actions from public, anon, authenticated;
revoke all on function claim_chat_action(uuid) from public, anon, authenticated;
revoke all on function deployment_health() from public, anon, authenticated;

grant select, insert, update on table automation_heartbeats to service_role;
grant select, insert, update on table chat_actions to service_role;
grant execute on function claim_chat_action(uuid) to service_role;
grant execute on function deployment_health() to service_role;
