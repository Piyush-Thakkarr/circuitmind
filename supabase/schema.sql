-- CircuitMind tables. Apply once in the Supabase SQL editor (or with the migration tool).
--
-- designs: one row per run a signed-in user starts. The engine inserts it with the
-- user's own token, so row-level security does the access control: a user sees and
-- writes only their rows. Rows are never deleted by the app, so counting today's rows
-- is the per-user daily cap.
--
-- sim_ms_used_this_month(): sum of simulated milliseconds across every user this
-- calendar month. Runs as the table owner (security definer) so a plain user can
-- read the total without seeing anyone's rows. The engine refuses new simulated runs
-- when the total nears the free-tier budget; the web app shows the figure.

create table if not exists public.designs (
  id          uuid primary key default gen_random_uuid(),
  user_id     uuid not null references auth.users (id) on delete cascade,
  created_at  timestamptz not null default now(),
  prompt      text not null,
  status      text not null check (status in ('running', 'verified', 'free_checks', 'failed', 'error')),
  simulated   boolean not null default false,
  sim_ms      integer not null default 0,
  attempts    integer not null default 0,
  model       text,
  design      jsonb,
  guide       jsonb,
  diagram     jsonb,
  checks      jsonb,
  failure     jsonb
);

create index if not exists designs_user_created on public.designs (user_id, created_at desc);
create index if not exists designs_created on public.designs (created_at);

alter table public.designs enable row level security;

drop policy if exists "own rows: read" on public.designs;
create policy "own rows: read" on public.designs
  for select to authenticated using (auth.uid() = user_id);

drop policy if exists "own rows: insert" on public.designs;
create policy "own rows: insert" on public.designs
  for insert to authenticated with check (auth.uid() = user_id);

drop policy if exists "own rows: update" on public.designs;
create policy "own rows: update" on public.designs
  for update to authenticated using (auth.uid() = user_id) with check (auth.uid() = user_id);

-- no delete policy: rows stay, so the daily count cannot be reset by the user

create or replace function public.sim_ms_used_this_month()
returns bigint
language sql
security definer
set search_path = public
stable
as $$
  select coalesce(sum(sim_ms), 0)::bigint
  from public.designs
  where created_at >= date_trunc('month', now() at time zone 'utc');
$$;

revoke all on function public.sim_ms_used_this_month() from public;
grant execute on function public.sim_ms_used_this_month() to anon, authenticated;
