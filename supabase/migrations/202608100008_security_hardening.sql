begin;

create or replace function public.is_safe_public_source_url(p_url text)
returns boolean
language plpgsql
immutable
strict
set search_path = ''
as $$
declare
    authority text;
    host_name text;
    port_text text;
begin
    if length(p_url) > 2048
       or p_url !~* '^https?://'
       or p_url ~ '[[:space:][:cntrl:]]'
       or position(chr(92) in p_url) > 0 then
        return false;
    end if;
    authority := substring(p_url from '^[Hh][Tt][Tt][Pp][Ss]?://([^/?#]+)');
    if authority is null or position('@' in authority) > 0 or left(authority, 1) = '[' then
        return false;
    end if;
    if authority !~ '^[^:]+(:[0-9]{1,5})?$' then
        return false;
    end if;
    port_text := substring(authority from ':([0-9]{1,5})$');
    if port_text is not null and port_text::integer > 65535 then return false; end if;
    host_name := rtrim(lower(split_part(authority, ':', 1)), '.');
    if position('.' in host_name) = 0
       or host_name ~ '^[0-9.]+$'
       or host_name = 'localhost'
       or host_name ~ '\.\.'
       or host_name ~ '(^|\.)-'
       or host_name ~ '-(\.|$)'
       or host_name ~ '(\.localhost|\.local|\.internal|\.home\.arpa|\.nip\.io|\.sslip\.io|\.xip\.io)$' then
        return false;
    end if;
    return host_name ~ '^[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?$';
end;
$$;

create or replace function public.enforce_safe_source_url()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
declare
    candidate text;
begin
    if tg_table_name = 'sources' then
        if to_jsonb(new) ->> 'kind' <> 'url' then
            return new;
        end if;
        candidate := to_jsonb(new) ->> 'locator';
    elsif tg_table_name = 'source_versions' then
        candidate := to_jsonb(new) ->> 'fetch_url';
        if candidate is null then
            return new;
        end if;
    else
        return new;
    end if;
    if not public.is_safe_public_source_url(candidate) then
        raise exception using
            errcode = '22023',
            message = 'source URL must use public HTTP(S) host without credentials or IP literals';
    end if;
    return new;
end;
$$;

create trigger sources_safe_url
before insert or update of kind, locator on public.sources
for each row execute function public.enforce_safe_source_url();
create trigger source_versions_safe_fetch_url
before insert or update of fetch_url on public.source_versions
for each row execute function public.enforce_safe_source_url();

alter table public.validation_runs add column release_fingerprint text;

create or replace function public.release_validation_fingerprint(p_release_id uuid)
returns text
language plpgsql
stable
security definer
set search_path = ''
as $$
declare
    payload jsonb;
begin
    select jsonb_build_object(
        'release', jsonb_build_object(
            'releaseId', release.release_id,
            'contentVersion', release.content_version,
            'versionName', release.version_name,
            'schemaVersion', release.schema_version,
            'minimumAppVersion', release.minimum_app_version,
            'releaseNotes', release.release_notes,
            'manifest', release.manifest,
            'manifestSha256', release.manifest_sha256,
            'databaseSha256', release.database_sha256,
            'databaseByteSize', release.database_byte_size
        ),
        'items', coalesce((
            select jsonb_agg(
                jsonb_build_object(
                    'entityType', item.entity_type,
                    'entityKey', item.entity_key,
                    'revisionNumber', item.revision_number,
                    'contentHash', item.content_hash
                ) order by item.entity_type, item.entity_key
            )
            from public.release_items as item
            where item.release_id = release.release_id
        ), '[]'::jsonb),
        'artifacts', coalesce((
            select jsonb_agg(
                jsonb_build_object(
                    'kind', artifact.artifact_kind,
                    'bucket', artifact.bucket_id,
                    'path', artifact.object_path,
                    'mimeType', artifact.mime_type,
                    'byteSize', artifact.byte_size,
                    'sha256', artifact.sha256
                ) order by artifact.artifact_kind
            )
            from public.release_artifacts as artifact
            where artifact.release_id = release.release_id
        ), '[]'::jsonb)
    ) into payload
    from public.content_releases as release
    where release.release_id = p_release_id;

    if payload is null then
        raise exception using errcode = 'P0002', message = 'release not found';
    end if;
    return encode(extensions.digest(convert_to(payload::text, 'UTF8'), 'sha256'), 'hex');
end;
$$;

update public.validation_runs
set release_fingerprint = public.release_validation_fingerprint(release_id)
where target_type = 'release';

alter table public.validation_runs
    add constraint validation_runs_release_fingerprint_shape check (
        (target_type = 'release' and release_fingerprint ~ '^[0-9a-f]{64}$')
        or (target_type <> 'release' and release_fingerprint is null)
    );

create or replace function public.bind_release_validation_fingerprint()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
declare
    current_fingerprint text;
begin
    if tg_op = 'UPDATE' and (
        new.target_type is distinct from old.target_type
        or new.revision_id is distinct from old.revision_id
        or new.release_id is distinct from old.release_id
        or new.release_fingerprint is distinct from old.release_fingerprint
    ) then
        raise exception using errcode = '55000', message = 'validation target and fingerprint are immutable';
    end if;
    if new.target_type <> 'release' then
        new.release_fingerprint := null;
        return new;
    end if;

    current_fingerprint := public.release_validation_fingerprint(new.release_id);
    if tg_op = 'INSERT' then
        new.release_fingerprint := current_fingerprint;
    elsif new.status = 'passed' and old.status is distinct from 'passed'
          and new.release_fingerprint <> current_fingerprint then
        raise exception using errcode = '23514', message = 'release changed while validation was running';
    end if;
    return new;
