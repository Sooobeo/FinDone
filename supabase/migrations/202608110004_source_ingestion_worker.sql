alter type public.source_parse_status
    add value if not exists 'needs_review' after 'extracting';

begin;

-- Parser output is immutable evidence. A worker replaces the whole set only
-- while its source version is non-terminal, then seals the version as ready or
-- needs_review in the same completion transaction.
create table public.source_fragments (
    source_fragment_id uuid primary key default gen_random_uuid(),
    source_version_id uuid not null references public.source_versions(source_version_id) on delete restrict,
    ordinal integer not null check (ordinal >= 0),
    fragment_kind text not null,
    locator jsonb not null default '{}'::jsonb,
    content_text text not null,
    normalized_text text not null,
    content_sha256 text not null,
    ocr_confidence numeric(5,4),
    search_vector tsvector generated always as (
        to_tsvector('simple'::regconfig, normalized_text)
    ) stored,
    created_at timestamptz not null default clock_timestamp(),
    created_by uuid references auth.users(id) on delete set null,
    constraint source_fragments_kind_check check (
        fragment_kind in ('text', 'table', 'formula', 'ocr')
    ),
    constraint source_fragments_locator_object check (jsonb_typeof(locator) = 'object'),
    constraint source_fragments_text_not_blank check (btrim(content_text) <> ''),
    constraint source_fragments_normalized_not_blank check (btrim(normalized_text) <> ''),
    constraint source_fragments_hash_format check (content_sha256 ~ '^[0-9a-f]{64}$'),
    constraint source_fragments_ocr_confidence check (
        ocr_confidence is null or ocr_confidence between 0 and 1
    ),
    constraint source_fragments_version_ordinal_unique unique (source_version_id, ordinal)
);

create table public.source_element_candidates (
    source_version_id uuid not null references public.source_versions(source_version_id) on delete restrict,
    element_id text not null references public.elements(element_id) on delete restrict,
    rank integer not null check (rank between 1 and 20),
    score numeric(6,5) not null check (score between 0 and 1),
    reason text not null default '',
    matched_terms jsonb not null default '[]'::jsonb,
    created_at timestamptz not null default clock_timestamp(),
    created_by uuid references auth.users(id) on delete set null,
    primary key (source_version_id, element_id),
    constraint source_element_candidates_rank_unique unique (source_version_id, rank),
    constraint source_element_candidates_terms_array check (jsonb_typeof(matched_terms) = 'array')
);

create index source_fragments_version_kind_idx
    on public.source_fragments(source_version_id, fragment_kind, ordinal);
create index source_fragments_search_idx
    on public.source_fragments using gin(search_vector);
create index source_element_candidates_version_score_idx
    on public.source_element_candidates(source_version_id, score desc, rank);

create trigger source_fragments_append_only
before update or delete on public.source_fragments
for each row execute function public.prevent_row_mutation();

create trigger source_element_candidates_append_only
before update or delete on public.source_element_candidates
for each row execute function public.prevent_row_mutation();

alter table public.source_fragments enable row level security;
alter table public.source_element_candidates enable row level security;

create policy source_fragments_owner_select
on public.source_fragments for select to authenticated
using ((select public.is_admin()));

create policy source_element_candidates_owner_select
on public.source_element_candidates for select to authenticated
using ((select public.is_admin()));

grant select on public.source_fragments, public.source_element_candidates to authenticated;
grant select, insert, delete on public.source_fragments, public.source_element_candidates to service_role;

-- One immutable Storage object may back multiple source-version aliases with
-- the same SHA-256. This is the archive-level deduplication contract.
alter table public.source_files
    drop constraint if exists source_files_object_unique;
create index if not exists source_files_object_lookup_idx
    on public.source_files(bucket_id, object_path);

create or replace function public.find_reusable_source_file(
    p_sha256 text,
    p_byte_size bigint
)
returns jsonb
language plpgsql
security definer
stable
set search_path = ''
as $$
declare
    reusable jsonb;
