begin;

create type public.release_status as enum (
    'draft',
    'building',
    'validation_failed',
    'ready',
    'published',
    'withdrawn'
);
create type public.release_artifact_kind as enum (
    'content_database',
    'manifest',
    'signature',
    'checksum',
    'export'
);
create type public.job_kind as enum (
    'url_fetch',
    'file_extract',
    'ocr',
    'content_validation',
    'spreadsheet_export',
    'release_build',
    'release_validation'
);
create type public.job_status as enum (
    'queued',
    'running',
    'succeeded',
    'failed',
    'cancelled'
);
create type public.job_event_level as enum ('debug', 'info', 'warning', 'error');

create table public.content_releases (
    release_id uuid primary key default gen_random_uuid(),
    content_version integer not null unique check (content_version > 0),
    version_name text not null unique,
    schema_version integer not null check (schema_version > 0),
    minimum_app_version integer not null default 1 check (minimum_app_version > 0),
    status public.release_status not null default 'draft',
    release_notes text not null default '',
    manifest jsonb,
    manifest_sha256 text,
    database_sha256 text,
    database_byte_size bigint check (database_byte_size is null or database_byte_size > 0),
    published_at timestamptz,
    created_at timestamptz not null default clock_timestamp(),
    created_by uuid references auth.users(id) on delete set null,
    updated_at timestamptz not null default clock_timestamp(),
    updated_by uuid references auth.users(id) on delete set null,
    constraint content_releases_name_not_blank check (btrim(version_name) <> ''),
    constraint content_releases_manifest_object check (
        manifest is null or jsonb_typeof(manifest) = 'object'
    ),
    constraint content_releases_manifest_hash_format check (
        manifest_sha256 is null or manifest_sha256 ~ '^[0-9a-f]{64}$'
    ),
    constraint content_releases_database_hash_format check (
        database_sha256 is null or database_sha256 ~ '^[0-9a-f]{64}$'
    )
);

create table public.release_items (
    release_item_id uuid primary key default gen_random_uuid(),
    release_id uuid not null references public.content_releases(release_id) on delete restrict,
    revision_id uuid not null references public.content_revisions(revision_id) on delete restrict,
    entity_type public.content_entity_type not null,
    entity_key text not null,
    revision_number integer not null,
    content_hash text not null,
    created_at timestamptz not null default clock_timestamp(),
    created_by uuid references auth.users(id) on delete set null,
    constraint release_items_hash_format check (content_hash ~ '^[0-9a-f]{64}$'),
    constraint release_items_release_revision_unique unique (release_id, revision_id),
    constraint release_items_release_entity_unique unique (release_id, entity_type, entity_key)
);

create table public.release_artifacts (
    release_artifact_id uuid primary key default gen_random_uuid(),
    release_id uuid not null references public.content_releases(release_id) on delete restrict,
    artifact_kind public.release_artifact_kind not null,
    bucket_id text not null default 'release-bundles',
    object_path text not null,
    mime_type text not null,
    byte_size bigint not null check (byte_size > 0),
    sha256 text not null check (sha256 ~ '^[0-9a-f]{64}$'),
    created_at timestamptz not null default clock_timestamp(),
    created_by uuid references auth.users(id) on delete set null,
    constraint release_artifacts_private_bucket check (bucket_id = 'release-bundles'),
    constraint release_artifacts_path_not_blank check (btrim(object_path) <> ''),
    constraint release_artifacts_release_kind_unique unique (release_id, artifact_kind),
    constraint release_artifacts_object_unique unique (bucket_id, object_path)
);

create table public.release_events (
    release_event_id bigint generated always as identity primary key,
    release_id uuid not null references public.content_releases(release_id) on delete restrict,
    status public.release_status not null,
    note text,
    created_at timestamptz not null default clock_timestamp(),
    created_by uuid references auth.users(id) on delete set null
);

create table public.release_channels (
    channel text primary key,
    release_id uuid not null references public.content_releases(release_id) on delete restrict,
    activated_at timestamptz not null default clock_timestamp(),
    activated_by uuid references auth.users(id) on delete set null,
    constraint release_channels_name_format check (channel ~ '^[a-z][a-z0-9_-]{1,31}$')
);

alter table public.validation_runs
    add constraint validation_runs_release_fk
    foreign key (release_id) references public.content_releases(release_id) on delete restrict;

