create table if not exists public.sync_events (
  sequence bigint generated always as identity primary key,
  event_id uuid not null unique,
  team_id uuid not null,
  entity_type text not null,
  entity_id uuid not null,
  operation text not null check (operation in ('upsert', 'delete')),
  version integer not null,
  changed_at timestamptz not null,
  changed_by_device uuid not null,
  payload jsonb not null,
  created_at timestamptz not null default now()
);

create index if not exists sync_events_team_sequence_idx
on public.sync_events (team_id, sequence);