end;
$$;

create trigger validation_runs_bind_release_fingerprint
before insert or update on public.validation_runs
for each row execute function public.bind_release_validation_fingerprint();

create or replace function public.require_current_release_validation()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
declare
    current_fingerprint text;
begin
    if new.status <> 'ready' or old.status = 'ready' then
        return new;
    end if;
    if new.manifest is distinct from old.manifest
       or new.manifest_sha256 is distinct from old.manifest_sha256
       or new.database_sha256 is distinct from old.database_sha256
       or new.database_byte_size is distinct from old.database_byte_size
       or new.release_notes is distinct from old.release_notes
       or new.minimum_app_version is distinct from old.minimum_app_version then
        raise exception using
            errcode = '23514',
            message = 'seal release metadata before running release validation';
    end if;
    current_fingerprint := public.release_validation_fingerprint(new.release_id);
    if not exists (
        select 1 from public.release_artifacts as artifact
        where artifact.release_id = new.release_id
          and artifact.artifact_kind = 'content_database'
          and artifact.sha256 = new.database_sha256
          and artifact.byte_size = new.database_byte_size
    ) or not exists (
        select 1 from public.release_artifacts as artifact
        where artifact.release_id = new.release_id
          and artifact.artifact_kind = 'manifest'
          and artifact.sha256 = new.manifest_sha256
    ) then
        raise exception using
            errcode = '23514',
            message = 'release artifact hashes and sizes must match sealed release metadata';
    end if;
    if new.manifest ->> 'sha256' is distinct from new.database_sha256
       or (new.manifest ->> 'byteSize')::bigint is distinct from new.database_byte_size
       or (new.manifest ->> 'contentDbVersion')::integer is distinct from new.content_version then
        raise exception using
            errcode = '23514',
            message = 'manifest database identity must match the release';
    end if;
    if not exists (
        select 1
        from public.validation_runs as run
        where run.release_id = new.release_id
          and run.status = 'passed'
          and run.release_fingerprint = current_fingerprint
    ) then
        raise exception using
            errcode = '23514',
            message = 'successful validation for the exact release fingerprint is required';
    end if;
    return new;
end;
$$;

create trigger content_releases_require_current_validation
before update of status on public.content_releases
for each row execute function public.require_current_release_validation();

create or replace function public.start_release_validation(
    p_release_id uuid,
    p_validator_name text default 'findone-release-validator',
    p_validator_version text default ''
)
returns public.validation_runs
language plpgsql
security definer
set search_path = ''
as $$
declare
    release_row public.content_releases%rowtype;
    result public.validation_runs%rowtype;
begin
    if not public.has_admin_role(array['owner', 'reviewer', 'releaser']::public.admin_role[]) then
        raise exception using errcode = '42501', message = 'reviewer or releaser role required';
    end if;
    select * into release_row
    from public.content_releases
    where release_id = p_release_id
    for update;
    if not found then
        raise exception using errcode = 'P0002', message = 'release not found';
    end if;
    if release_row.status <> 'building' then
        raise exception using errcode = '23514', message = 'only a building release can be validated';
    end if;
    if exists (
        select 1 from public.ingestion_jobs
        where release_id = p_release_id
          and job_kind = 'release_build'
          and status in ('queued', 'running')
    ) then
        raise exception using errcode = '55000', message = 'release build is still queued or running';
    end if;
    if not exists (
        select 1 from public.ingestion_jobs
        where release_id = p_release_id
          and job_kind = 'release_build'
          and status = 'succeeded'
    ) then
        raise exception using errcode = '55000', message = 'a successful release build is required before validation';
    end if;
    if release_row.database_sha256 is null
       or release_row.database_byte_size is null
       or release_row.manifest_sha256 is null
       or release_row.manifest = '{}'::jsonb
       or not exists (
           select 1 from public.release_artifacts as artifact
           where artifact.release_id = p_release_id
             and artifact.artifact_kind = 'content_database'
             and artifact.sha256 = release_row.database_sha256
             and artifact.byte_size = release_row.database_byte_size
       )
       or not exists (
           select 1 from public.release_artifacts as artifact
           where artifact.release_id = p_release_id
             and artifact.artifact_kind = 'manifest'
             and artifact.sha256 = release_row.manifest_sha256
       ) then
        raise exception using errcode = '55000', message = 'sealed database and manifest artifacts are required before validation';
    end if;
    if exists (
        select 1 from public.validation_runs
        where release_id = p_release_id and status in ('queued', 'running')
    ) then
        raise exception using errcode = '55000', message = 'release validation is already queued or running';
    end if;

    insert into public.validation_runs (
        target_type, release_id, validator_name, validator_version, created_by
    ) values (
        'release', p_release_id, p_validator_name, p_validator_version, auth.uid()
    ) returning * into result;

    insert into public.ingestion_jobs (
        job_kind, release_id, input, created_by
    ) values (
        'release_validation',
        p_release_id,
        jsonb_build_object(
            'validationRunId', result.validation_run_id,
            'releaseFingerprint', result.release_fingerprint
        ),
        auth.uid()
    );
    return result;
end;
$$;

revoke all on function public.is_safe_public_source_url(text) from public;
revoke all on function public.enforce_safe_source_url() from public;
revoke all on function public.release_validation_fingerprint(uuid) from public;
revoke all on function public.bind_release_validation_fingerprint() from public;
revoke all on function public.require_current_release_validation() from public;
revoke all on function public.start_release_validation(uuid, text, text) from public;
grant execute on function public.is_safe_public_source_url(text) to authenticated, service_role;
grant execute on function public.start_release_validation(uuid, text, text) to authenticated, service_role;

commit;
