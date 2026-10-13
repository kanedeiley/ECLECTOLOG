-- Daily trigger for the Eclectolog GitHub workflow. GitHub's own `schedule:` trigger was starting
-- the job ~6 hours late, so pg_cron calls the workflow_dispatch API on time instead.
--
-- Needs two Vault secrets (see README → "Schedule the daily run"):
--   eclectolog_github_repo   e.g. 'kanedeiley/ECLECTOLOG'
--   eclectolog_github_token  fine-grained PAT for that repo with Actions: read and write
-- Each call's response lands in net._http_response; GitHub answers 204 on success.

create extension if not exists pg_cron with schema pg_catalog;
create extension if not exists pg_net with schema extensions;

-- Kept out of `public` so the REST API can't expose it as an RPC.
create schema if not exists private;

create or replace function private.dispatch_eclectolog()
returns bigint
language plpgsql
as $$
declare
  repo  text := (select decrypted_secret from vault.decrypted_secrets where name = 'eclectolog_github_repo');
  token text := (select decrypted_secret from vault.decrypted_secrets where name = 'eclectolog_github_token');
begin
  if repo is null or token is null then
    raise warning 'eclectolog dispatch skipped: Vault secrets eclectolog_github_repo / eclectolog_github_token not set';
    return null;
  end if;

  return net.http_post(
    url     := format('https://api.github.com/repos/%s/actions/workflows/eclectolog.yml/dispatches', repo),
    body    := jsonb_build_object('ref', 'main'),
    headers := jsonb_build_object(
      'Accept', 'application/vnd.github+json',
      'Authorization', 'Bearer ' || token,
      'Content-Type', 'application/json',
      'User-Agent', 'eclectolog-pg-cron',
      'X-GitHub-Api-Version', '2022-11-28'
    )
  );
end;
$$;

revoke all on function private.dispatch_eclectolog() from public, anon, authenticated;

-- Daily at 01:30 UTC = 9:30 PM US Eastern in summer (EDT), 8:30 PM in winter (EST).
-- pg_cron runs in UTC. Re-running this with the same job name replaces the schedule.
select cron.schedule('eclectolog-daily', '30 1 * * *', 'select private.dispatch_eclectolog()');