begin
    if not public.has_admin_role(array['owner', 'editor']::public.admin_role[]) then
        raise exception using errcode = '42501', message = 'editor role required';
    end if;
    if auth.uid() is null
       or coalesce(p_sha256, '') !~ '^[0-9a-f]{64}$'
       or p_byte_size < 1 then
        raise exception using errcode = '22023', message = 'invalid source hash lookup';
    end if;

    select jsonb_build_object(
        'objectPath', file.object_path,
        'sourceVersionId', file.source_version_id,
        'parseStatus', version.parse_status,
        'originalFilename', file.original_filename
    ) into reusable
    from public.source_files as file
    join public.source_versions as version
      on version.source_version_id = file.source_version_id
    join storage.objects as object
      on object.bucket_id = file.bucket_id
     and object.name = file.object_path
    where file.file_role in ('original', 'snapshot')
      and file.bucket_id = 'source-private'
      and file.sha256 = p_sha256
      and file.byte_size = p_byte_size
      and version.parse_status <> 'failed'
      and split_part(file.object_path, '/', 1) = auth.uid()::text
      and object.metadata ->> 'size' = p_byte_size::text
    order by
        (version.parse_status in ('ready', 'needs_review')) desc,
        file.created_at,
        file.source_file_id
    limit 1;

    return reusable;
end;
$$;

create or replace function public.claim_source_ingestion_job(
    p_worker_id text
)
returns public.ingestion_jobs
language plpgsql
security definer
set search_path = ''
as $$
declare
    candidate_job public.ingestion_jobs%rowtype;
    exhausted_job public.ingestion_jobs%rowtype;
    lease_cutoff timestamptz := clock_timestamp() - interval '20 minutes';
begin
    if coalesce(auth.role(), '') <> 'service_role' then
        raise exception using errcode = '42501', message = 'service role required';
    end if;
    if p_worker_id is null
       or p_worker_id !~ '^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$' then
        raise exception using errcode = '22023', message = 'invalid worker id';
    end if;

    -- Seal abandoned jobs that exhausted their retry budget before looking for
    -- another claim. This prevents a source from displaying an eternal spinner.
    for exhausted_job in
        select job.*
        from public.ingestion_jobs as job
        where job.job_kind in ('file_extract', 'url_fetch')
          and job.status = 'running'
          and job.attempt_count >= job.max_attempts
          and coalesce(job.claimed_at, job.started_at, job.updated_at, job.created_at) <= lease_cutoff
        order by coalesce(job.claimed_at, job.started_at, job.updated_at, job.created_at), job.job_id
        limit 10
        for update skip locked
    loop
        update public.source_versions
        set parse_status = 'failed',
            failure_message = 'source worker lease expired and retry budget was exhausted'
        where source_version_id = exhausted_job.source_version_id
          and parse_status not in ('ready', 'archived');

        update public.ingestion_jobs
        set status = 'failed',
            progress_percent = 100,
            error_message = 'source worker lease expired and retry budget was exhausted',
            output = output || jsonb_build_object(
                'stage', 'failed',
                'workerFailure', true,
                'leaseExpired', true
            )
        where job_id = exhausted_job.job_id;
    end loop;

    -- Recover a recent claim made by the same stable worker ID. This makes a
    -- lost HTTP response idempotent without consuming another attempt.
    select job.* into candidate_job
    from public.ingestion_jobs as job
    where job.job_kind in ('file_extract', 'url_fetch')
      and job.status = 'running'
      and job.claimed_by = p_worker_id
      and coalesce(job.claimed_at, job.started_at, job.updated_at, job.created_at) > lease_cutoff
    order by job.claimed_at, job.job_id
    limit 1
    for update;
    if found then
        return candidate_job;
    end if;

    -- Reclaim an abandoned attempt while preserving the original job identity.
    select job.* into candidate_job
    from public.ingestion_jobs as job
    where job.job_kind in ('file_extract', 'url_fetch')
      and job.status = 'running'
      and job.attempt_count < job.max_attempts
      and coalesce(job.claimed_at, job.started_at, job.updated_at, job.created_at) <= lease_cutoff
    order by coalesce(job.claimed_at, job.started_at, job.updated_at, job.created_at), job.job_id
    limit 1
    for update skip locked;
    if found then
        update public.ingestion_jobs
        set attempt_count = attempt_count + 1,
            progress_percent = 1,
            claimed_by = p_worker_id,
            claimed_at = clock_timestamp(),
            started_at = clock_timestamp(),
            completed_at = null,
            error_message = null,
            output = jsonb_build_object('stage', 'starting', 'reclaimed', true)
        where job_id = candidate_job.job_id
        returning * into candidate_job;

        update public.source_versions
        set parse_status = case
                when candidate_job.job_kind = 'url_fetch' then 'fetching'::public.source_parse_status
                else 'extracting'::public.source_parse_status
            end,
            failure_message = null
        where source_version_id = candidate_job.source_version_id
          and parse_status not in ('ready', 'archived');

        insert into public.job_events (job_id, status, level, message, payload)
        values (
            candidate_job.job_id,
            'running',
            'warning',
            'source extraction lease reclaimed',
            jsonb_build_object('workerId', p_worker_id, 'attemptCount', candidate_job.attempt_count)
        );
        return candidate_job;
    end if;

    select job.* into candidate_job
    from public.ingestion_jobs as job
    where job.job_kind in ('file_extract', 'url_fetch')
      and job.status = 'queued'
      and job.attempt_count < job.max_attempts
    order by job.created_at, job.job_id
    limit 1
    for update skip locked;
    if not found then
        return null;
    end if;

    update public.ingestion_jobs
    set status = 'running',
        attempt_count = attempt_count + 1,
        progress_percent = 1,
        claimed_by = p_worker_id,
        claimed_at = clock_timestamp(),
        started_at = clock_timestamp(),
        completed_at = null,
        error_message = null,
        output = jsonb_build_object('stage', 'starting')
    where job_id = candidate_job.job_id
      and status = 'queued'
    returning * into candidate_job;
    if not found then
        raise exception using errcode = '40001', message = 'source job claim was lost';
    end if;

    update public.source_versions
    set parse_status = case
            when candidate_job.job_kind = 'url_fetch' then 'fetching'::public.source_parse_status
            else 'extracting'::public.source_parse_status
        end,
        failure_message = null
    where source_version_id = candidate_job.source_version_id
      and parse_status not in ('ready', 'archived');

    return candidate_job;
