-- People who joined Eclectolog through the web app, and the Spotify credentials
-- the daily job uses to build each person's mix.

-- Profile shown in the app. Users can read only their own row; writes happen server-side.
create table public.profiles (
  id           uuid primary key references auth.users (id) on delete cascade,
  spotify_id   text not null unique,
  display_name text,
  avatar_url   text,
  country      text,
  product      text,          -- "premium" / "free"
  joined_at    timestamptz not null default now(),
  updated_at   timestamptz not null default now()
);

alter table public.profiles enable row level security;

create policy "profiles: read own"
  on public.profiles for select
  to authenticated
  using ((select auth.uid()) = id);

-- Spotify OAuth tokens. RLS is on with no policies, and table privileges are
-- revoked, so only the service role (server code and the cron job) can touch it.
create table public.spotify_tokens (
  user_id       uuid primary key references auth.users (id) on delete cascade,
  refresh_token text not null,
  access_token  text,
  expires_at    timestamptz,
  scope         text,
  updated_at    timestamptz not null default now()
);

alter table public.spotify_tokens enable row level security;
revoke all on public.spotify_tokens from anon, authenticated;

create or replace function public.touch_updated_at()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  new.updated_at := now();
  return new;
end;
$$;

create trigger profiles_touch before update on public.profiles
  for each row execute function public.touch_updated_at();

create trigger spotify_tokens_touch before update on public.spotify_tokens
  for each row execute function public.touch_updated_at();
