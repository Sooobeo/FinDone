-- Manual source processing controls.  Registration creates a dormant job;
-- the external worker only sees it after an Owner starts it.
alter type public.job_status add value if not exists 'pending_start' before 'queued';
alter type public.job_status add value if not exists 'paused' after 'running';

begin;

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
        (old.status = 'pending_start' and new.status in ('queued', 'cancelled'))
        or (old.status = 'queued' and new.status in ('running', 'paused', 'cancelled', 'failed'))
        or (old.status = 'running' and new.status in ('succeeded', 'paused', 'failed', 'cancelled'))
        or (old.status = 'paused' and new.status in ('queued', 'cancelled'))
        or (old.status = 'failed' and new.status = 'queued' and new.attempt_count > old.attempt_count)
    ) then
        raise exception using errcode = '23514', message = format('invalid job transition: %s -> %s', old.status, new.status);
    end if;
    if new.status = 'running' and new.started_at is null then new.started_at := clock_timestamp(); end if;
    if new.status in ('succeeded', 'failed', 'cancelled') and new.completed_at is null then new.completed_at := clock_timestamp(); end if;
    if new.status in ('pending_start', 'queued', 'paused') then new.completed_at := null; end if;
    return new;
end;
$$;

create or replace function public.register_url_source(
    p_source_id text, p_label text, p_url text, p_source_type text default 'web'
)
returns jsonb language plpgsql security definer set search_path = '' as $$
declare version_id uuid; job_id_value uuid;
begin
    if not public.has_admin_role(array['owner', 'editor']::public.admin_role[]) then raise exception using errcode = '42501', message = 'editor role required'; end if;
    if not public.is_safe_public_source_url(p_url) then raise exception using errcode = '22023', message = 'unsafe source URL'; end if;
    insert into public.sources (source_id, kind, label, locator, source_type, created_by)
    values (p_source_id, 'url', p_label, p_url, coalesce(p_source_type, 'web'), auth.uid());
    insert into public.source_versions (source_id, version_number, fetch_url, parse_status, created_by)
    values (p_source_id, 1, p_url, 'pending', auth.uid()) returning source_version_id into version_id;
    insert into public.ingestion_jobs (job_kind, status, source_version_id, input, created_by)
    values ('url_fetch', 'pending_start', version_id, jsonb_build_object('url', p_url), auth.uid()) returning job_id into job_id_value;
    return jsonb_build_object('sourceVersionId', version_id, 'jobId', job_id_value, 'jobStatus', 'pending_start');
end; $$;

create or replace function public.register_file_source(
    p_source_id text, p_source_version_id uuid, p_label text, p_object_path text,
    p_original_filename text, p_mime_type text, p_byte_size bigint, p_sha256 text
)
returns jsonb language plpgsql security definer set search_path = '' as $$
declare job_id_value uuid;
begin
    if not public.has_admin_role(array['owner', 'editor']::public.admin_role[]) then raise exception using errcode = '42501', message = 'editor role required'; end if;
    if auth.uid() is null or split_part(p_object_path, '/', 1) <> auth.uid()::text then raise exception using errcode = '42501', message = 'storage object must belong to the current admin'; end if;
    if p_byte_size < 1 or p_byte_size > 104857600 or p_sha256 !~ '^[0-9a-f]{64}$' or nullif(btrim(p_original_filename), '') is null then raise exception using errcode = '22023', message = 'invalid source file metadata'; end if;
    if not exists (select 1 from storage.objects where bucket_id = 'source-private' and name = p_object_path) then raise exception using errcode = 'P0002', message = 'uploaded storage object not found'; end if;
    insert into public.sources (source_id, kind, label, locator, source_type, created_by)
    values (p_source_id, 'file', p_label, p_object_path, coalesce(p_mime_type, 'application/octet-stream'), auth.uid());
    insert into public.source_versions (source_version_id, source_id, version_number, original_filename, mime_type, byte_size, sha256, parse_status, created_by)
    values (p_source_version_id, p_source_id, 1, p_original_filename, p_mime_type, p_byte_size, p_sha256, 'pending', auth.uid());
    insert into public.source_files (source_version_id, file_role, object_path, original_filename, mime_type, byte_size, sha256, created_by)
    values (p_source_version_id, 'original', p_object_path, p_original_filename, p_mime_type, p_byte_size, p_sha256, auth.uid());
    insert into public.ingestion_jobs (job_kind, status, source_version_id, input, created_by)
    values ('file_extract', 'pending_start', p_source_version_id, jsonb_build_object('objectPath', p_object_path, 'originalFilename', p_original_filename), auth.uid()) returning job_id into job_id_value;
    return jsonb_build_object('sourceVersionId', p_source_version_id, 'jobId', job_id_value, 'jobStatus', 'pending_start');
end; $$;

