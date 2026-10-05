-- Per-user mix weights, edited from the web app. Columns match the `mix:` keys in
-- config.yaml and are stored as whole percentages that always add up to 100.

create table public.preferences (
  user_id         uuid primary key references auth.users (id) on delete cascade,
  deep_cuts       smallint not null default 25 check (deep_cuts between 0 and 100),
  genre_neighbors smallint not null default 35 check (genre_neighbors between 0 and 100),
  wildcard        smallint not null default 20 check (wildcard between 0 and 100),
  compass         smallint not null default 20 check (compass between 0 and 100),
  updated_at      timestamptz not null default now(),
  constraint mix_sums_to_100 check (deep_cuts + genre_neighbors + wildcard + compass = 100)
);

alter table public.preferences enable row level security;

create policy "preferences: read own"
  on public.preferences for select
  to authenticated
  using ((select auth.uid()) = user_id);

create policy "preferences: insert own"
  on public.preferences for insert
  to authenticated
  with check ((select auth.uid()) = user_id);

create policy "preferences: update own"
  on public.preferences for update
  to authenticated
  using ((select auth.uid()) = user_id)
  with check ((select auth.uid()) = user_id);

create trigger preferences_touch before update on public.preferences
  for each row execute function public.touch_updated_at();
