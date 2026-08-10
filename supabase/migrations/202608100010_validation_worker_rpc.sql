begin;

-- Normalize direct/default RPC callers to the validator contract used by the
-- Admin route and the worker. The original 005 migration intentionally remains
-- historical; this corrective definition changes only the default metadata.
create or replace function public.start_revision_validation(
    p_revision_id uuid,
    p_validator_name text default 'findone-content-validator',
    p_validator_version text default 'admin-v1'
)
returns public.validation_runs
language plpgsql
security definer
set search_path = ''
as $$
declare
    result public.validation_runs%rowtype;
begin
    if not public.has_admin_role(array['owner', 'editor', 'reviewer']::public.admin_role[]) then
        raise exception using errcode = '42501', message = 'admin role required';
    end if;
    if public.current_revision_state(p_revision_id) not in ('draft', 'validation_failed') then
        raise exception using errcode = '23514', message = 'revision is not ready for validation';
    end if;

    insert into public.validation_runs (
        target_type, revision_id, validator_name, validator_version, created_by
    ) values (
        'revision', p_revision_id, p_validator_name, p_validator_version, auth.uid()
    ) returning * into result;

    insert into public.ingestion_jobs (
        job_kind, revision_id, input, created_by
    ) values (
        'content_validation',
        p_revision_id,
        jsonb_build_object('validationRunId', result.validation_run_id),
        auth.uid()
    );
    return result;
end;
$$;

-- Only non-network worker classes may be claimed through this RPC. URL fetch and
-- file extraction require SSRF/file sandboxing that this worker intentionally does not provide.
create or replace function public.claim_ingestion_job(
    p_worker_id text,
    p_allowed_job_kinds public.job_kind[] default array['content_validation'::public.job_kind]
)
returns public.ingestion_jobs
language plpgsql
security definer
set search_path = ''
as $$
declare
    candidate_job_id uuid;
    claimed_job public.ingestion_jobs%rowtype;
    exhausted_job public.ingestion_jobs%rowtype;
    validation_run_id_value uuid;
    lease_cutoff timestamptz := clock_timestamp() - interval '15 minutes';