create table public.ingestion_jobs (
    job_id uuid primary key default gen_random_uuid(),
    job_kind public.job_kind not null,
    status public.job_status not null default 'queued',
    source_version_id uuid references public.source_versions(source_version_id) on delete restrict,
    revision_id uuid references public.content_revisions(revision_id) on delete restrict,
    release_id uuid references public.content_releases(release_id) on delete restrict,
    progress_percent smallint not null default 0 check (progress_percent between 0 and 100),
    attempt_count integer not null default 0 check (attempt_count >= 0),
    max_attempts integer not null default 3 check (max_attempts between 1 and 20),
    input jsonb not null default '{}'::jsonb,
    output jsonb not null default '{}'::jsonb,
    error_message text,
    claimed_by text,
    claimed_at timestamptz,
    started_at timestamptz,
    completed_at timestamptz,
    created_at timestamptz not null default clock_timestamp(),
    created_by uuid references auth.users(id) on delete set null,
    updated_at timestamptz not null default clock_timestamp(),
    updated_by uuid references auth.users(id) on delete set null,
    constraint ingestion_jobs_input_object check (jsonb_typeof(input) = 'object'),
    constraint ingestion_jobs_output_object check (jsonb_typeof(output) = 'object'),
    constraint ingestion_jobs_failure_message check (
        status <> 'failed' or nullif(btrim(error_message), '') is not null
    )
);

create table public.job_events (
    job_event_id bigint generated always as identity primary key,
    job_id uuid not null references public.ingestion_jobs(job_id) on delete restrict,
    status public.job_status,
    level public.job_event_level not null default 'info',
    message text not null,
    payload jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default clock_timestamp(),
    created_by uuid references auth.users(id) on delete set null,
    constraint job_events_message_not_blank check (btrim(message) <> ''),
    constraint job_events_payload_object check (jsonb_typeof(payload) = 'object')
);

create index release_items_release_idx on public.release_items(release_id);
create index release_artifacts_release_idx on public.release_artifacts(release_id);
create index release_events_release_idx on public.release_events(release_id, release_event_id desc);
create index ingestion_jobs_queue_idx
    on public.ingestion_jobs(status, created_at)
    where status in ('queued', 'running');
create index ingestion_jobs_source_version_idx
    on public.ingestion_jobs(source_version_id, created_at desc)
    where source_version_id is not null;
create index job_events_job_idx on public.job_events(job_id, job_event_id);

create or replace function public.validate_release_item()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
declare
    revision_row public.content_revisions%rowtype;
    release_state public.release_status;
begin
    select * into revision_row
    from public.content_revisions
    where revision_id = new.revision_id;

    if not found then
        raise exception using errcode = '23503', message = 'unknown revision';
    end if;
    if public.current_revision_state(new.revision_id) <> 'approved' then
        raise exception using errcode = '23514', message = 'only approved revisions can enter a release';
    end if;

    select status into release_state
    from public.content_releases
    where release_id = new.release_id;
    if release_state not in ('draft', 'building') then
        raise exception using errcode = '55000', message = 'release contents are already sealed';
    end if;

    new.entity_type := revision_row.entity_type;
    new.entity_key := revision_row.entity_key;
    new.revision_number := revision_row.revision_number;
    new.content_hash := revision_row.content_hash;
    new.created_by := coalesce(new.created_by, auth.uid());
    return new;
end;
$$;

create or replace function public.protect_release_child_mutation()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
declare
    target_release_id uuid;
    release_state public.release_status;
begin
    target_release_id := case when tg_op = 'DELETE' then old.release_id else new.release_id end;
    select status into release_state
    from public.content_releases
    where release_id = target_release_id;

    if release_state not in ('draft', 'building') then
        raise exception using errcode = '55000', message = 'release contents and artifacts are sealed';
    end if;
    if tg_op = 'DELETE' then
        return old;
    end if;
    return new;
end;
$$;

create or replace function public.validate_release_change()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
declare
    old_payload jsonb;
    new_payload jsonb;
