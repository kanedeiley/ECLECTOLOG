-- Served-track history: one row per generated mix, replacing history.jsonl on the
-- eclectolog-state branch. `tracks` holds the same objects as a line of that file:
--   [{"id", "name", "artists": [[id, name], ...], "album", "source", "reason"}, ...]
-- The daily job writes with the service role; people can read their own mixes in the web app.

create table public.mix_runs (
  id            bigint generated always as identity primary key,
  user_id       uuid not null references auth.users (id) on delete cascade,
  ran_at        timestamptz not null default now(),
  playlist_name text not null,
  playlist_url  text,
  tracks        jsonb not null default '[]'::jsonb check (jsonb_typeof(tracks) = 'array')
);

create index mix_runs_user_ran_at on public.mix_runs (user_id, ran_at desc);

alter table public.mix_runs enable row level security;

create policy "mix_runs: read own"
  on public.mix_runs for select
  to authenticated
  using ((select auth.uid()) = user_id);