begin
    if coalesce(auth.role(), '') <> 'service_role' then
        raise exception using errcode = '42501', message = 'service role required';
    end if;
    if p_worker_id is null
       or p_worker_id !~ '^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$' then
        raise exception using errcode = '22023', message = 'invalid worker id';
    end if;
    if coalesce(cardinality(p_allowed_job_kinds), 0) = 0
       or exists (
           select 1
           from unnest(p_allowed_job_kinds) as allowed(kind)
           where allowed.kind is null
              or allowed.kind not in (
               'content_validation'::public.job_kind,
               'spreadsheet_export'::public.job_kind,
               'release_build'::public.job_kind,
               'release_validation'::public.job_kind
           )
       ) then
        raise exception using
            errcode = '22023',
            message = 'allowed job kinds must contain only non-network worker jobs';
    end if;

    -- Seal abandoned jobs that have no retry budget left. Issues must be inserted
    -- before the validation run becomes terminal (009 enforces that ordering).
    for exhausted_job in
        select job.*
        from public.ingestion_jobs as job
        where job.status = 'running'
          and job.job_kind = any (p_allowed_job_kinds)
          and job.attempt_count >= job.max_attempts
          and coalesce(job.claimed_at, job.started_at, job.updated_at, job.created_at) <= lease_cutoff
        order by coalesce(job.claimed_at, job.started_at, job.updated_at, job.created_at), job.job_id
        limit 10
        for update skip locked
    loop
        validation_run_id_value := null;
        if exhausted_job.job_kind = 'content_validation'
           and nullif(exhausted_job.input ->> 'validationRunId', '') is not null then
            begin
                validation_run_id_value := (exhausted_job.input ->> 'validationRunId')::uuid;
            exception when invalid_text_representation then
                validation_run_id_value := null;
            end;
            if validation_run_id_value is not null and exists (
                select 1
                from public.validation_runs as run
                where run.validation_run_id = validation_run_id_value
                  and run.revision_id = exhausted_job.revision_id
                  and run.status = 'running'
            ) then
                insert into public.validation_issues (
                    validation_run_id, severity, code, field_path, message, details
                ) values (
                    validation_run_id_value,
                    'error',
                    'worker_lease_exhausted',
                    null,
                    'validation worker lease expired and the retry budget was exhausted',
                    jsonb_build_object('jobId', exhausted_job.job_id)
                );
                update public.validation_runs
                set status = 'failed',
                    checks_total = 1,
                    checks_passed = 0,
                    checks_failed = 1,
                    summary = jsonb_build_object(
                        'workerFailure', true,
                        'leaseExpired', true,
                        'jobId', exhausted_job.job_id
                    )
                where validation_run_id = validation_run_id_value;
            end if;
        end if;
        update public.ingestion_jobs
        set status = 'failed',
            progress_percent = 100,
            error_message = 'worker lease expired and retry budget was exhausted',
            output = output || jsonb_build_object('workerFailure', true, 'leaseExpired', true)
        where job_id = exhausted_job.job_id;
    end loop;

    -- A stable worker id can recover a claim whose HTTP response was lost without
    -- incrementing attempts or claiming a second job.
    select job.* into claimed_job
    from public.ingestion_jobs as job
    where job.status = 'running'
      and job.claimed_by = p_worker_id
      and job.job_kind = any (p_allowed_job_kinds)
      and coalesce(job.claimed_at, job.started_at, job.updated_at, job.created_at) > lease_cutoff
    order by job.claimed_at, job.job_id
    for update
    limit 1;
    if found then
        return claimed_job;
    end if;

    -- A different process may reclaim an abandoned attempt after the bounded
    -- lease. This consumes another attempt but keeps the already-running
    -- validation run, so no invalid state transition is needed.
    select job.* into claimed_job
    from public.ingestion_jobs as job
    where job.status = 'running'
      and job.job_kind = any (p_allowed_job_kinds)
      and job.attempt_count < job.max_attempts
      and coalesce(job.claimed_at, job.started_at, job.updated_at, job.created_at) <= lease_cutoff
    order by coalesce(job.claimed_at, job.started_at, job.updated_at, job.created_at), job.job_id
    for update skip locked
    limit 1;
    if found then
        update public.ingestion_jobs
        set attempt_count = attempt_count + 1,
            progress_percent = 0,
            claimed_by = p_worker_id,
            claimed_at = clock_timestamp(),
            started_at = clock_timestamp(),
            completed_at = null,
            error_message = null,
            output = '{}'::jsonb
        where job_id = claimed_job.job_id
          and status = 'running'
        returning * into claimed_job;
        if not found then
            raise exception using errcode = '40001', message = 'stale job reclaim lost unexpectedly';
        end if;
        if claimed_job.job_kind = 'content_validation' and not exists (
            select 1
            from public.validation_runs as run
            where run.validation_run_id = (claimed_job.input ->> 'validationRunId')::uuid
              and run.revision_id = claimed_job.revision_id
              and run.status = 'running'
        ) then
            raise exception using
                errcode = '55000',
                message = 'stale validation job does not have a matching running validation run';
        end if;
        insert into public.job_events (job_id, status, level, message, payload)
        values (
            claimed_job.job_id,
            'running',
            'warning',
            'job lease reclaimed',
            jsonb_build_object('workerId', p_worker_id, 'attemptCount', claimed_job.attempt_count)
        );
        return claimed_job;
    end if;

    select job.job_id
    into candidate_job_id
    from public.ingestion_jobs as job
    where job.status = 'queued'
      and job.job_kind = any (p_allowed_job_kinds)
      and job.attempt_count < job.max_attempts
    order by job.created_at, job.job_id
    for update skip locked
    limit 1;

    if candidate_job_id is null then
        return null;
    end if;

    update public.ingestion_jobs
    set status = 'running',
        attempt_count = attempt_count + 1,
        progress_percent = 0,
        claimed_by = p_worker_id,
        claimed_at = clock_timestamp(),
        started_at = clock_timestamp(),
        completed_at = null,
        error_message = null,
        output = '{}'::jsonb
    where job_id = candidate_job_id
      and status = 'queued'
    returning * into claimed_job;

    if not found then
        raise exception using errcode = '40001', message = 'job claim lost unexpectedly';
    end if;

    if claimed_job.job_kind = 'content_validation' then
        if claimed_job.revision_id is null
           or nullif(claimed_job.input ->> 'validationRunId', '') is null then
            raise exception using
                errcode = '23514',
                message = 'content validation job target is incomplete';
        end if;
        begin
            validation_run_id_value := (claimed_job.input ->> 'validationRunId')::uuid;
        exception when invalid_text_representation then
            raise exception using
                errcode = '23514',
                message = 'content validation job has an invalid validation run id';
        end;

        update public.validation_runs
        set status = 'running'
        where validation_run_id = validation_run_id_value
          and target_type = 'revision'
          and revision_id = claimed_job.revision_id
          and status = 'queued';
        if not found then
            raise exception using
                errcode = '55000',
                message = 'matching queued validation run was not found';
        end if;
    end if;

    return claimed_job;