begin
    if tg_op = 'INSERT' then
        if new.status <> 'draft' then
            raise exception using errcode = '23514', message = 'a release must start as draft';
        end if;
        return new;
    end if;

    if old.status in ('ready', 'published', 'withdrawn') then
        old_payload := to_jsonb(old) - array['status', 'updated_at', 'updated_by'];
        new_payload := to_jsonb(new) - array['status', 'updated_at', 'updated_by'];
        if old_payload is distinct from new_payload then
            raise exception using errcode = '55000', message = 'sealed release metadata is immutable';
        end if;
    end if;

    if old.status = new.status then
        return new;
    end if;

    if not (
        (old.status = 'draft' and new.status in ('building', 'withdrawn'))
        or (old.status = 'building' and new.status in ('validation_failed', 'ready', 'withdrawn'))
        or (old.status = 'validation_failed' and new.status in ('building', 'withdrawn'))
        or (old.status = 'ready' and new.status in ('published', 'withdrawn'))
        or (old.status = 'published' and new.status = 'withdrawn')
    ) then
        raise exception using
            errcode = '23514',
            message = format('invalid release transition: %s -> %s', old.status, new.status);
    end if;

    if new.status = 'ready' then
        if new.manifest is null
           or new.manifest_sha256 is null
           or new.database_sha256 is null
           or new.database_byte_size is null then
            raise exception using errcode = '23514', message = 'ready release metadata is incomplete';
        end if;
        if not exists (select 1 from public.release_items where release_id = new.release_id) then
            raise exception using errcode = '23514', message = 'a ready release must contain approved revisions';
        end if;
        if not exists (
            select 1 from public.release_artifacts
            where release_id = new.release_id and artifact_kind = 'content_database'
        ) or not exists (
            select 1 from public.release_artifacts
            where release_id = new.release_id and artifact_kind = 'manifest'
        ) then
            raise exception using errcode = '23514', message = 'database and manifest artifacts are required';
        end if;
        if not exists (
            select 1 from public.validation_runs
            where release_id = new.release_id and status = 'passed'
        ) then
            raise exception using errcode = '23514', message = 'successful release validation is required';
        end if;
    end if;

    if new.status = 'published' and new.published_at is null then
        new.published_at := clock_timestamp();
    end if;
    return new;
end;
$$;

create or replace function public.record_release_event()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
    if tg_op = 'INSERT' or new.status is distinct from old.status then
        insert into public.release_events (release_id, status, note, created_by)
        values (
            new.release_id,
            new.status,
            nullif(current_setting('app.release_note', true), ''),
            auth.uid()
        );
    end if;
    return new;
end;
$$;

create or replace function public.set_release_status(
    p_release_id uuid,
    p_status public.release_status,
    p_note text default null
)
returns public.content_releases
language plpgsql
security definer
set search_path = ''
as $$
declare
    result public.content_releases%rowtype;
begin
    if not public.has_admin_role(array['owner', 'releaser']::public.admin_role[]) then
        raise exception using errcode = '42501', message = 'releaser role required';
    end if;

    perform set_config('app.release_note', coalesce(p_note, ''), true);

    update public.content_releases
    set status = p_status
    where release_id = p_release_id
    returning * into result;
    if not found then
        raise exception using errcode = 'P0002', message = 'release not found';
    end if;

    return result;
end;
$$;

create or replace function public.activate_release(
    p_release_id uuid,
    p_channel text default 'stable'
)
returns public.release_channels
language plpgsql
security definer
set search_path = ''
as $$
declare
    release_state public.release_status;
    result public.release_channels%rowtype;
begin
    if not public.has_admin_role(array['owner', 'releaser']::public.admin_role[]) then
        raise exception using errcode = '42501', message = 'releaser role required';
    end if;
    if p_channel !~ '^[a-z][a-z0-9_-]{1,31}$' then
        raise exception using errcode = '23514', message = 'invalid release channel';
    end if;

    perform pg_advisory_xact_lock(hashtextextended('release-channel:' || p_channel, 0));
    select status into release_state
    from public.content_releases
    where release_id = p_release_id
    for update;
    if not found then
        raise exception using errcode = 'P0002', message = 'release not found';
    end if;
    if release_state = 'ready' then
        update public.content_releases
        set status = 'published'
        where release_id = p_release_id;
    elsif release_state <> 'published' then
        raise exception using errcode = '23514', message = 'only ready or published releases can be activated';
    end if;

    insert into public.release_channels (channel, release_id, activated_at, activated_by)
    values (p_channel, p_release_id, clock_timestamp(), auth.uid())
    on conflict (channel) do update
    set release_id = excluded.release_id,
        activated_at = excluded.activated_at,
        activated_by = excluded.activated_by
    returning * into result;

    insert into public.revision_state_events (revision_id, state, note, created_by)
    select item.revision_id, 'published', 'included in release ' || p_release_id::text, auth.uid()
    from public.release_items as item
    where item.release_id = p_release_id
      and public.current_revision_state(item.revision_id) = 'approved';

    return result;
