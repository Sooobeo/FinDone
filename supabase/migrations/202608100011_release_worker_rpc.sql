begin;

-- Service-role release workers are the only writers allowed to seal generated
-- SQLite artifacts or finish release validation.  The browser can request a
-- release, but it never receives the service key and never writes worker output.

create or replace function public.complete_release_build_job(
    p_job_id uuid,
    p_worker_id text,
    p_manifest jsonb,
    p_manifest_sha256 text,
    p_manifest_byte_size bigint,
    p_database_sha256 text,
    p_database_byte_size bigint,
    p_database_object_path text,
    p_manifest_object_path text,
    p_output jsonb default '{}'::jsonb
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
    job_row public.ingestion_jobs%rowtype;
    release_row public.content_releases%rowtype;
    validation_run public.validation_runs%rowtype;
    validation_job_id uuid;
begin
    if coalesce(auth.role(), '') <> 'service_role' then
        raise exception using errcode = '42501', message = 'service role required';
    end if;
    if p_worker_id is null
       or p_worker_id !~ '^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$' then
        raise exception using errcode = '22023', message = 'invalid worker id';
    end if;
    if p_manifest is null or jsonb_typeof(p_manifest) <> 'object'
       or octet_length(p_manifest::text) > 262144
       or p_output is null or jsonb_typeof(p_output) <> 'object'
       or octet_length(p_output::text) > 65536 then
        raise exception using errcode = '22023', message = 'release build payload is invalid';
    end if;
    if p_manifest_sha256 !~ '^[0-9a-f]{64}$'
       or p_database_sha256 !~ '^[0-9a-f]{64}$'
       or p_manifest_byte_size is null or p_manifest_byte_size < 1
       or p_database_byte_size is null or p_database_byte_size < 1 then
        raise exception using errcode = '22023', message = 'release artifact identity is invalid';
    end if;
    if p_database_object_path !~ '^[0-9a-f-]{36}/content\.sqlite3$'
       or p_manifest_object_path !~ '^[0-9a-f-]{36}/content-manifest\.json$' then
        raise exception using errcode = '22023', message = 'release artifact path is invalid';
    end if;

    select * into job_row
    from public.ingestion_jobs
    where job_id = p_job_id
    for update;
    if not found then
        raise exception using errcode = 'P0002', message = 'job not found';
    end if;
    if job_row.job_kind <> 'release_build'
       or job_row.claimed_by is distinct from p_worker_id
       or job_row.release_id is null then
        raise exception using errcode = '55000', message = 'job is not owned by this release worker';
    end if;
    if job_row.status = 'succeeded' then
        return jsonb_build_object(
            'jobId', p_job_id,
            'jobStatus', 'succeeded',
            'releaseId', job_row.release_id,
            'alreadyTerminal', true
        );
    end if;
    if job_row.status <> 'running' then
        raise exception using errcode = '55000', message = 'release build job is not running';
    end if;

    perform pg_advisory_xact_lock(hashtextextended('release-build:' || job_row.release_id::text, 0));
    select * into release_row
    from public.content_releases
    where release_id = job_row.release_id
    for update;
    if not found or release_row.status <> 'building' then
        raise exception using errcode = '55000', message = 'release is not in building state';
    end if;
    if p_database_object_path <> (release_row.release_id::text || '/content.sqlite3')
       or p_manifest_object_path <> (release_row.release_id::text || '/content-manifest.json') then
        raise exception using errcode = '22023', message = 'artifact path does not match release id';
    end if;
    if (p_manifest ->> 'manifestVersion')::integer <> 1
       or (p_manifest ->> 'schemaVersion')::integer <> release_row.schema_version
       or (p_manifest ->> 'contentDbVersion')::integer <> release_row.content_version
       or p_manifest ->> 'databaseAsset' <> 'content.sqlite3'
       or p_manifest ->> 'sha256' <> p_database_sha256
       or (p_manifest ->> 'byteSize')::bigint <> p_database_byte_size
       or jsonb_typeof(p_manifest -> 'rowCounts') <> 'object'
       or jsonb_typeof(p_manifest -> 'domainElementCounts') <> 'object' then
        raise exception using errcode = '23514', message = 'manifest does not match release identity';
    end if;
    if not exists (
        select 1 from public.release_items as item
        join public.content_revisions as revision on revision.revision_id = item.revision_id
        where item.release_id = release_row.release_id
          and revision.entity_type = item.entity_type
          and revision.entity_key = item.entity_key
          and revision.revision_number = item.revision_number
          and revision.content_hash = item.content_hash
    ) then
        raise exception using errcode = '55000', message = 'release has no verified frozen items';
    end if;
    if exists (
        select 1 from public.release_items as item
        left join public.content_revisions as revision on revision.revision_id = item.revision_id
        where item.release_id = release_row.release_id
          and (
              revision.revision_id is null
              or revision.entity_type <> item.entity_type
              or revision.entity_key <> item.entity_key
              or revision.revision_number <> item.revision_number
              or revision.content_hash <> item.content_hash
          )
    ) then
        raise exception using errcode = '55000', message = 'release frozen item changed';
    end if;
    if not exists (
        select 1 from storage.objects
        where bucket_id = 'release-bundles' and name = p_database_object_path
    ) or not exists (
        select 1 from storage.objects
        where bucket_id = 'release-bundles' and name = p_manifest_object_path
    ) then
        raise exception using errcode = '55000', message = 'uploaded release objects were not found';
    end if;

    insert into public.release_artifacts (
        release_id, artifact_kind, bucket_id, object_path, mime_type, byte_size, sha256
    ) values
        (
            release_row.release_id, 'content_database', 'release-bundles',
            p_database_object_path, 'application/x-sqlite3',
            p_database_byte_size, p_database_sha256
        ),
        (
            release_row.release_id, 'manifest', 'release-bundles',
            p_manifest_object_path, 'application/json',
            p_manifest_byte_size, p_manifest_sha256
        )
    on conflict (release_id, artifact_kind) do update set
        object_path = excluded.object_path,
        mime_type = excluded.mime_type,
        byte_size = excluded.byte_size,
        sha256 = excluded.sha256;

    update public.content_releases
    set manifest = p_manifest,
        manifest_sha256 = p_manifest_sha256,
        database_sha256 = p_database_sha256,
        database_byte_size = p_database_byte_size
    where release_id = release_row.release_id;

    update public.ingestion_jobs
    set status = 'succeeded',
        progress_percent = 100,
        error_message = null,
        output = p_output || jsonb_build_object(
            'releaseId', release_row.release_id,
            'manifestSha256', p_manifest_sha256,
            'databaseSha256', p_database_sha256,
            'databaseByteSize', p_database_byte_size
        )
    where job_id = p_job_id;

    insert into public.validation_runs (
        target_type, release_id, validator_name, validator_version, created_by
    ) values (
        'release', release_row.release_id, 'findone-release-validator', 'admin-v1', null
    ) returning * into validation_run;

    insert into public.ingestion_jobs (job_kind, release_id, input, created_by)
    values (
        'release_validation', release_row.release_id,
        jsonb_build_object(
            'validationRunId', validation_run.validation_run_id,
            'releaseFingerprint', validation_run.release_fingerprint
        ),
        null
    ) returning job_id into validation_job_id;

    return jsonb_build_object(
        'jobId', p_job_id,
        'jobStatus', 'succeeded',
        'releaseId', release_row.release_id,
        'validationRunId', validation_run.validation_run_id,
        'validationJobId', validation_job_id
    );
end;
$$;

create or replace function public.complete_release_validation_job(
    p_job_id uuid,
    p_worker_id text,
    p_validation_run_id uuid,
    p_validation_status public.validation_status,
    p_checks_total integer,
    p_checks_passed integer,
    p_checks_failed integer,
    p_summary jsonb default '{}'::jsonb,
    p_issues jsonb default '[]'::jsonb,
    p_output jsonb default '{}'::jsonb
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
    job_row public.ingestion_jobs%rowtype;
    run_row public.validation_runs%rowtype;
    issue_value jsonb;
    error_issue_count integer;
    published boolean := false;
begin
    if coalesce(auth.role(), '') <> 'service_role' then
        raise exception using errcode = '42501', message = 'service role required';
    end if;
    if p_worker_id is null
       or p_worker_id !~ '^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$' then
        raise exception using errcode = '22023', message = 'invalid worker id';
    end if;
    if p_validation_status not in ('passed', 'failed')
       or p_checks_total < 1 or p_checks_passed < 0 or p_checks_failed < 0
       or p_checks_passed + p_checks_failed <> p_checks_total
       or (p_validation_status = 'passed' and p_checks_failed <> 0)
       or (p_validation_status = 'failed' and p_checks_failed < 1) then
        raise exception using errcode = '22023', message = 'invalid release validation counts';
    end if;
    if p_summary is null or jsonb_typeof(p_summary) <> 'object'
       or p_issues is null or jsonb_typeof(p_issues) <> 'array'
       or p_output is null or jsonb_typeof(p_output) <> 'object'
       or octet_length(p_summary::text) > 65536
       or octet_length(p_issues::text) > 262144
       or octet_length(p_output::text) > 65536
       or jsonb_array_length(p_issues) > 100 then
        raise exception using errcode = '22023', message = 'release validation payload is invalid';
    end if;
    if exists (
        select 1 from jsonb_array_elements(p_issues) as item(issue)
        where jsonb_typeof(item.issue) <> 'object'
           or coalesce(item.issue ->> 'severity', '') not in ('info', 'warning', 'error')
           or nullif(btrim(item.issue ->> 'code'), '') is null
           or nullif(btrim(item.issue ->> 'message'), '') is null
           or jsonb_typeof(coalesce(item.issue -> 'details', '{}'::jsonb)) <> 'object'
    ) then
        raise exception using errcode = '22023', message = 'release validation issue is invalid';
    end if;
    select count(*)::integer into error_issue_count
    from jsonb_array_elements(p_issues) as item(issue)
    where item.issue ->> 'severity' = 'error';
    if (p_validation_status = 'passed' and error_issue_count <> 0)
       or (p_validation_status = 'failed' and error_issue_count < 1) then
        raise exception using errcode = '22023', message = 'release validation status and issues disagree';
    end if;

    select * into job_row from public.ingestion_jobs
    where job_id = p_job_id for update;
    if not found then raise exception using errcode = 'P0002', message = 'job not found'; end if;
    if job_row.job_kind <> 'release_validation'
       or job_row.claimed_by is distinct from p_worker_id
       or job_row.release_id is null then
        raise exception using errcode = '55000', message = 'job is not owned by this release validator';
    end if;
    if job_row.status = 'succeeded' then
        return jsonb_build_object(
            'jobId', p_job_id, 'jobStatus', 'succeeded',
            'releaseId', job_row.release_id, 'alreadyTerminal', true
        );
    end if;
    if job_row.status <> 'running' then
        raise exception using errcode = '55000', message = 'release validation job is not running';
    end if;
    if (job_row.input ->> 'validationRunId')::uuid is distinct from p_validation_run_id then
        raise exception using errcode = '55000', message = 'validation run does not match release job';
    end if;

    select * into run_row from public.validation_runs
    where validation_run_id = p_validation_run_id for update;
    if not found or run_row.target_type <> 'release'
       or run_row.release_id is distinct from job_row.release_id
       or run_row.status not in ('queued', 'running') then
        raise exception using errcode = '55000', message = 'release validation run is not active';
    end if;
    if run_row.release_fingerprint is distinct from public.release_validation_fingerprint(job_row.release_id)
       or job_row.input ->> 'releaseFingerprint' is distinct from run_row.release_fingerprint then
        raise exception using errcode = '55000', message = 'release changed while validation was running';
    end if;

    if run_row.status = 'queued' then
        update public.validation_runs set status = 'running'
        where validation_run_id = p_validation_run_id;
    end if;
    for issue_value in select value from jsonb_array_elements(p_issues)
    loop
        insert into public.validation_issues (
            validation_run_id, severity, code, field_path, message, details
        ) values (
            p_validation_run_id,
            (issue_value ->> 'severity')::public.validation_severity,
            issue_value ->> 'code',
            nullif(issue_value ->> 'fieldPath', ''),
            issue_value ->> 'message',
            coalesce(issue_value -> 'details', '{}'::jsonb)
        );
    end loop;

    update public.validation_runs
    set status = p_validation_status,
        checks_total = p_checks_total,
        checks_passed = p_checks_passed,
        checks_failed = p_checks_failed,
        summary = p_summary
    where validation_run_id = p_validation_run_id;

    update public.ingestion_jobs
    set status = 'succeeded', progress_percent = 100, error_message = null,
        output = p_output || jsonb_build_object(
            'validationRunId', p_validation_run_id,
            'validationStatus', p_validation_status,
            'checksTotal', p_checks_total,
            'checksPassed', p_checks_passed,
            'checksFailed', p_checks_failed
        )
    where job_id = p_job_id;

    perform set_config('app.release_transition_authorized', '1', true);
    update public.content_releases
    set status = case when p_validation_status = 'passed' then 'ready'::public.release_status
                      else 'validation_failed'::public.release_status end
    where release_id = job_row.release_id;

    if p_validation_status = 'passed' then
        -- Creating a release is the explicit publication intent. Once the frozen
        -- snapshot passes validation, atomically promote it to stable so clients
        -- never observe an unvalidated bundle.
        perform pg_advisory_xact_lock(hashtextextended('release-channel:stable', 0));
        perform set_config('app.release_transition_authorized', '1', true);
        update public.content_releases
        set status = 'published'
        where release_id = job_row.release_id and status = 'ready';

        insert into public.release_channels (channel, release_id, activated_at, activated_by)
        values ('stable', job_row.release_id, clock_timestamp(), auth.uid())
        on conflict (channel) do update set
            release_id = excluded.release_id,
            activated_at = excluded.activated_at,
            activated_by = excluded.activated_by;

        insert into public.revision_state_events (revision_id, state, note, created_by)
        select item.revision_id, 'published',
               'automatically included in stable release ' || job_row.release_id::text,
               auth.uid()
        from public.release_items as item
        where item.release_id = job_row.release_id
          and public.current_revision_state(item.revision_id) = 'approved';
        published := true;
    end if;

    return jsonb_build_object(
        'jobId', p_job_id, 'jobStatus', 'succeeded',
        'releaseId', job_row.release_id,
        'validationRunId', p_validation_run_id,
        'validationStatus', p_validation_status,
        'releaseStatus', case when published then 'published'
                              else 'validation_failed' end,
        'channel', case when published then 'stable' else null end
    );
end;
$$;

create or replace function public.fail_release_job(
    p_job_id uuid,
    p_worker_id text,
    p_error_message text,
    p_output jsonb default '{}'::jsonb
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
    job_row public.ingestion_jobs%rowtype;
    run_id uuid;
    safe_message text;
begin
    if coalesce(auth.role(), '') <> 'service_role' then
        raise exception using errcode = '42501', message = 'service role required';
    end if;
    safe_message := left(nullif(btrim(p_error_message), ''), 2000);
    if safe_message is null then
        raise exception using errcode = '22023', message = 'failure message is required';
    end if;
    select * into job_row from public.ingestion_jobs
    where job_id = p_job_id for update;
    if not found then raise exception using errcode = 'P0002', message = 'job not found'; end if;
    if job_row.job_kind not in ('release_build', 'release_validation')
       or job_row.claimed_by is distinct from p_worker_id then
        raise exception using errcode = '55000', message = 'job is not owned by this release worker';
    end if;
    if job_row.status in ('succeeded', 'failed') then
        return jsonb_build_object('jobId', p_job_id, 'jobStatus', job_row.status, 'alreadyTerminal', true);
    end if;
    if job_row.status <> 'running' then
        raise exception using errcode = '55000', message = 'release job is not running';
    end if;

    if job_row.job_kind = 'release_validation'
       and nullif(job_row.input ->> 'validationRunId', '') is not null then
        begin run_id := (job_row.input ->> 'validationRunId')::uuid;
        exception when invalid_text_representation then run_id := null;
        end;
        if run_id is not null then
            update public.validation_runs set status = 'running'
            where validation_run_id = run_id and status = 'queued';
            insert into public.validation_issues (
                validation_run_id, severity, code, message, details
            )
            select run_id, 'error', 'release_worker_failure', safe_message,
                   jsonb_build_object('jobId', p_job_id)
            where exists (
                select 1 from public.validation_runs
                where validation_run_id = run_id and status = 'running'
            );
            update public.validation_runs
            set status = 'failed', checks_total = 1, checks_passed = 0, checks_failed = 1,
                summary = jsonb_build_object('workerFailure', true, 'jobId', p_job_id)
            where validation_run_id = run_id and status = 'running';
        end if;
    end if;

    update public.ingestion_jobs
    set status = 'failed', progress_percent = 100, error_message = safe_message,
        output = coalesce(p_output, '{}'::jsonb) || jsonb_build_object('workerFailure', true)
    where job_id = p_job_id;
    if job_row.release_id is not null then
        perform set_config('app.release_transition_authorized', '1', true);
        update public.content_releases set status = 'validation_failed'
        where release_id = job_row.release_id and status = 'building';
    end if;
    return jsonb_build_object('jobId', p_job_id, 'jobStatus', 'failed', 'releaseId', job_row.release_id);
end;
$$;

revoke all on function public.complete_release_build_job(
    uuid, text, jsonb, text, bigint, text, bigint, text, text, jsonb
) from public, anon, authenticated;
revoke all on function public.complete_release_validation_job(
    uuid, text, uuid, public.validation_status, integer, integer, integer, jsonb, jsonb, jsonb
) from public, anon, authenticated;
revoke all on function public.fail_release_job(uuid, text, text, jsonb)
from public, anon, authenticated;

grant execute on function public.complete_release_build_job(
    uuid, text, jsonb, text, bigint, text, bigint, text, text, jsonb
) to service_role;
grant execute on function public.complete_release_validation_job(
    uuid, text, uuid, public.validation_status, integer, integer, integer, jsonb, jsonb, jsonb
) to service_role;
grant execute on function public.fail_release_job(uuid, text, text, jsonb)
to service_role;

commit;
