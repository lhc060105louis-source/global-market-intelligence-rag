alter table public.sync_events enable row level security;

create policy "team members read sync events"
on public.sync_events for select
using (public.is_team_member(team_id, auth.uid()));

create policy "team members append sync events"
on public.sync_events for insert
with check (public.is_team_member(team_id, auth.uid()));