end;
$$;

create or replace function public.enforce_job_change()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
    if tg_op = 'UPDATE' and (
        new.job_id <> old.job_id
        or new.job_kind <> old.job_kind
        or new.source_version_id is distinct from old.source_version_id
        or new.revision_id is distinct from old.revision_id
        or new.release_id is distinct from old.release_id
    ) then
        raise exception using errcode = '55000', message = 'job identity and targets are immutable';
    end if;
    if tg_op = 'UPDATE' and old.status <> new.status and not (
        (old.status = 'queued' and new.status in ('running', 'cancelled', 'failed'))
        or (old.status = 'running' and new.status in ('succeeded', 'failed', 'cancelled'))
        or (old.status = 'failed' and new.status = 'queued' and new.attempt_count > old.attempt_count)
    ) then
        raise exception using
            errcode = '23514',
            message = format('invalid job transition: %s -> %s', old.status, new.status);
    end if;
    if new.status = 'running' and new.started_at is null then
        new.started_at := clock_timestamp();
    end if;
    if new.status in ('succeeded', 'failed', 'cancelled') and new.completed_at is null then
        new.completed_at := clock_timestamp();
    end if;
    return new;
end;
$$;

create or replace function public.record_job_event()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
    if tg_op = 'INSERT' or new.status is distinct from old.status then
        insert into public.job_events (job_id, status, level, message, created_by)
        values (
            new.job_id,
            new.status,
            case when new.status = 'failed' then 'error'::public.job_event_level else 'info'::public.job_event_level end,
            case when new.status = 'failed' then coalesce(new.error_message, 'job failed') else 'job ' || new.status::text end,
            auth.uid()
        );
    end if;
    return new;
end;
$$;

create trigger content_releases_set_audit_columns
before insert or update on public.content_releases
for each row execute function public.set_audit_columns();
create trigger content_releases_validate_change
before insert or update on public.content_releases
for each row execute function public.validate_release_change();
create trigger content_releases_record_event
after insert or update of status on public.content_releases
for each row execute function public.record_release_event();
create trigger content_releases_immutable_identity
before update on public.content_releases
for each row execute function public.prevent_column_update('release_id', 'content_version', 'version_name', 'schema_version');

create trigger release_items_validate
before insert on public.release_items
for each row execute function public.validate_release_item();
create trigger release_items_protect_mutation
before update or delete on public.release_items
for each row execute function public.protect_release_child_mutation();
create trigger release_items_immutable_identity
before update on public.release_items
for each row execute function public.prevent_column_update('release_item_id', 'release_id', 'revision_id');

create trigger release_artifacts_protect_mutation
before insert or update or delete on public.release_artifacts
for each row execute function public.protect_release_child_mutation();
create trigger release_artifacts_immutable_identity
before update on public.release_artifacts
for each row execute function public.prevent_column_update('release_artifact_id', 'release_id', 'artifact_kind', 'bucket_id', 'object_path');

create trigger release_events_append_only
before update or delete on public.release_events
for each row execute function public.prevent_row_mutation();

create trigger ingestion_jobs_set_audit_columns
before insert or update on public.ingestion_jobs
for each row execute function public.set_audit_columns();
create trigger ingestion_jobs_enforce_change
before insert or update on public.ingestion_jobs
for each row execute function public.enforce_job_change();
create trigger ingestion_jobs_record_event
after insert or update of status on public.ingestion_jobs
for each row execute function public.record_job_event();
create trigger job_events_append_only
before update or delete on public.job_events
for each row execute function public.prevent_row_mutation();

revoke all on function public.validate_release_item() from public;
revoke all on function public.protect_release_child_mutation() from public;
revoke all on function public.validate_release_change() from public;
revoke all on function public.record_release_event() from public;
revoke all on function public.set_release_status(uuid, public.release_status, text) from public;
revoke all on function public.activate_release(uuid, text) from public;
revoke all on function public.enforce_job_change() from public;
revoke all on function public.record_job_event() from public;

commit;