end;
$$;

create or replace function public.update_source_ingestion_progress(
    p_job_id uuid,
    p_worker_id text,
    p_progress_percent integer,
    p_stage text,
    p_details jsonb default '{}'::jsonb
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
    job_row public.ingestion_jobs%rowtype;
    previous_stage text;
begin
    if coalesce(auth.role(), '') <> 'service_role' then
        raise exception using errcode = '42501', message = 'service role required';
    end if;
    if p_progress_percent not between 1 and 99 then
        raise exception using errcode = '22023', message = 'progress must be between 1 and 99';
    end if;
    if p_stage not in (
        'starting', 'downloading', 'validating', 'archiving', 'deduplicating',
        'extracting', 'ocr', 'normalizing', 'matching', 'saving'
    ) then
        raise exception using errcode = '22023', message = 'unknown source processing stage';
    end if;
    if p_details is null
       or jsonb_typeof(p_details) <> 'object'
       or octet_length(p_details::text) > 16384 then
        raise exception using errcode = '22023', message = 'progress details are invalid';
    end if;

    select * into job_row
    from public.ingestion_jobs
    where job_id = p_job_id
    for update;
    if not found then
        raise exception using errcode = 'P0002', message = 'job not found';
    end if;
    if job_row.job_kind not in ('file_extract', 'url_fetch')
       or job_row.status <> 'running'
       or job_row.claimed_by is distinct from p_worker_id
       or job_row.source_version_id is null then
        raise exception using errcode = '55000', message = 'source job is not owned by this worker';
    end if;

    previous_stage := job_row.output ->> 'stage';
    update public.ingestion_jobs
    set progress_percent = greatest(progress_percent, p_progress_percent),
        claimed_at = clock_timestamp(),
        output = output || p_details || jsonb_build_object('stage', p_stage)
    where job_id = p_job_id;

    if previous_stage is distinct from p_stage then
        insert into public.job_events (job_id, status, level, message, payload)
        values (
            p_job_id,
            'running',
            'info',
            'source processing stage: ' || p_stage,
            p_details || jsonb_build_object('progressPercent', p_progress_percent)
        );
    end if;

    return jsonb_build_object(
        'jobId', p_job_id,
        'jobStatus', 'running',
        'progressPercent', greatest(job_row.progress_percent, p_progress_percent),
        'stage', p_stage
    );
end;
$$;

create or replace function public.complete_source_ingestion_job(
    p_job_id uuid,
    p_worker_id text,
    p_extracted_text text,
    p_extraction_metadata jsonb,
    p_fragments jsonb,
    p_candidates jsonb default '[]'::jsonb,
    p_requires_review boolean default false,
    p_output jsonb default '{}'::jsonb
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
    job_row public.ingestion_jobs%rowtype;
    version_row public.source_versions%rowtype;
    fragment_value jsonb;
    candidate_value jsonb;
    fragment_count integer;
    candidate_count integer;
    auto_link_element_id text;
begin
    if coalesce(auth.role(), '') <> 'service_role' then
        raise exception using errcode = '42501', message = 'service role required';
    end if;
    if p_extracted_text is null
       or octet_length(p_extracted_text) > 8388608
       or (not p_requires_review and nullif(btrim(p_extracted_text), '') is null) then
        raise exception using errcode = '22023', message = 'extracted text is invalid';
    end if;
    if p_extraction_metadata is null
       or jsonb_typeof(p_extraction_metadata) <> 'object'
       or octet_length(p_extraction_metadata::text) > 524288 then
        raise exception using errcode = '22023', message = 'extraction metadata is invalid';
    end if;
    if p_fragments is null
       or jsonb_typeof(p_fragments) <> 'array'
       or octet_length(p_fragments::text) > 8388608 then
        raise exception using errcode = '22023', message = 'source fragments are invalid';
    end if;
    if p_candidates is null
       or jsonb_typeof(p_candidates) <> 'array'
       or octet_length(p_candidates::text) > 131072 then
        raise exception using errcode = '22023', message = 'source candidates are invalid';
    end if;
    if p_output is null
       or jsonb_typeof(p_output) <> 'object'
       or octet_length(p_output::text) > 65536 then
        raise exception using errcode = '22023', message = 'source job output is invalid';
    end if;

    fragment_count := jsonb_array_length(p_fragments);
    candidate_count := jsonb_array_length(p_candidates);
    if fragment_count > 4000
       or (fragment_count = 0 and not p_requires_review)
       or candidate_count > 20 then
        raise exception using errcode = '22023', message = 'source result count is invalid';
    end if;

    for fragment_value in select value from jsonb_array_elements(p_fragments)
    loop
        if jsonb_typeof(fragment_value) <> 'object'
           or coalesce(fragment_value ->> 'kind', '') not in ('text', 'table', 'formula', 'ocr')
           or nullif(btrim(fragment_value ->> 'text'), '') is null
           or octet_length(fragment_value ->> 'text') > 131072
           or jsonb_typeof(coalesce(fragment_value -> 'locator', '{}'::jsonb)) <> 'object'
           or (
               fragment_value ? 'ocrConfidence'
               and (
                   jsonb_typeof(fragment_value -> 'ocrConfidence') <> 'number'
                   or (fragment_value ->> 'ocrConfidence')::numeric not between 0 and 1
               )
           ) then
            raise exception using errcode = '22023', message = 'source fragment item is invalid';
        end if;
    end loop;

    for candidate_value in select value from jsonb_array_elements(p_candidates)
    loop
        if jsonb_typeof(candidate_value) <> 'object'
           or nullif(candidate_value ->> 'elementId', '') is null
           or jsonb_typeof(candidate_value -> 'rank') <> 'number'
           or (candidate_value ->> 'rank')::integer not between 1 and 20
           or jsonb_typeof(candidate_value -> 'score') <> 'number'
           or (candidate_value ->> 'score')::numeric not between 0 and 1
           or jsonb_typeof(coalesce(candidate_value -> 'matchedTerms', '[]'::jsonb)) <> 'array'
           or octet_length(coalesce(candidate_value ->> 'reason', '')) > 1000
           or not exists (
               select 1 from public.elements
               where element_id = candidate_value ->> 'elementId'
           ) then
            raise exception using errcode = '22023', message = 'source candidate item is invalid';
        end if;
    end loop;

    select * into job_row
    from public.ingestion_jobs
    where job_id = p_job_id
    for update;
    if not found then
        raise exception using errcode = 'P0002', message = 'job not found';
    end if;
    if job_row.status = 'succeeded' then
        return jsonb_build_object(
            'jobId', p_job_id,
            'jobStatus', 'succeeded',
            'sourceVersionId', job_row.source_version_id,
            'alreadyTerminal', true
        );
    end if;
    if job_row.job_kind not in ('file_extract', 'url_fetch')
       or job_row.status <> 'running'
       or job_row.claimed_by is distinct from p_worker_id
       or job_row.source_version_id is null then
        raise exception using errcode = '55000', message = 'source job is not owned by this worker';
    end if;

    select * into version_row
    from public.source_versions
    where source_version_id = job_row.source_version_id
    for update;
    if not found then
        raise exception using errcode = 'P0002', message = 'source version not found';
    end if;
    if job_row.job_kind = 'url_fetch' then
        if not case
               when jsonb_typeof(p_extraction_metadata -> 'sourceByteSize') = 'number'
                    and (p_extraction_metadata ->> 'sourceByteSize') ~ '^[0-9]{1,11}$'
               then (p_extraction_metadata ->> 'sourceByteSize')::bigint between 1 and 10737418240
               else false
           end
           or coalesce(p_extraction_metadata ->> 'sourceSha256', '') !~ '^[0-9a-f]{64}$'
           or nullif(btrim(p_extraction_metadata ->> 'snapshotObjectPath'), '') is null
           or octet_length(p_extraction_metadata ->> 'snapshotObjectPath') > 1024
           or version_row.created_by is null
           or split_part(p_extraction_metadata ->> 'snapshotObjectPath', '/', 1) <> version_row.created_by::text
           or nullif(btrim(p_extraction_metadata ->> 'originalFilename'), '') is null
           or octet_length(p_extraction_metadata ->> 'originalFilename') > 500
           or coalesce(p_extraction_metadata ->> 'mimeType', '') not in (
               'application/pdf',
               'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
               'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
               'application/vnd.openxmlformats-officedocument.presentationml.presentation',
               'application/json', 'application/x-ndjson',
               'text/csv', 'text/html', 'text/markdown', 'text/plain',
               'image/png', 'image/jpeg', 'image/webp'
           )
           or not coalesce(public.is_safe_public_source_url(p_extraction_metadata ->> 'requestedUrl'), false)
           or not coalesce(public.is_safe_public_source_url(p_extraction_metadata ->> 'finalUrl'), false) then
            raise exception using errcode = '22023', message = 'URL snapshot metadata is invalid';
        end if;
    end if;

    insert into public.source_fragments (
        source_version_id, ordinal, fragment_kind, locator, content_text,
        normalized_text, content_sha256, ocr_confidence
    )
    select
        job_row.source_version_id,
        (entry.ordinality - 1)::integer,
        entry.value ->> 'kind',
        coalesce(entry.value -> 'locator', '{}'::jsonb),
        entry.value ->> 'text',
        coalesce(nullif(entry.value ->> 'normalizedText', ''), entry.value ->> 'text'),
        encode(
            extensions.digest(
                convert_to(
                    coalesce(nullif(entry.value ->> 'normalizedText', ''), entry.value ->> 'text'),
                    'UTF8'
                ),
                'sha256'
            ),
            'hex'
        ),
        case when entry.value ? 'ocrConfidence'
             then (entry.value ->> 'ocrConfidence')::numeric
             else null end
    from jsonb_array_elements(p_fragments) with ordinality as entry(value, ordinality);

    insert into public.source_element_candidates (
        source_version_id, element_id, rank, score, reason, matched_terms
    )
    select
        job_row.source_version_id,
        entry.value ->> 'elementId',
        (entry.value ->> 'rank')::integer,
        (entry.value ->> 'score')::numeric,
        coalesce(entry.value ->> 'reason', ''),
        coalesce(entry.value -> 'matchedTerms', '[]'::jsonb)
    from jsonb_array_elements(p_candidates) as entry(value);

    -- R0 is the only automatic lineage mutation. It is entirely
    -- deterministic and requires the same score/gap contract enforced by the
    -- Worker; every ambiguous result remains only a candidate for review.
    if not p_requires_review
       and p_extraction_metadata ->> 'route' = 'R0_DETERMINISTIC_MATCH' then
        select first_candidate.element_id into auto_link_element_id
        from public.source_element_candidates as first_candidate
        left join public.source_element_candidates as second_candidate
          on second_candidate.source_version_id = first_candidate.source_version_id
         and second_candidate.rank = 2
        where first_candidate.source_version_id = job_row.source_version_id
          and first_candidate.rank = 1
          and first_candidate.score >= 0.92
          and (
              second_candidate.element_id is null
              or first_candidate.score - second_candidate.score >= 0.12
          );
        if auto_link_element_id is not null then
            perform 1
            from public.elements
            where element_id = auto_link_element_id
            for update;

            insert into public.element_sources (
                element_id, source_id, ordinal, created_by
            )
            select
                auto_link_element_id,
                version_row.source_id,
                coalesce(max(link.ordinal), -1) + 1,
                version_row.created_by
            from public.element_sources as link
            where link.element_id = auto_link_element_id
            on conflict do nothing;
        end if;
    end if;

    if job_row.job_kind = 'url_fetch' then
        insert into public.source_files (
            source_version_id, file_role, bucket_id, object_path, original_filename,
            mime_type, byte_size, sha256, created_by
        ) values (
            job_row.source_version_id,
            'snapshot',
            'source-private',
            p_extraction_metadata ->> 'snapshotObjectPath',
            p_extraction_metadata ->> 'originalFilename',
            p_extraction_metadata ->> 'mimeType',
            (p_extraction_metadata ->> 'sourceByteSize')::bigint,
            p_extraction_metadata ->> 'sourceSha256',
            version_row.created_by
        );
    end if;

    update public.source_versions
    set parse_status = case
            when p_requires_review then 'needs_review'::public.source_parse_status
            else 'ready'::public.source_parse_status
        end,
        extracted_text = p_extracted_text,
        extraction_metadata = p_extraction_metadata || jsonb_build_object(
            'fragmentCount', fragment_count,
            'candidateCount', candidate_count,
            'requiresReview', p_requires_review,
            'autoLinkedElementId', auto_link_element_id
        ),
        original_filename = case when job_row.job_kind = 'url_fetch'
            then p_extraction_metadata ->> 'originalFilename' else original_filename end,
        mime_type = case when job_row.job_kind = 'url_fetch'
            then p_extraction_metadata ->> 'mimeType' else mime_type end,
        byte_size = case when job_row.job_kind = 'url_fetch'
            then (p_extraction_metadata ->> 'sourceByteSize')::bigint else byte_size end,
        sha256 = case when job_row.job_kind = 'url_fetch'
            then p_extraction_metadata ->> 'sourceSha256' else sha256 end,
        failure_message = null,
        captured_at = coalesce(captured_at, clock_timestamp())
    where source_version_id = job_row.source_version_id;

    update public.ingestion_jobs
    set status = 'succeeded',
        progress_percent = 100,
        error_message = null,
        output = p_output || jsonb_build_object(
            'stage', case when p_requires_review then 'needs_review' else 'completed' end,
            'fragmentCount', fragment_count,
            'candidateCount', candidate_count,
            'requiresReview', p_requires_review,
            'autoLinkedElementId', auto_link_element_id
        )
    where job_id = p_job_id;

    return jsonb_build_object(
        'jobId', p_job_id,
        'jobStatus', 'succeeded',
        'sourceVersionId', job_row.source_version_id,
        'parseStatus', case when p_requires_review then 'needs_review' else 'ready' end,
        'fragmentCount', fragment_count,
        'candidateCount', candidate_count,
        'autoLinkedElementId', auto_link_element_id,
        'alreadyTerminal', false
    );
end;
$$;

create or replace function public.fail_source_ingestion_job(
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
    version_row public.source_versions%rowtype;
    safe_message text;
begin
    if coalesce(auth.role(), '') <> 'service_role' then
        raise exception using errcode = '42501', message = 'service role required';
    end if;
    safe_message := left(nullif(btrim(p_error_message), ''), 2000);
    if safe_message is null
       or p_output is null
       or jsonb_typeof(p_output) <> 'object'
       or octet_length(p_output::text) > 65536 then
        raise exception using errcode = '22023', message = 'source failure payload is invalid';
    end if;

    select * into job_row
    from public.ingestion_jobs
    where job_id = p_job_id
    for update;
    if not found then
        raise exception using errcode = 'P0002', message = 'job not found';
    end if;
    if job_row.status in ('succeeded', 'failed', 'cancelled') then
        return jsonb_build_object(
            'jobId', p_job_id,
            'jobStatus', job_row.status,
            'sourceVersionId', job_row.source_version_id,
            'alreadyTerminal', true
        );
    end if;
    if job_row.job_kind not in ('file_extract', 'url_fetch')
       or job_row.status <> 'running'
       or job_row.claimed_by is distinct from p_worker_id
       or job_row.source_version_id is null then
        raise exception using errcode = '55000', message = 'source job is not owned by this worker';
    end if;

    -- A URL fetch may have archived its immutable snapshot before parsing
    -- failed. Preserve that snapshot when its bounded metadata is valid, but
    -- never let malformed capture metadata prevent the job from terminating.
    if job_row.job_kind = 'url_fetch' and p_output ? 'snapshotObjectPath' then
        begin
            select * into version_row
            from public.source_versions
            where source_version_id = job_row.source_version_id
            for update;
            if version_row.created_by is not null
               and split_part(p_output ->> 'snapshotObjectPath', '/', 1) = version_row.created_by::text
               and octet_length(p_output ->> 'snapshotObjectPath') between 1 and 1024
               and coalesce(p_output ->> 'sourceSha256', '') ~ '^[0-9a-f]{64}$'
               and jsonb_typeof(p_output -> 'sourceByteSize') = 'number'
               and (p_output ->> 'sourceByteSize')::bigint between 1 and 10737418240
               and octet_length(coalesce(p_output ->> 'originalFilename', '')) between 1 and 500
               and coalesce(p_output ->> 'mimeType', '') in (
                   'application/pdf',
                   'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                   'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                   'application/vnd.openxmlformats-officedocument.presentationml.presentation',
                   'application/json', 'application/x-ndjson',
                   'text/csv', 'text/html', 'text/markdown', 'text/plain',
                   'image/png', 'image/jpeg', 'image/webp'
               ) then
                insert into public.source_files (
                    source_version_id, file_role, bucket_id, object_path, original_filename,
                    mime_type, byte_size, sha256, created_by
                ) values (
                    job_row.source_version_id,
                    'snapshot',
                    'source-private',
                    p_output ->> 'snapshotObjectPath',
                    p_output ->> 'originalFilename',
                    p_output ->> 'mimeType',
                    (p_output ->> 'sourceByteSize')::bigint,
                    p_output ->> 'sourceSha256',
                    version_row.created_by
                ) on conflict (bucket_id, object_path) do nothing;

                update public.source_versions
                set original_filename = p_output ->> 'originalFilename',
                    mime_type = p_output ->> 'mimeType',
                    byte_size = (p_output ->> 'sourceByteSize')::bigint,
                    sha256 = p_output ->> 'sourceSha256',
                    captured_at = coalesce(captured_at, clock_timestamp()),
                    extraction_metadata = extraction_metadata || jsonb_build_object(
                        'captureFailedAfterSnapshot', true,
                        'requestedUrl', p_output ->> 'requestedUrl',
                        'finalUrl', p_output ->> 'finalUrl',
                        'snapshotObjectPath', p_output ->> 'snapshotObjectPath'
                    )
                where source_version_id = job_row.source_version_id;
            end if;
        exception when others then
            null;
        end;
    end if;

    update public.source_versions
    set parse_status = 'failed', failure_message = safe_message
    where source_version_id = job_row.source_version_id
      and parse_status not in ('ready', 'archived');

    update public.ingestion_jobs
    set status = 'failed',
        progress_percent = 100,
        error_message = safe_message,
        output = p_output || jsonb_build_object('stage', 'failed', 'workerFailure', true)
    where job_id = p_job_id;

    return jsonb_build_object(
        'jobId', p_job_id,
        'jobStatus', 'failed',
        'sourceVersionId', job_row.source_version_id,
        'alreadyTerminal', false
    );
end;
$$;

create or replace view public.source_catalog_overview
with (security_invoker = true)
as
select
    source.*,
    coalesce(version_counts.version_count, 0) as version_count,
    latest_version.source_version_id as latest_source_version_id,
    latest_version.created_at as latest_version_at,
    coalesce(latest_version.parse_status, 'ready'::public.source_parse_status) as latest_parse_status,
    latest_version.byte_size as latest_byte_size,
    latest_version.extraction_metadata as latest_extraction_metadata,
    coalesce(element_counts.element_count, 0) as linked_element_count,
    latest_job.job_id as latest_job_id,
    latest_job.job_kind as latest_job_kind,
    latest_job.status as latest_job_status,
    latest_job.progress_percent as latest_job_progress_percent,
    latest_job.output ->> 'stage' as latest_processing_stage,
    latest_job.error_message as latest_job_error_message,
    latest_job.updated_at as latest_job_updated_at,
    candidate_counts.candidate_count,
    top_candidate.element_id as top_candidate_element_id,
    top_candidate.score as top_candidate_score
from public.sources as source
left join lateral (
    select count(*)::integer as version_count
    from public.source_versions as version
    where version.source_id = source.source_id
) as version_counts on true
left join lateral (
    select version.*
    from public.source_versions as version
    where version.source_id = source.source_id
    order by version.version_number desc, version.created_at desc, version.source_version_id desc
    limit 1
) as latest_version on true
left join lateral (
    select count(*)::integer as element_count
    from public.element_sources as link
    where link.source_id = source.source_id
) as element_counts on true
left join lateral (
    select job.*
    from public.ingestion_jobs as job
    where job.source_version_id = latest_version.source_version_id
    order by job.created_at desc, job.job_id desc
    limit 1
) as latest_job on true
left join lateral (
    select count(*)::integer as candidate_count
    from public.source_element_candidates as candidate
    where candidate.source_version_id = latest_version.source_version_id
) as candidate_counts on true
left join lateral (
    select candidate.element_id, candidate.score
    from public.source_element_candidates as candidate
    where candidate.source_version_id = latest_version.source_version_id
    order by candidate.rank, candidate.score desc
    limit 1
) as top_candidate on true;

revoke all on function public.claim_source_ingestion_job(text) from public, anon, authenticated;
revoke all on function public.find_reusable_source_file(text, bigint) from public, anon;
revoke all on function public.update_source_ingestion_progress(uuid, text, integer, text, jsonb) from public, anon, authenticated;
revoke all on function public.complete_source_ingestion_job(uuid, text, text, jsonb, jsonb, jsonb, boolean, jsonb) from public, anon, authenticated;
revoke all on function public.fail_source_ingestion_job(uuid, text, text, jsonb) from public, anon, authenticated;

grant execute on function public.claim_source_ingestion_job(text) to service_role;
grant execute on function public.find_reusable_source_file(text, bigint) to authenticated;
grant execute on function public.update_source_ingestion_progress(uuid, text, integer, text, jsonb) to service_role;
grant execute on function public.complete_source_ingestion_job(uuid, text, text, jsonb, jsonb, jsonb, boolean, jsonb) to service_role;
grant execute on function public.fail_source_ingestion_job(uuid, text, text, jsonb) to service_role;

grant select on public.source_catalog_overview to authenticated;

comment on table public.source_fragments is
    'Immutable parser/OCR fragments with reproducible source locators and FTS indexing.';
comment on table public.source_element_candidates is
    'Deterministic, non-approved element match candidates produced by source ingestion.';
comment on function public.claim_source_ingestion_job(text) is
    'Atomically claims only sandboxed file_extract and SSRF-hardened url_fetch jobs for the dedicated source worker.';
comment on function public.find_reusable_source_file(text, bigint) is
    'Finds a current-admin Storage object with the exact source SHA-256 so uploads can create an alias instead of another object.';

commit;