end;
$$;

create or replace function public.complete_content_validation_job(
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
    expected_run_id uuid;
begin
    if coalesce(auth.role(), '') <> 'service_role' then
        raise exception using errcode = '42501', message = 'service role required';
    end if;
    if p_worker_id is null
       or p_worker_id !~ '^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$' then
        raise exception using errcode = '22023', message = 'invalid worker id';
    end if;

    select * into job_row
    from public.ingestion_jobs
    where job_id = p_job_id
    for update;
    if not found then
        raise exception using errcode = 'P0002', message = 'job not found';
    end if;
    if job_row.job_kind <> 'content_validation'
       or job_row.claimed_by is distinct from p_worker_id then
        raise exception using errcode = '55000', message = 'job is not owned by this validation worker';
    end if;
    begin
        expected_run_id := (job_row.input ->> 'validationRunId')::uuid;
    exception when invalid_text_representation then
        raise exception using errcode = '23514', message = 'job validation run id is invalid';
    end;
    if expected_run_id is distinct from p_validation_run_id then
        raise exception using errcode = '55000', message = 'validation run does not match the claimed job';
    end if;
    if job_row.status = 'succeeded' then
        if job_row.output ->> 'validationRunId' is distinct from p_validation_run_id::text
           or job_row.output ->> 'validationStatus' is distinct from p_validation_status::text
           or job_row.output ->> 'checksTotal' is distinct from p_checks_total::text
           or job_row.output ->> 'checksPassed' is distinct from p_checks_passed::text
           or job_row.output ->> 'checksFailed' is distinct from p_checks_failed::text
           or not exists (
               select 1
               from public.validation_runs as completed_run
               where completed_run.validation_run_id = p_validation_run_id
                 and completed_run.status = p_validation_status
                 and completed_run.checks_total = p_checks_total
                 and completed_run.checks_passed = p_checks_passed
                 and completed_run.checks_failed = p_checks_failed
           ) then
            raise exception using
                errcode = '55000',
                message = 'completed validation result differs from the idempotent retry';
        end if;
        return jsonb_build_object(
            'jobId', p_job_id,
            'jobStatus', 'succeeded',
            'validationRunId', p_validation_run_id,
            'validationStatus', p_validation_status,
            'alreadyTerminal', true
        );
    end if;
    if job_row.status <> 'running' then
        raise exception using errcode = '55000', message = 'validation job is not running';
    end if;
    if not exists (
        select 1
        from public.content_revisions as revision
        where revision.revision_id = job_row.revision_id
          and revision.content_hash = encode(
              extensions.digest(convert_to(revision.snapshot::text, 'UTF8'), 'sha256'),
              'hex'
          )
    ) then
        raise exception using
            errcode = '55000',
            message = 'revision snapshot hash does not match its stored content hash';
    end if;

    select * into run_row
    from public.validation_runs
    where validation_run_id = p_validation_run_id
    for update;
    if not found
       or run_row.status <> 'running'
       or run_row.target_type <> 'revision'
       or run_row.revision_id is distinct from job_row.revision_id then
        raise exception using errcode = '55000', message = 'validation run is not active for the claimed revision';
    end if;

    if p_validation_status is null
       or p_validation_status not in ('passed', 'failed')
       or p_checks_total is null
       or p_checks_passed is null
       or p_checks_failed is null
       or p_checks_total < 1
       or p_checks_passed < 0
       or p_checks_failed < 0
       or p_checks_passed + p_checks_failed <> p_checks_total
       or (p_validation_status = 'passed' and p_checks_failed <> 0)
       or (p_validation_status = 'failed' and p_checks_failed < 1) then
        raise exception using errcode = '22023', message = 'invalid validation result counts';
    end if;
    if p_summary is null
       or p_issues is null
       or p_output is null
       or jsonb_typeof(p_summary) <> 'object'
       or jsonb_typeof(p_issues) <> 'array'
       or jsonb_typeof(p_output) <> 'object' then
        raise exception using errcode = '22023', message = 'validation result payload has an invalid shape';
    end if;
    if octet_length(p_summary::text) > 65536
       or octet_length(p_issues::text) > 262144
       or octet_length(p_output::text) > 65536
       or jsonb_array_length(p_issues) > 100 then
        raise exception using errcode = '22023', message = 'validation result payload exceeds its safety limit';
    end if;
    if exists (
        select 1
        from jsonb_array_elements(p_issues) as item(issue)
        where jsonb_typeof(item.issue) <> 'object'
           or coalesce(item.issue ->> 'severity', '') not in ('info', 'warning', 'error')
           or nullif(btrim(item.issue ->> 'code'), '') is null
           or length(item.issue ->> 'code') > 128
           or length(coalesce(item.issue ->> 'fieldPath', '')) > 512
           or nullif(btrim(item.issue ->> 'message'), '') is null
           or length(item.issue ->> 'message') > 2000
           or jsonb_typeof(coalesce(item.issue -> 'details', '{}'::jsonb)) <> 'object'
    ) then
        raise exception using errcode = '22023', message = 'validation issue payload is invalid';
    end if;

    select count(*)::integer into error_issue_count
    from jsonb_array_elements(p_issues) as item(issue)
    where item.issue ->> 'severity' = 'error';
    if (p_validation_status = 'passed' and error_issue_count <> 0)
       or (p_validation_status = 'failed' and error_issue_count < 1) then
        raise exception using errcode = '22023', message = 'validation status and error issues disagree';
    end if;

    for issue_value in select value from jsonb_array_elements(p_issues)
    loop
        insert into public.validation_issues (
            validation_run_id,
            severity,
            code,
            field_path,
            message,
            details
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
    set status = 'succeeded',
        progress_percent = 100,
        output = p_output || jsonb_build_object(
            'validationRunId', p_validation_run_id,
            'validationStatus', p_validation_status,
            'checksTotal', p_checks_total,
            'checksPassed', p_checks_passed,
            'checksFailed', p_checks_failed
        ),
        error_message = null
    where job_id = p_job_id;

    return jsonb_build_object(
        'jobId', p_job_id,
        'jobStatus', 'succeeded',
        'validationRunId', p_validation_run_id,
        'validationStatus', p_validation_status
    );
end;
$$;

create or replace function public.fail_ingestion_job(
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
    validation_run_id_value uuid;
    safe_message text;
    run_status public.validation_status;
begin
    if coalesce(auth.role(), '') <> 'service_role' then
        raise exception using errcode = '42501', message = 'service role required';
    end if;
    if p_worker_id is null
       or p_worker_id !~ '^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$' then
        raise exception using errcode = '22023', message = 'invalid worker id';
    end if;
    safe_message := left(nullif(btrim(p_error_message), ''), 2000);
    if safe_message is null then
        raise exception using errcode = '22023', message = 'failure message is required';
    end if;
    if p_output is null
       or jsonb_typeof(p_output) <> 'object'
       or octet_length(p_output::text) > 65536 then
        raise exception using errcode = '22023', message = 'failure output exceeds its safety limit';
    end if;

    select * into job_row
    from public.ingestion_jobs
    where job_id = p_job_id
    for update;
    if not found then
        raise exception using errcode = 'P0002', message = 'job not found';
    end if;
    if job_row.claimed_by is distinct from p_worker_id then
        raise exception using errcode = '55000', message = 'job is not owned by this worker';
    end if;

    if job_row.job_kind = 'content_validation'
       and nullif(job_row.input ->> 'validationRunId', '') is not null then
        begin
            validation_run_id_value := (job_row.input ->> 'validationRunId')::uuid;
        exception when invalid_text_representation then
            validation_run_id_value := null;
        end;
    end if;
    if job_row.status in ('succeeded', 'failed') then
        return jsonb_build_object(
            'jobId', p_job_id,
            'jobStatus', job_row.status,
            'validationRunId', validation_run_id_value,
            'validationStatus', job_row.output ->> 'validationStatus',
            'alreadyTerminal', true
        );
    end if;
    if job_row.status <> 'running' then
        raise exception using errcode = '55000', message = 'job is not running';
    end if;

    if job_row.job_kind = 'content_validation'
       and validation_run_id_value is not null then
        select status into run_status
        from public.validation_runs
        where validation_run_id = validation_run_id_value
          and revision_id = job_row.revision_id
        for update;
        if found and run_status = 'queued' then
            update public.validation_runs
            set status = 'running'
            where validation_run_id = validation_run_id_value;
            run_status := 'running';
        end if;
        if found and run_status = 'running' then
            insert into public.validation_issues (
                validation_run_id, severity, code, field_path, message, details
            ) values (
                validation_run_id_value,
                'error',
                'worker_failure',
                null,
                safe_message,
                jsonb_build_object('jobId', p_job_id)
            );
            update public.validation_runs
            set status = 'failed',
                checks_total = 1,
                checks_passed = 0,
                checks_failed = 1,
                summary = jsonb_build_object('workerFailure', true, 'jobId', p_job_id)
            where validation_run_id = validation_run_id_value;
        end if;
    end if;

    update public.ingestion_jobs
    set status = 'failed',
        error_message = safe_message,
        output = p_output || jsonb_build_object('workerFailure', true),
        progress_percent = 100
    where job_id = p_job_id;

    return jsonb_build_object(
        'jobId', p_job_id,
        'jobStatus', 'failed',
        'validationRunId', validation_run_id_value
    );
end;
$$;

revoke all on function public.claim_ingestion_job(text, public.job_kind[]) from public, anon, authenticated;
revoke all on function public.start_revision_validation(uuid, text, text) from public;
revoke all on function public.complete_content_validation_job(
    uuid, text, uuid, public.validation_status, integer, integer, integer, jsonb, jsonb, jsonb
) from public, anon, authenticated;
revoke all on function public.fail_ingestion_job(uuid, text, text, jsonb) from public, anon, authenticated;

grant execute on function public.claim_ingestion_job(text, public.job_kind[]) to service_role;
grant execute on function public.start_revision_validation(uuid, text, text) to authenticated, service_role;
grant execute on function public.complete_content_validation_job(
    uuid, text, uuid, public.validation_status, integer, integer, integer, jsonb, jsonb, jsonb
) to service_role;
grant execute on function public.fail_ingestion_job(uuid, text, text, jsonb) to service_role;

commit;