create or replace function public.control_source_ingestion_job(p_job_id uuid, p_action text)
returns jsonb language plpgsql security definer set search_path = '' as $$
declare job_row public.ingestion_jobs%rowtype; next_status public.job_status; next_stage text;
begin
    if not public.has_admin_role(array['owner']::public.admin_role[]) then raise exception using errcode = '42501', message = 'owner role required'; end if;
    if p_action not in ('start', 'pause', 'resume', 'cancel') then raise exception using errcode = '22023', message = 'unsupported source job action'; end if;
    select * into job_row from public.ingestion_jobs where job_id = p_job_id for update;
    if not found or job_row.job_kind not in ('file_extract', 'url_fetch') then raise exception using errcode = 'P0002', message = 'source job not found'; end if;
    if p_action in ('start', 'resume') then
        if job_row.status not in ('pending_start', 'paused') then raise exception using errcode = '55000', message = 'source job is not waiting to start or resume'; end if;
        next_status := 'queued'; next_stage := 'queued';
    elsif p_action = 'pause' then
        if job_row.status not in ('queued', 'running') then raise exception using errcode = '55000', message = 'source job is not active'; end if;
        next_status := 'paused'; next_stage := 'paused';
    else
        if job_row.status not in ('pending_start', 'queued', 'running', 'paused') then raise exception using errcode = '55000', message = 'source job cannot be cancelled'; end if;
        next_status := 'cancelled'; next_stage := 'cancelled';
    end if;
    update public.ingestion_jobs
    set status = next_status, output = output || jsonb_build_object('stage', next_stage, 'controlAction', p_action),
        error_message = null, claimed_by = case when next_status = 'paused' then claimed_by else null end,
        claimed_at = case when next_status = 'paused' then claimed_at else null end, updated_by = auth.uid()
    where job_id = p_job_id;
    if next_status = 'cancelled' then
        update public.source_versions set parse_status = 'archived', updated_by = auth.uid()
        where source_version_id = job_row.source_version_id and parse_status not in ('ready', 'needs_review');
    end if;
    return jsonb_build_object('jobId', p_job_id, 'jobStatus', next_status, 'stage', next_stage);
end; $$;

create or replace function public.archive_unconnected_source(p_source_id text)
returns jsonb language plpgsql security definer set search_path = '' as $$
declare linked_count integer; active_count integer; archived_count integer;
begin
    if not public.has_admin_role(array['owner']::public.admin_role[]) then raise exception using errcode = '42501', message = 'owner role required'; end if;
    select count(*) into linked_count from public.element_sources where source_id = p_source_id;
    if linked_count > 0 then raise exception using errcode = '23503', message = 'connected source cannot be deleted'; end if;
    update public.ingestion_jobs job
    set status = 'cancelled', output = output || jsonb_build_object('stage', 'cancelled', 'controlAction', 'delete')
    from public.source_versions version
    where version.source_version_id = job.source_version_id
      and version.source_id = p_source_id
      and job.status = 'pending_start';
    select count(*) into active_count from public.ingestion_jobs job join public.source_versions version on version.source_version_id = job.source_version_id where version.source_id = p_source_id and job.status in ('pending_start', 'queued', 'running', 'paused');
    if active_count > 0 then raise exception using errcode = '55000', message = 'pause or cancel processing before deleting'; end if;
    update public.sources set is_active = false, updated_by = auth.uid() where source_id = p_source_id and is_active;
    get diagnostics archived_count = row_count;
    update public.source_versions set parse_status = 'archived', updated_by = auth.uid() where source_id = p_source_id and parse_status <> 'archived';
    return jsonb_build_object('sourceId', p_source_id, 'archived', archived_count > 0, 'recoverable', true);
end; $$;

create or replace function public.get_source_ingestion_job_state(p_job_id uuid)
returns jsonb language plpgsql security definer stable set search_path = '' as $$
declare job_row public.ingestion_jobs%rowtype;
begin
    if coalesce(auth.role(), '') <> 'service_role' then raise exception using errcode = '42501', message = 'service role required'; end if;
    select * into job_row from public.ingestion_jobs where job_id = p_job_id;
    if not found then raise exception using errcode = 'P0002', message = 'job not found'; end if;
    return jsonb_build_object('jobId', job_row.job_id, 'jobStatus', job_row.status, 'sourceVersionId', job_row.source_version_id);
end; $$;

-- Inactive sources remain auditable and recoverable, but are no longer exposed in
-- the admin catalog. Storage objects are removed by the explicit UI action only.
create or replace view public.source_catalog_overview with (security_invoker = true) as
select source.*, coalesce(version_counts.version_count, 0) as version_count,
    latest_version.source_version_id as latest_source_version_id, latest_version.created_at as latest_version_at,
    coalesce(latest_version.parse_status, 'ready'::public.source_parse_status) as latest_parse_status,
    latest_version.byte_size as latest_byte_size, latest_version.extraction_metadata as latest_extraction_metadata,
    coalesce(element_counts.element_count, 0) as linked_element_count,
    latest_job.job_id as latest_job_id, latest_job.job_kind as latest_job_kind, latest_job.status as latest_job_status,
    latest_job.progress_percent as latest_job_progress_percent, latest_job.output ->> 'stage' as latest_processing_stage,
    latest_job.error_message as latest_job_error_message, latest_job.updated_at as latest_job_updated_at,
    candidate_counts.candidate_count, top_candidate.element_id as top_candidate_element_id, top_candidate.score as top_candidate_score
from public.sources source
left join lateral (select count(*)::integer as version_count from public.source_versions version where version.source_id = source.source_id) version_counts on true
left join lateral (select version.* from public.source_versions version where version.source_id = source.source_id order by version.version_number desc, version.created_at desc, version.source_version_id desc limit 1) latest_version on true
left join lateral (select count(*)::integer as element_count from public.element_sources link where link.source_id = source.source_id) element_counts on true
left join lateral (select job.* from public.ingestion_jobs job where job.source_version_id = latest_version.source_version_id order by job.created_at desc, job.job_id desc limit 1) latest_job on true
left join lateral (select count(*)::integer as candidate_count from public.source_element_candidates candidate where candidate.source_version_id = latest_version.source_version_id) candidate_counts on true
left join lateral (select candidate.element_id, candidate.score from public.source_element_candidates candidate where candidate.source_version_id = latest_version.source_version_id order by candidate.rank, candidate.score desc limit 1) top_candidate on true
where source.is_active;

grant execute on function public.control_source_ingestion_job(uuid, text) to authenticated;
grant execute on function public.archive_unconnected_source(text) to authenticated;
grant execute on function public.get_source_ingestion_job_state(uuid) to service_role;

commit;
