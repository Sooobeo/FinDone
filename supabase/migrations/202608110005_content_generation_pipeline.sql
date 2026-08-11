begin;

create type public.content_generation_status as enum (
    'queued',
    'running',
    'ready_for_review',
    'no_changes',
    'rejected',
    'releasing',
    'released',
    'failed'
);

create table public.content_generation_batches (
    batch_id uuid primary key default gen_random_uuid(),
    request_key uuid not null unique,
    status public.content_generation_status not null default 'queued',
    model_name text not null default 'findone-local-content-v1',
    prompt_version text not null default 'findone-local-schema-v1',
    baseline_content_version integer not null default 5 check (baseline_content_version > 0),
    version_name text,
    release_notes text not null default '',
    minimum_app_version integer not null default 1 check (minimum_app_version > 0),
    progress_percent integer not null default 0 check (progress_percent between 0 and 100),
    processing_stage text not null default 'queued',
    attempt_count integer not null default 0 check (attempt_count >= 0),
    max_attempts integer not null default 3 check (max_attempts between 1 and 10),
    claimed_by text,
    claimed_at timestamptz,
    started_at timestamptz,
    completed_at timestamptz,
    item_count integer not null default 0 check (item_count >= 0),
    changed_element_count integer not null default 0 check (changed_element_count >= 0),
    evidence_count integer not null default 0 check (evidence_count >= 0),
    auto_repair_count integer not null default 0 check (auto_repair_count >= 0),
    statistics jsonb not null default '{}'::jsonb,
    error_message text,
    approval_request_key uuid unique,
    approval_comment text not null default '',
    approved_at timestamptz,
    approved_by uuid references auth.users(id) on delete set null,
    release_id uuid unique references public.content_releases(release_id) on delete restrict,
    created_at timestamptz not null default clock_timestamp(),
    created_by uuid references auth.users(id) on delete set null,
    updated_at timestamptz not null default clock_timestamp(),
    updated_by uuid references auth.users(id) on delete set null,
    constraint content_generation_model_not_blank check (btrim(model_name) <> ''),
    constraint content_generation_prompt_not_blank check (btrim(prompt_version) <> ''),
    constraint content_generation_stage_not_blank check (btrim(processing_stage) <> ''),
    constraint content_generation_statistics_object check (jsonb_typeof(statistics) = 'object'),
    constraint content_generation_version_name_length check (version_name is null or length(version_name) <= 80),
    constraint content_generation_release_notes_length check (length(release_notes) <= 4000),
    constraint content_generation_error_length check (error_message is null or length(error_message) <= 2000),
    constraint content_generation_claim_shape check (
        (claimed_by is null and claimed_at is null)
        or (claimed_by ~ '^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$' and claimed_at is not null)
    ),
    constraint content_generation_approval_shape check (
        (approval_request_key is null and approved_at is null and approved_by is null)
        or (approval_request_key is not null and approved_at is not null and approved_by is not null)
    )
);

create table public.content_generation_batch_sources (
    batch_id uuid not null references public.content_generation_batches(batch_id) on delete restrict,
    source_version_id uuid not null references public.source_versions(source_version_id) on delete restrict,
    source_id text not null references public.sources(source_id) on delete restrict,
    created_at timestamptz not null default clock_timestamp(),
    created_by uuid references auth.users(id) on delete set null,
    primary key (batch_id, source_version_id)
);

create table public.content_generation_items (
    generation_item_id uuid primary key default gen_random_uuid(),
    batch_id uuid not null references public.content_generation_batches(batch_id) on delete restrict,
    element_id text not null references public.elements(element_id) on delete restrict,
    entity_type public.content_entity_type not null,
    entity_key text not null,
    baseline_snapshot jsonb not null,
    generated_snapshot jsonb not null,
    changed_fields jsonb not null,
    change_summary text not null default '',
    confidence numeric(5,4) not null check (confidence between 0 and 1),
    risk_level text not null check (risk_level in ('low', 'medium', 'high')),
    validation_summary jsonb not null,
    revision_id uuid unique references public.content_revisions(revision_id) on delete restrict,
    created_at timestamptz not null default clock_timestamp(),
    created_by uuid references auth.users(id) on delete set null,
    constraint content_generation_items_type check (entity_type in ('element', 'concept', 'formula')),
    constraint content_generation_items_key_not_blank check (btrim(entity_key) <> ''),
    constraint content_generation_items_snapshots_object check (
        jsonb_typeof(baseline_snapshot) = 'object'
        and jsonb_typeof(generated_snapshot) = 'object'
    ),
    constraint content_generation_items_changed_fields_array check (
        jsonb_typeof(changed_fields) = 'array' and jsonb_array_length(changed_fields) > 0
    ),
    constraint content_generation_items_validation_object check (jsonb_typeof(validation_summary) = 'object'),
    constraint content_generation_items_batch_entity_unique unique (batch_id, entity_type, entity_key)
);

create table public.content_generation_evidence (
    generation_evidence_id uuid primary key default gen_random_uuid(),
    generation_item_id uuid not null references public.content_generation_items(generation_item_id) on delete restrict,
    field_path text not null,
    source_fragment_id uuid not null references public.source_fragments(source_fragment_id) on delete restrict,
    support_role text not null default 'primary' check (support_role in ('primary', 'corroborating', 'context')),
    rationale text not null default '',
    created_at timestamptz not null default clock_timestamp(),
    created_by uuid references auth.users(id) on delete set null,
    constraint content_generation_evidence_field_not_blank check (btrim(field_path) <> ''),
    constraint content_generation_evidence_unique unique (generation_item_id, field_path, source_fragment_id)
);

create table public.content_model_runs (
    model_run_id uuid primary key default gen_random_uuid(),
    batch_id uuid not null references public.content_generation_batches(batch_id) on delete restrict,
    element_id text references public.elements(element_id) on delete restrict,
    run_kind text not null check (run_kind in ('generate', 'repair')),
    run_number integer not null check (run_number between 1 and 10),
    model_name text not null,
    prompt_version text not null,
    response_id text,
    input_sha256 text not null,
    output_sha256 text,
    input_tokens integer not null default 0 check (input_tokens >= 0),
    output_tokens integer not null default 0 check (output_tokens >= 0),
    duration_ms integer not null default 0 check (duration_ms >= 0),
    status text not null check (status in ('succeeded', 'failed')),
    error_message text,
    created_at timestamptz not null default clock_timestamp(),
    created_by uuid references auth.users(id) on delete set null,
    constraint content_model_runs_model_not_blank check (btrim(model_name) <> ''),
    constraint content_model_runs_prompt_not_blank check (btrim(prompt_version) <> ''),
    constraint content_model_runs_input_hash check (input_sha256 ~ '^[0-9a-f]{64}$'),
    constraint content_model_runs_output_hash check (output_sha256 is null or output_sha256 ~ '^[0-9a-f]{64}$'),
    constraint content_model_runs_error_length check (error_message is null or length(error_message) <= 1000),
    constraint content_model_runs_batch_element_run_unique unique (batch_id, element_id, run_kind, run_number)
);

create index content_generation_batches_status_created_idx
    on public.content_generation_batches(status, created_at, batch_id);
create index content_generation_batch_sources_source_idx
    on public.content_generation_batch_sources(source_version_id, batch_id);
create index content_generation_items_batch_element_idx
    on public.content_generation_items(batch_id, element_id, entity_type);
create index content_generation_evidence_item_field_idx
    on public.content_generation_evidence(generation_item_id, field_path);
create index content_model_runs_batch_element_idx
    on public.content_model_runs(batch_id, element_id, run_number);

create trigger content_generation_batches_set_audit_columns
before insert or update on public.content_generation_batches
for each row execute function public.set_audit_columns();

create trigger content_generation_batch_sources_append_only
before update or delete on public.content_generation_batch_sources
for each row execute function public.prevent_row_mutation();
create trigger content_generation_items_append_only
before delete on public.content_generation_items
for each row execute function public.prevent_row_mutation();
create trigger content_generation_evidence_append_only
before update or delete on public.content_generation_evidence
for each row execute function public.prevent_row_mutation();
create trigger content_model_runs_append_only
before update or delete on public.content_model_runs
for each row execute function public.prevent_row_mutation();

alter table public.content_generation_batches enable row level security;
alter table public.content_generation_batch_sources enable row level security;
alter table public.content_generation_items enable row level security;
alter table public.content_generation_evidence enable row level security;
alter table public.content_model_runs enable row level security;

create policy content_generation_batches_admin_select
on public.content_generation_batches for select to authenticated
using ((select public.is_admin()));
create policy content_generation_batch_sources_admin_select
on public.content_generation_batch_sources for select to authenticated
using ((select public.is_admin()));
create policy content_generation_items_admin_select
on public.content_generation_items for select to authenticated
using ((select public.is_admin()));
create policy content_generation_evidence_admin_select
on public.content_generation_evidence for select to authenticated
using ((select public.is_admin()));
create policy content_model_runs_admin_select
on public.content_model_runs for select to authenticated
using ((select public.is_admin()));

create or replace function public.generation_entity_snapshot(
    p_entity_type public.content_entity_type,
    p_entity_key text
)
returns jsonb
language plpgsql
security definer
stable
set search_path = ''
as $$
declare
    result jsonb;
begin
    if p_entity_type = 'element' then
        select jsonb_build_object(
            'element_id', element.element_id,
            'domain_id', element.domain_id,
            'element_number', element.element_number,
            'title', element.title,
            'topic_name', element.topic_name,
            'subtopic_name', element.subtopic_name,
            'mode', element.mode,
            'core_relation', element.core_relation,
            'scope_notes', element.scope_notes,
            'source_label', element.source_label,
            'source_locator', element.source_locator,
            'spec_section_locator', element.spec_section_locator,
            'display_order', element.display_order,
            'is_active', element.is_active
        ) into result
        from public.elements as element
        where element.element_id = p_entity_key;
    elsif p_entity_type = 'concept' then
        select jsonb_build_object(
            'concept_id', concept.concept_id,
            'element_id', concept.element_id,
            'title', concept.title,
            'definition_markdown', concept.definition_markdown,
            'intuition_markdown', concept.intuition_markdown,
            'learning_notes_markdown', concept.learning_notes_markdown,
            'checklist_markdown', concept.checklist_markdown,
            'glossary_terms', concept.glossary_terms
        ) into result
        from public.concepts as concept
        where concept.concept_id = p_entity_key;
    elsif p_entity_type = 'formula' then
        select jsonb_build_object(
            'formula_id', formula.formula_id,
            'element_id', formula.element_id,
            'formula_key', formula.formula_key,
            'title', formula.title,
            'expression_markdown', formula.expression_markdown,
            'assumptions_markdown', formula.assumptions_markdown,
            'notes_markdown', formula.notes_markdown,
            'variables', formula.variables,
            'display_order', formula.display_order,
            'is_primary', formula.is_primary
        ) into result
        from public.formulas as formula
        where formula.formula_id = p_entity_key;
    else
        raise exception using errcode = '22023', message = 'entity type is not app-projectable';
    end if;
    if result is null then
        raise exception using errcode = 'P0002', message = 'generation baseline entity not found';
    end if;
    return result;
end;
$$;

create or replace function public.queue_catalog_url_sources(
    p_source_ids text[] default null,
    p_limit integer default 50,
    p_refresh boolean default false
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
    source_row public.sources%rowtype;
    version_id uuid;
    job_id_value uuid;
    next_version integer;
    actor_id uuid := auth.uid();
    queued_versions jsonb := '[]'::jsonb;
    queued_count integer := 0;
begin
    if not public.has_admin_role(array['owner', 'editor']::public.admin_role[]) then
        raise exception using errcode = '42501', message = 'editor role required';
    end if;
    if p_limit < 1 or p_limit > 100 then
        raise exception using errcode = '22023', message = 'catalog queue limit must be between 1 and 100';
    end if;
    if p_source_ids is not null and cardinality(p_source_ids) > 100 then
        raise exception using errcode = '22023', message = 'too many source ids';
    end if;
    if actor_id is null then
        select admin.user_id into actor_id
        from public.admin_users as admin
        where admin.is_active and admin.role = 'owner'
        order by admin.created_at, admin.user_id
        limit 1;
    end if;
    if actor_id is null then
        raise exception using errcode = '55000', message = 'active owner is required to queue catalog sources';
    end if;

    for source_row in
        select source.*
        from public.sources as source
        where source.is_active
          and public.is_safe_public_source_url(source.locator)
          and (p_source_ids is null or source.source_id = any (p_source_ids))
          and not exists (
              select 1
              from public.source_versions as active_version
              where active_version.source_id = source.source_id
                and active_version.parse_status in ('pending', 'fetching', 'extracting')
          )
          and (
              p_refresh
              or not exists (
                  select 1 from public.source_versions as prior_version
                  where prior_version.source_id = source.source_id
              )
          )
        order by source.created_at, source.source_id
        limit p_limit
    loop
        perform pg_advisory_xact_lock(hashtextextended('source-version:' || source_row.source_id, 0));
        if exists (
            select 1 from public.source_versions as active_version
            where active_version.source_id = source_row.source_id
              and active_version.parse_status in ('pending', 'fetching', 'extracting')
        ) or (
            not p_refresh and exists (
                select 1 from public.source_versions as prior_version
                where prior_version.source_id = source_row.source_id
            )
        ) then
            continue;
        end if;
        select coalesce(max(version.version_number), 0) + 1 into next_version
        from public.source_versions as version
        where version.source_id = source_row.source_id;

        insert into public.source_versions (
            source_id, version_number, fetch_url, parse_status, created_by
        ) values (
            source_row.source_id, next_version, source_row.locator, 'pending', actor_id
        ) returning source_version_id into version_id;

        insert into public.ingestion_jobs (job_kind, source_version_id, input, created_by)
        values (
            'url_fetch', version_id,
            jsonb_build_object('url', source_row.locator, 'catalogImport', true),
            actor_id
        ) returning job_id into job_id_value;

        queued_count := queued_count + 1;
        queued_versions := queued_versions || jsonb_build_array(jsonb_build_object(
            'sourceId', source_row.source_id,
            'sourceVersionId', version_id,
            'jobId', job_id_value
        ));
    end loop;

    return jsonb_build_object('queuedCount', queued_count, 'queued', queued_versions);
end;
$$;

create or replace function public.create_content_generation_batch(
    p_request_key uuid,
    p_model_name text default 'findone-local-content-v1',
    p_prompt_version text default 'findone-local-schema-v1',
    p_release_notes text default '',
    p_minimum_app_version integer default 1,
    p_source_version_ids uuid[] default null,
    p_max_sources integer default 50
)
returns public.content_generation_batches
language plpgsql
security definer
set search_path = ''
as $$
declare
    result public.content_generation_batches%rowtype;
    source_count integer;
    baseline_version integer;
begin
    if not public.has_admin_role(array['owner', 'editor']::public.admin_role[]) then
        raise exception using errcode = '42501', message = 'editor role required';
    end if;
    if p_request_key is null then
        raise exception using errcode = '22023', message = 'generation request key is required';
    end if;
    if nullif(btrim(p_model_name), '') is null or length(p_model_name) > 120
       or nullif(btrim(p_prompt_version), '') is null or length(p_prompt_version) > 120 then
        raise exception using errcode = '22023', message = 'generation model contract is invalid';
    end if;
    if p_minimum_app_version < 1 or p_max_sources < 1 or p_max_sources > 100
       or length(coalesce(p_release_notes, '')) > 4000 then
        raise exception using errcode = '22023', message = 'generation release options are invalid';
    end if;
    if p_source_version_ids is not null and cardinality(p_source_version_ids) > 100 then
        raise exception using errcode = '22023', message = 'too many generation sources';
    end if;

    perform pg_advisory_xact_lock(hashtextextended('generation-request:' || p_request_key::text, 0));
    select * into result from public.content_generation_batches where request_key = p_request_key;
    if found then
        if result.created_by is distinct from auth.uid() then
            raise exception using errcode = '42501', message = 'generation request key belongs to another actor';
        end if;
        return result;
    end if;

    select coalesce(
        (select release.content_version from public.content_releases as release
         where release.status = 'published' order by release.content_version desc limit 1),
        (select max(import.schema_version * 0 + (import.source_metadata ->> 'contentDbVersion')::integer)
         from public.content_imports as import),
        5
    ) into baseline_version;

    insert into public.content_generation_batches (
        request_key, model_name, prompt_version, baseline_content_version,
        release_notes, minimum_app_version, created_by
    ) values (
        p_request_key, btrim(p_model_name), btrim(p_prompt_version), baseline_version,
        coalesce(p_release_notes, ''), p_minimum_app_version, auth.uid()
    ) returning * into result;

    insert into public.content_generation_batch_sources (
        batch_id, source_version_id, source_id, created_by
    )
    select result.batch_id, candidate.source_version_id, candidate.source_id, auth.uid()
    from (
        select distinct on (version.source_id)
            version.source_version_id, version.source_id, version.version_number
        from public.source_versions as version
        join public.sources as source on source.source_id = version.source_id and source.is_active
        where version.parse_status = 'ready'
          and exists (
              select 1 from public.source_fragments as fragment
              where fragment.source_version_id = version.source_version_id
          )
          and (p_source_version_ids is null or version.source_version_id = any (p_source_version_ids))
          and (
              p_source_version_ids is not null
              or not exists (
                  select 1
                  from public.content_generation_batch_sources as used_source
                  where used_source.source_version_id = version.source_version_id
              )
          )
        order by version.source_id, version.version_number desc, version.created_at desc
    ) as candidate
    order by candidate.version_number desc, candidate.source_id
    limit p_max_sources;
    get diagnostics source_count = row_count;
    if source_count < 1 then
        raise exception using errcode = '55000', message = 'no unprocessed ready source versions are available';
    end if;
    return result;
end;
$$;

create or replace function public.enqueue_ready_content_generation(
    p_model_name text,
    p_prompt_version text,
    p_max_sources integer default 50
)
returns public.content_generation_batches
language plpgsql
security definer
set search_path = ''
as $$
declare
    result public.content_generation_batches%rowtype;
    batch_request_key uuid := gen_random_uuid();
    source_count integer;
    baseline_version integer;
    actor_id uuid;
begin
    if coalesce(auth.role(), '') <> 'service_role' then
        raise exception using errcode = '42501', message = 'service role required';
    end if;
    if nullif(btrim(p_model_name), '') is null or length(p_model_name) > 120
       or nullif(btrim(p_prompt_version), '') is null or length(p_prompt_version) > 120
       or p_max_sources < 1 or p_max_sources > 100 then
        raise exception using errcode = '22023', message = 'generation worker contract is invalid';
    end if;
    perform pg_advisory_xact_lock(hashtextextended('generation-auto-enqueue', 0));

    if not exists (
        select 1
        from public.source_versions as version
        where version.parse_status = 'ready'
          and version.created_at <= clock_timestamp() - interval '30 seconds'
          and exists (select 1 from public.source_fragments as fragment where fragment.source_version_id = version.source_version_id)
          and not exists (
              select 1 from public.content_generation_batch_sources as used_source
              where used_source.source_version_id = version.source_version_id
          )
    ) then
        return null;
    end if;

    select coalesce(
        (select release.content_version from public.content_releases as release
         where release.status = 'published' order by release.content_version desc limit 1),
        (select (import.source_metadata ->> 'contentDbVersion')::integer
         from public.content_imports as import order by import.imported_at desc limit 1),
        5
    ) into baseline_version;

    select version.created_by into actor_id
    from public.source_versions as version
    where version.parse_status = 'ready' and version.created_by is not null
    order by version.created_at
    limit 1;

    insert into public.content_generation_batches (
        request_key, model_name, prompt_version, baseline_content_version,
        release_notes, created_by
    ) values (
        batch_request_key, btrim(p_model_name), btrim(p_prompt_version), baseline_version,
        '원본 근거 기반 로컬 규칙 콘텐츠 변환', actor_id
    ) returning * into result;

    insert into public.content_generation_batch_sources (
        batch_id, source_version_id, source_id, created_by
    )
    select result.batch_id, candidate.source_version_id, candidate.source_id, actor_id
    from (
        select distinct on (version.source_id)
            version.source_version_id, version.source_id, version.version_number
        from public.source_versions as version
        join public.sources as source on source.source_id = version.source_id and source.is_active
        where version.parse_status = 'ready'
          and version.created_at <= clock_timestamp() - interval '30 seconds'
          and exists (select 1 from public.source_fragments as fragment where fragment.source_version_id = version.source_version_id)
          and not exists (
              select 1 from public.content_generation_batch_sources as used_source
              where used_source.source_version_id = version.source_version_id
          )
        order by version.source_id, version.version_number desc, version.created_at desc
    ) as candidate
    order by candidate.version_number desc, candidate.source_id
    limit p_max_sources;
    get diagnostics source_count = row_count;

    if source_count < 1 then
        raise exception using errcode = '40001', message = 'ready generation sources were claimed concurrently';
    end if;
    return result;
end;
$$;

create or replace function public.claim_content_generation_batch(
    p_worker_id text,
    p_model_name text,
    p_prompt_version text
)
returns public.content_generation_batches
language plpgsql
security definer
set search_path = ''
as $$
declare
    result public.content_generation_batches%rowtype;
    candidate_id uuid;
    lease_cutoff timestamptz := clock_timestamp() - interval '30 minutes';
begin
    if coalesce(auth.role(), '') <> 'service_role' then
        raise exception using errcode = '42501', message = 'service role required';
    end if;
    if p_worker_id is null or p_worker_id !~ '^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$'
       or nullif(btrim(p_model_name), '') is null
       or nullif(btrim(p_prompt_version), '') is null then
        raise exception using errcode = '22023', message = 'generation claim contract is invalid';
    end if;

    update public.content_generation_batches
    set status = 'failed', progress_percent = 100, processing_stage = 'failed',
        completed_at = clock_timestamp(),
        error_message = 'generation worker lease expired and retry budget was exhausted'
    where status = 'running'
      and attempt_count >= max_attempts
      and coalesce(claimed_at, started_at, updated_at) <= lease_cutoff;

    select batch.* into result
    from public.content_generation_batches as batch
    where batch.status = 'running'
      and batch.claimed_by = p_worker_id
      and coalesce(batch.claimed_at, batch.started_at, batch.updated_at) > lease_cutoff
    order by batch.claimed_at, batch.batch_id
    for update
    limit 1;
    if found then return result; end if;

    select batch.batch_id into candidate_id
    from public.content_generation_batches as batch
    where (
        batch.status = 'queued'
        or (
            batch.status = 'running'
            and batch.attempt_count < batch.max_attempts
            and coalesce(batch.claimed_at, batch.started_at, batch.updated_at) <= lease_cutoff
        )
      )
      and batch.model_name in ('worker-default', p_model_name)
      and batch.prompt_version = p_prompt_version
    order by case when batch.status = 'running' then 0 else 1 end,
             batch.created_at, batch.batch_id
    for update skip locked
    limit 1;

    if candidate_id is null then return null; end if;

    update public.content_generation_batches
    set status = 'running', model_name = p_model_name,
        attempt_count = attempt_count + 1,
        progress_percent = 1, processing_stage = 'baseline_loading',
        claimed_by = p_worker_id, claimed_at = clock_timestamp(),
        started_at = coalesce(started_at, clock_timestamp()), completed_at = null,
        error_message = null
    where batch_id = candidate_id
    returning * into result;
    return result;
end;
$$;

create or replace function public.update_content_generation_progress(
    p_batch_id uuid,
    p_worker_id text,
    p_progress_percent integer,
    p_processing_stage text,
    p_statistics jsonb default '{}'::jsonb
)
returns public.content_generation_batches
language plpgsql
security definer
set search_path = ''
as $$
declare
    result public.content_generation_batches%rowtype;
begin
    if coalesce(auth.role(), '') <> 'service_role' then
        raise exception using errcode = '42501', message = 'service role required';
    end if;
    if p_progress_percent < 1 or p_progress_percent > 95
       or nullif(btrim(p_processing_stage), '') is null
       or length(p_processing_stage) > 120
       or p_statistics is null or jsonb_typeof(p_statistics) <> 'object'
       or octet_length(p_statistics::text) > 262144 then
        raise exception using errcode = '22023', message = 'generation progress is invalid';
    end if;
    update public.content_generation_batches
    set progress_percent = greatest(progress_percent, p_progress_percent),
        processing_stage = p_processing_stage,
        statistics = statistics || p_statistics,
        claimed_at = clock_timestamp()
    where batch_id = p_batch_id and status = 'running' and claimed_by = p_worker_id
    returning * into result;
    if not found then
        raise exception using errcode = '55000', message = 'generation batch is not owned by this worker';
    end if;
    return result;
end;
$$;

create or replace function public.get_content_generation_fragments(
    p_batch_id uuid,
    p_worker_id text,
    p_limit_per_source integer default 120
)
returns table (
    source_fragment_id uuid,
    source_version_id uuid,
    source_id text,
    fragment_kind text,
    locator jsonb,
    content_excerpt text,
    ocr_confidence numeric
)
language plpgsql
security definer
stable
set search_path = ''
as $$
begin
    if coalesce(auth.role(), '') <> 'service_role' then
        raise exception using errcode = '42501', message = 'service role required';
    end if;
    if p_limit_per_source < 10 or p_limit_per_source > 250 then
        raise exception using errcode = '22023', message = 'fragment sample limit is invalid';
    end if;
    if not exists (
        select 1 from public.content_generation_batches as batch
        where batch.batch_id = p_batch_id
          and batch.status = 'running'
          and batch.claimed_by = p_worker_id
    ) then
        raise exception using errcode = '55000', message = 'generation batch is not owned by this worker';
    end if;
    return query
    with ranked as (
        select
            fragment.source_fragment_id,
            fragment.source_version_id,
            batch_source.source_id,
            fragment.fragment_kind,
            fragment.locator,
            fragment.content_text,
            fragment.ocr_confidence,
            row_number() over (
                partition by fragment.source_version_id order by fragment.ordinal
            ) as row_number_value,
            count(*) over (partition by fragment.source_version_id) as row_count_value
        from public.content_generation_batch_sources as batch_source
        join public.source_fragments as fragment
          on fragment.source_version_id = batch_source.source_version_id
        where batch_source.batch_id = p_batch_id
    )
    select
        ranked.source_fragment_id,
        ranked.source_version_id,
        ranked.source_id,
        ranked.fragment_kind,
        ranked.locator,
        left(ranked.content_text, 4000),
        ranked.ocr_confidence
    from ranked
    where ranked.row_count_value <= p_limit_per_source
       or mod(
            ranked.row_number_value - 1,
            greatest(1, ceil(ranked.row_count_value::numeric / p_limit_per_source)::integer)
       ) = 0
    order by ranked.source_version_id, ranked.row_number_value;
end;
$$;

create or replace function public.complete_content_generation_batch(
    p_batch_id uuid,
    p_worker_id text,
    p_items jsonb,
    p_evidence jsonb,
    p_model_runs jsonb,
    p_statistics jsonb default '{}'::jsonb
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
    batch_row public.content_generation_batches%rowtype;
    item_value jsonb;
    evidence_value jsonb;
    run_value jsonb;
    item_type public.content_entity_type;
    item_key text;
    item_element_id text;
    item_id uuid;
    baseline jsonb;
    generated jsonb;
    changed jsonb;
    changed_field text;
    allowed_fields text[];
    actual_changed_count integer;
    item_count_value integer;
    evidence_count_value integer;
    element_count_value integer;
    repair_count_value integer;
    final_status public.content_generation_status;
begin
    if coalesce(auth.role(), '') <> 'service_role' then
        raise exception using errcode = '42501', message = 'service role required';
    end if;
    if p_items is null or jsonb_typeof(p_items) <> 'array'
       or p_evidence is null or jsonb_typeof(p_evidence) <> 'array'
       or p_model_runs is null or jsonb_typeof(p_model_runs) <> 'array'
       or p_statistics is null or jsonb_typeof(p_statistics) <> 'object'
       or jsonb_array_length(p_items) > 405
       or jsonb_array_length(p_evidence) > 6000
       or jsonb_array_length(p_model_runs) > 1000
       or octet_length(p_items::text) > 12582912
       or octet_length(p_evidence::text) > 8388608
       or octet_length(p_model_runs::text) > 4194304
       or octet_length(p_statistics::text) > 262144 then
        raise exception using errcode = '22023', message = 'generation completion payload is invalid';
    end if;

    select * into batch_row from public.content_generation_batches
    where batch_id = p_batch_id for update;
    if not found then raise exception using errcode = 'P0002', message = 'generation batch not found'; end if;
    if batch_row.status in ('ready_for_review', 'no_changes') then
        return jsonb_build_object(
            'batchId', p_batch_id, 'status', batch_row.status,
            'itemCount', batch_row.item_count, 'alreadyTerminal', true
        );
    end if;
    if batch_row.status <> 'running' or batch_row.claimed_by is distinct from p_worker_id then
        raise exception using errcode = '55000', message = 'generation batch is not owned by this worker';
    end if;

    for item_value in select value from jsonb_array_elements(p_items)
    loop
        if jsonb_typeof(item_value) <> 'object' then
            raise exception using errcode = '22023', message = 'generation item must be an object';
        end if;
        begin
            item_type := (item_value ->> 'entityType')::public.content_entity_type;
        exception when invalid_text_representation then
            raise exception using errcode = '22023', message = 'generation item entity type is invalid';
        end;
        if item_type not in ('element', 'concept', 'formula') then
            raise exception using errcode = '22023', message = 'generation item is not app-projectable';
        end if;
        item_key := item_value ->> 'entityKey';
        item_element_id := item_value ->> 'elementId';
        baseline := item_value -> 'baselineSnapshot';
        generated := item_value -> 'generatedSnapshot';
        changed := item_value -> 'changedFields';
        if nullif(btrim(item_key), '') is null or nullif(btrim(item_element_id), '') is null
           or jsonb_typeof(baseline) <> 'object' or jsonb_typeof(generated) <> 'object'
           or jsonb_typeof(changed) <> 'array' or jsonb_array_length(changed) < 1
           or jsonb_array_length(changed) > 20
           or jsonb_typeof(item_value -> 'validationSummary') <> 'object'
           or coalesce((item_value #>> '{validationSummary,checksTotal}')::integer, 0) < 1
           or coalesce((item_value #>> '{validationSummary,checksFailed}')::integer, -1) <> 0
           or coalesce((item_value #>> '{validationSummary,checksPassed}')::integer, -1)
              <> coalesce((item_value #>> '{validationSummary,checksTotal}')::integer, 0)
           or coalesce((item_value ->> 'confidence')::numeric, -1) not between 0 and 1
           or coalesce(item_value ->> 'riskLevel', '') not in ('low', 'medium', 'high') then
            raise exception using errcode = '22023', message = 'generation item contract is invalid';
        end if;
        if baseline is distinct from public.generation_entity_snapshot(item_type, item_key) then
            raise exception using errcode = '55000', message = 'generation baseline is stale';
        end if;
        if (select array_agg(key order by key) from jsonb_object_keys(baseline) as keys(key))
           is distinct from
           (select array_agg(key order by key) from jsonb_object_keys(generated) as keys(key)) then
            raise exception using errcode = '22023', message = 'generated snapshot keys differ from baseline';
        end if;
        if generated ->> 'element_id' is distinct from item_element_id
           or (item_type = 'element' and generated ->> 'element_id' is distinct from item_key)
           or (item_type = 'concept' and generated ->> 'concept_id' is distinct from item_key)
           or (item_type = 'formula' and generated ->> 'formula_id' is distinct from item_key) then
            raise exception using errcode = '22023', message = 'generated snapshot identity changed';
        end if;

        allowed_fields := case item_type
            when 'element' then array['title', 'core_relation', 'scope_notes']::text[]
            when 'concept' then array[
                'title', 'definition_markdown', 'intuition_markdown',
                'learning_notes_markdown', 'checklist_markdown', 'glossary_terms'
            ]::text[]
            when 'formula' then array[
                'title', 'expression_markdown', 'assumptions_markdown',
                'notes_markdown', 'variables'
            ]::text[]
            else array[]::text[]
        end;
        if (baseline - allowed_fields) is distinct from (generated - allowed_fields) then
            raise exception using errcode = '22023', message = 'generated snapshot changed an immutable field';
        end if;

        actual_changed_count := 0;
        foreach changed_field in array allowed_fields
        loop
            if baseline -> changed_field is distinct from generated -> changed_field then
                actual_changed_count := actual_changed_count + 1;
                if not (changed ? changed_field) then
                    raise exception using errcode = '22023', message = 'changed field list is incomplete';
                end if;
            elsif changed ? changed_field then
                raise exception using errcode = '22023', message = 'changed field list contains an unchanged field';
            end if;
        end loop;
        if actual_changed_count <> jsonb_array_length(changed) then
            raise exception using errcode = '22023', message = 'changed field list contains an unsupported field';
        end if;

        insert into public.content_generation_items (
            batch_id, element_id, entity_type, entity_key,
            baseline_snapshot, generated_snapshot, changed_fields,
            change_summary, confidence, risk_level, validation_summary, created_by
        ) values (
            p_batch_id, item_element_id, item_type, item_key,
            baseline, generated, changed,
            left(coalesce(item_value ->> 'changeSummary', ''), 2000),
            (item_value ->> 'confidence')::numeric,
            item_value ->> 'riskLevel', item_value -> 'validationSummary', batch_row.created_by
        ) returning generation_item_id into item_id;
    end loop;

    for evidence_value in select value from jsonb_array_elements(p_evidence)
    loop
        if jsonb_typeof(evidence_value) <> 'object'
           or nullif(btrim(evidence_value ->> 'fieldPath'), '') is null
           or coalesce(evidence_value ->> 'supportRole', '') not in ('primary', 'corroborating', 'context') then
            raise exception using errcode = '22023', message = 'generation evidence contract is invalid';
        end if;
        select item.generation_item_id into item_id
        from public.content_generation_items as item
        where item.batch_id = p_batch_id
          and item.entity_type::text = evidence_value ->> 'entityType'
          and item.entity_key = evidence_value ->> 'entityKey';
        if not found then
            raise exception using errcode = '22023', message = 'generation evidence item was not found';
        end if;
        if not exists (
            select 1 from public.content_generation_items as item
            where item.generation_item_id = item_id
              and item.changed_fields ? (evidence_value ->> 'fieldPath')
        ) then
            raise exception using errcode = '22023', message = 'generation evidence field was not changed';
        end if;
        if not exists (
            select 1
            from public.source_fragments as fragment
            join public.content_generation_batch_sources as batch_source
              on batch_source.source_version_id = fragment.source_version_id
             and batch_source.batch_id = p_batch_id
            where fragment.source_fragment_id = (evidence_value ->> 'sourceFragmentId')::uuid
        ) then
            raise exception using errcode = '22023', message = 'generation evidence is outside the batch source scope';
        end if;
        insert into public.content_generation_evidence (
            generation_item_id, field_path, source_fragment_id,
            support_role, rationale, created_by
        ) values (
            item_id, evidence_value ->> 'fieldPath',
            (evidence_value ->> 'sourceFragmentId')::uuid,
            evidence_value ->> 'supportRole',
            left(coalesce(evidence_value ->> 'rationale', ''), 1000),
            batch_row.created_by
        );
    end loop;

    if exists (
        select 1
        from public.content_generation_items as item
        cross join lateral jsonb_array_elements_text(item.changed_fields) as changed_field(value)
        where item.batch_id = p_batch_id
          and not exists (
              select 1 from public.content_generation_evidence as evidence
              where evidence.generation_item_id = item.generation_item_id
                and evidence.field_path = changed_field.value
          )
    ) then
        raise exception using errcode = '23514', message = 'every generated field requires source evidence';
    end if;

    for run_value in select value from jsonb_array_elements(p_model_runs)
    loop
        if jsonb_typeof(run_value) <> 'object'
           or coalesce(run_value ->> 'runKind', '') not in ('generate', 'repair')
           or coalesce(run_value ->> 'status', '') not in ('succeeded', 'failed')
           or coalesce(run_value ->> 'inputSha256', '') !~ '^[0-9a-f]{64}$'
           or (run_value ? 'outputSha256' and run_value ->> 'outputSha256' is not null
               and run_value ->> 'outputSha256' !~ '^[0-9a-f]{64}$') then
            raise exception using errcode = '22023', message = 'model run contract is invalid';
        end if;
        insert into public.content_model_runs (
            batch_id, element_id, run_kind, run_number, model_name,
            prompt_version, response_id, input_sha256, output_sha256,
            input_tokens, output_tokens, duration_ms, status, error_message, created_by
        ) values (
            p_batch_id, nullif(run_value ->> 'elementId', ''),
            run_value ->> 'runKind', (run_value ->> 'runNumber')::integer,
            batch_row.model_name, batch_row.prompt_version,
            nullif(run_value ->> 'responseId', ''), run_value ->> 'inputSha256',
            nullif(run_value ->> 'outputSha256', ''),
            coalesce((run_value ->> 'inputTokens')::integer, 0),
            coalesce((run_value ->> 'outputTokens')::integer, 0),
            coalesce((run_value ->> 'durationMs')::integer, 0),
            run_value ->> 'status', left(nullif(run_value ->> 'errorMessage', ''), 1000),
            batch_row.created_by
        );
    end loop;

    select count(*)::integer, count(distinct item.element_id)::integer
    into item_count_value, element_count_value
    from public.content_generation_items as item where item.batch_id = p_batch_id;
    select count(*)::integer into evidence_count_value
    from public.content_generation_evidence as evidence
    join public.content_generation_items as item on item.generation_item_id = evidence.generation_item_id
    where item.batch_id = p_batch_id;
    select count(*)::integer into repair_count_value
    from public.content_model_runs as run where run.batch_id = p_batch_id and run.run_kind = 'repair';
    final_status := case when item_count_value = 0 then 'no_changes'::public.content_generation_status
                         else 'ready_for_review'::public.content_generation_status end;

    update public.content_generation_batches
    set status = final_status, progress_percent = 100,
        processing_stage = case when final_status = 'no_changes' then 'no_supported_changes' else 'final_review_ready' end,
        completed_at = clock_timestamp(), claimed_by = null, claimed_at = null,
        item_count = item_count_value, changed_element_count = element_count_value,
        evidence_count = evidence_count_value, auto_repair_count = repair_count_value,
        statistics = statistics || p_statistics, error_message = null
    where batch_id = p_batch_id;

    return jsonb_build_object(
        'batchId', p_batch_id, 'status', final_status,
        'itemCount', item_count_value, 'changedElementCount', element_count_value,
        'evidenceCount', evidence_count_value, 'autoRepairCount', repair_count_value
    );
end;
$$;

create or replace function public.fail_content_generation_batch(
    p_batch_id uuid,
    p_worker_id text,
    p_error_message text,
    p_statistics jsonb default '{}'::jsonb
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
    batch_row public.content_generation_batches%rowtype;
    retrying boolean;
    safe_message text;
begin
    if coalesce(auth.role(), '') <> 'service_role' then
        raise exception using errcode = '42501', message = 'service role required';
    end if;
    if nullif(btrim(p_error_message), '') is null
       or p_statistics is null or jsonb_typeof(p_statistics) <> 'object' then
        raise exception using errcode = '22023', message = 'generation failure payload is invalid';
    end if;
    select * into batch_row from public.content_generation_batches
    where batch_id = p_batch_id for update;
    if not found then raise exception using errcode = 'P0002', message = 'generation batch not found'; end if;
    if batch_row.status in ('ready_for_review', 'no_changes', 'rejected', 'releasing', 'released', 'failed') then
        return jsonb_build_object('batchId', p_batch_id, 'status', batch_row.status, 'alreadyTerminal', true);
    end if;
    if batch_row.status <> 'running' or batch_row.claimed_by is distinct from p_worker_id then
        raise exception using errcode = '55000', message = 'generation batch is not owned by this worker';
    end if;
    safe_message := left(btrim(p_error_message), 2000);
    retrying := batch_row.attempt_count < batch_row.max_attempts;
    update public.content_generation_batches
    set status = case when retrying then 'queued'::public.content_generation_status else 'failed'::public.content_generation_status end,
        progress_percent = case when retrying then 0 else 100 end,
        processing_stage = case when retrying then 'retry_queued' else 'failed' end,
        claimed_by = null, claimed_at = null,
        completed_at = case when retrying then null else clock_timestamp() end,
        statistics = statistics || p_statistics,
        error_message = safe_message
    where batch_id = p_batch_id;
    return jsonb_build_object(
        'batchId', p_batch_id,
        'status', case when retrying then 'queued' else 'failed' end,
        'retrying', retrying,
        'attemptCount', batch_row.attempt_count,
        'maxAttempts', batch_row.max_attempts
    );
end;
$$;

create or replace function public.approve_content_generation_batch(
    p_batch_id uuid,
    p_request_key uuid,
    p_comment text default ''
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
    batch_row public.content_generation_batches%rowtype;
    item_row public.content_generation_items%rowtype;
    revision_row public.content_revisions%rowtype;
    release_row public.content_releases%rowtype;
    validation_run_id_value uuid;
    next_version integer;
    item_count_value integer := 0;
    checks_total_value integer;
    comment_value text;
begin
    if not public.has_admin_role(array['owner', 'reviewer', 'releaser']::public.admin_role[]) then
        raise exception using errcode = '42501', message = 'owner review and release permission required';
    end if;
    if p_request_key is null then
        raise exception using errcode = '22023', message = 'approval request key is required';
    end if;
    comment_value := left(coalesce(p_comment, ''), 4000);
    perform pg_advisory_xact_lock(hashtextextended('generation-approval:' || p_batch_id::text, 0));
    select * into batch_row from public.content_generation_batches
    where batch_id = p_batch_id for update;
    if not found then raise exception using errcode = 'P0002', message = 'generation batch not found'; end if;
    if batch_row.approval_request_key is not null then
        if batch_row.approval_request_key is distinct from p_request_key then
            raise exception using errcode = '40900', message = 'generation batch was approved with another request key';
        end if;
        return jsonb_build_object(
            'batchId', batch_row.batch_id, 'status', batch_row.status,
            'releaseId', batch_row.release_id, 'alreadyApproved', true
        );
    end if;
    if batch_row.status <> 'ready_for_review' or batch_row.item_count < 1 then
        raise exception using errcode = '55000', message = 'only a non-empty final-review batch can be approved';
    end if;

    perform set_config('app.change_reason', '로컬 변환 배치 ' || p_batch_id::text, true);
    for item_row in
        select item.* from public.content_generation_items as item
        where item.batch_id = p_batch_id
        order by item.element_id,
                 case item.entity_type when 'element' then 1 when 'concept' then 2 else 3 end,
                 item.entity_key
    loop
        perform pg_advisory_xact_lock(hashtextextended(item_row.entity_type::text || ':' || item_row.entity_key, 0));
        if item_row.revision_id is not null then
            raise exception using errcode = '55000', message = 'generation item is already linked to a revision';
        end if;
        if item_row.baseline_snapshot is distinct from public.generation_entity_snapshot(item_row.entity_type, item_row.entity_key) then
            raise exception using errcode = '55000', message = 'authoring content changed after generation; regenerate before approval';
        end if;

        if item_row.entity_type = 'element' then
            update public.elements
            set title = item_row.generated_snapshot ->> 'title',
                core_relation = item_row.generated_snapshot ->> 'core_relation',
                scope_notes = item_row.generated_snapshot ->> 'scope_notes'
            where element_id = item_row.entity_key;
        elsif item_row.entity_type = 'concept' then
            update public.concepts
            set title = item_row.generated_snapshot ->> 'title',
                definition_markdown = item_row.generated_snapshot ->> 'definition_markdown',
                intuition_markdown = item_row.generated_snapshot ->> 'intuition_markdown',
                learning_notes_markdown = item_row.generated_snapshot ->> 'learning_notes_markdown',
                checklist_markdown = item_row.generated_snapshot ->> 'checklist_markdown',
                glossary_terms = item_row.generated_snapshot -> 'glossary_terms'
            where concept_id = item_row.entity_key;
        elsif item_row.entity_type = 'formula' then
            update public.formulas
            set title = item_row.generated_snapshot ->> 'title',
                expression_markdown = item_row.generated_snapshot ->> 'expression_markdown',
                assumptions_markdown = item_row.generated_snapshot ->> 'assumptions_markdown',
                notes_markdown = item_row.generated_snapshot ->> 'notes_markdown',
                variables = item_row.generated_snapshot -> 'variables'
            where formula_id = item_row.entity_key;
        end if;
        if not found then
            raise exception using errcode = 'P0002', message = 'generation approval target was not found';
        end if;

        select revision.* into revision_row
        from public.content_revisions as revision
        where revision.entity_type = item_row.entity_type
          and revision.entity_key = item_row.entity_key
        order by revision.revision_number desc
        limit 1;
        if not found or public.current_revision_state(revision_row.revision_id) <> 'draft' then
            raise exception using errcode = '55000', message = 'approved generation did not create a draft revision';
        end if;

        update public.content_generation_items
        set revision_id = revision_row.revision_id
        where generation_item_id = item_row.generation_item_id;

        checks_total_value := (item_row.validation_summary ->> 'checksTotal')::integer;
        insert into public.validation_runs (
            target_type, revision_id, status, validator_name, validator_version,
            checks_total, checks_passed, checks_failed, summary, created_by
        ) values (
            'revision', revision_row.revision_id, 'queued',
            coalesce(nullif(item_row.validation_summary ->> 'validatorName', ''), 'findone-content-validator'),
            coalesce(nullif(item_row.validation_summary ->> 'validatorVersion', ''), 'admin-v2'),
            0, 0, 0, '{}'::jsonb, auth.uid()
        ) returning validation_run_id into validation_run_id_value;
        update public.validation_runs set status = 'running'
        where validation_run_id = validation_run_id_value;
        update public.validation_runs
        set status = 'passed', checks_total = checks_total_value,
            checks_passed = checks_total_value, checks_failed = 0,
            summary = item_row.validation_summary || jsonb_build_object(
                'generationBatchId', p_batch_id,
                'evidenceCount', (
                    select count(*) from public.content_generation_evidence as evidence
                    where evidence.generation_item_id = item_row.generation_item_id
                )
            )
        where validation_run_id = validation_run_id_value;

        insert into public.review_decisions (revision_id, decision, comment, reviewer_id)
        values (
            revision_row.revision_id, 'approved',
            coalesce(nullif(comment_value, ''), '로컬 변환 배치 최종 검토 승인'), auth.uid()
        );
        item_count_value := item_count_value + 1;
    end loop;

    if item_count_value <> batch_row.item_count then
        raise exception using errcode = '55000', message = 'generation item count changed before approval';
    end if;

    perform pg_advisory_xact_lock(hashtextextended('findone-content-version', 0));
    select coalesce(max(release.content_version), 5) + 1 into next_version
    from public.content_releases as release;
    insert into public.content_releases (
        content_version, version_name, schema_version, minimum_app_version,
        status, release_notes, create_request_key, created_by
    ) values (
        next_version,
        coalesce(nullif(btrim(batch_row.version_name), ''), 'content-v' || next_version::text),
        1, batch_row.minimum_app_version, 'draft', batch_row.release_notes,
        p_request_key, auth.uid()
    ) returning * into release_row;

    insert into public.release_items (
        release_id, revision_id, entity_type, entity_key,
        revision_number, content_hash, created_by
    )
    select release_row.release_id, revision.revision_id, revision.entity_type,
           revision.entity_key, revision.revision_number, revision.content_hash, auth.uid()
    from public.content_generation_items as item
    join public.content_revisions as revision on revision.revision_id = item.revision_id
    where item.batch_id = p_batch_id;

    perform set_config('app.release_transition_authorized', '1', true);
    update public.content_releases set status = 'building'
    where release_id = release_row.release_id returning * into release_row;
    insert into public.ingestion_jobs (job_kind, release_id, input, created_by)
    values (
        'release_build', release_row.release_id,
        jsonb_build_object(
            'releaseId', release_row.release_id,
            'contentVersion', next_version,
            'generationBatchId', p_batch_id
        ),
        auth.uid()
    );

    update public.content_generation_batches
    set status = 'releasing', progress_percent = 96, processing_stage = 'release_queued',
        approval_request_key = p_request_key, approval_comment = comment_value,
        approved_at = clock_timestamp(), approved_by = auth.uid(),
        release_id = release_row.release_id, completed_at = null
    where batch_id = p_batch_id;

    return jsonb_build_object(
        'batchId', p_batch_id, 'status', 'releasing',
        'releaseId', release_row.release_id,
        'contentVersion', next_version,
        'versionName', release_row.version_name,
        'itemCount', item_count_value
    );
end;
$$;

create or replace function public.reject_content_generation_batch(
    p_batch_id uuid,
    p_comment text
)
returns public.content_generation_batches
language plpgsql
security definer
set search_path = ''
as $$
declare
    result public.content_generation_batches%rowtype;
begin
    if not public.has_admin_role(array['owner', 'reviewer']::public.admin_role[]) then
        raise exception using errcode = '42501', message = 'reviewer role required';
    end if;
    if nullif(btrim(p_comment), '') is null or length(p_comment) > 4000 then
        raise exception using errcode = '22023', message = 'rejection reason is required';
    end if;
    update public.content_generation_batches
    set status = 'rejected', processing_stage = 'rejected',
        approval_comment = p_comment, completed_at = clock_timestamp()
    where batch_id = p_batch_id and status = 'ready_for_review'
    returning * into result;
    if not found then
        raise exception using errcode = '55000', message = 'only a final-review batch can be rejected';
    end if;
    return result;
end;
$$;

create or replace function public.sync_generation_release_status()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
    if new.status = 'published' and old.status is distinct from new.status then
        update public.content_generation_batches
        set status = 'released', progress_percent = 100,
            processing_stage = 'stable_released', completed_at = clock_timestamp(),
            error_message = null
        where release_id = new.release_id and status = 'releasing';
    elsif new.status in ('validation_failed', 'withdrawn') and old.status is distinct from new.status then
        update public.content_generation_batches
        set status = 'failed', progress_percent = 100,
            processing_stage = case when new.status = 'withdrawn' then 'release_withdrawn' else 'release_validation_failed' end,
            completed_at = clock_timestamp(),
            error_message = case when new.status = 'withdrawn'
                                 then 'approved release was withdrawn'
                                 else 'generated SQLite release failed validation' end
        where release_id = new.release_id and status = 'releasing';
    end if;
    return new;
end;
$$;

create trigger content_releases_sync_generation_status
after update of status on public.content_releases
for each row execute function public.sync_generation_release_status();

create view public.content_generation_overview
with (security_invoker = true)
as
select
    batch.*,
    coalesce(source_counts.value, 0) as source_count,
    coalesce(item_counts.value, 0) as persisted_item_count,
    coalesce(element_counts.value, 0) as persisted_changed_element_count,
    coalesce(evidence_counts.value, 0) as persisted_evidence_count,
    coalesce(run_counts.value, 0) as model_run_count,
    release.status as release_status,
    release.content_version as release_content_version,
    release.version_name as release_version_name
from public.content_generation_batches as batch
left join lateral (
    select count(*)::integer as value
    from public.content_generation_batch_sources as source
    where source.batch_id = batch.batch_id
) as source_counts on true
left join lateral (
    select count(*)::integer as value
    from public.content_generation_items as item
    where item.batch_id = batch.batch_id
) as item_counts on true
left join lateral (
    select count(distinct item.element_id)::integer as value
    from public.content_generation_items as item
    where item.batch_id = batch.batch_id
) as element_counts on true
left join lateral (
    select count(*)::integer as value
    from public.content_generation_evidence as evidence
    join public.content_generation_items as item
      on item.generation_item_id = evidence.generation_item_id
    where item.batch_id = batch.batch_id
) as evidence_counts on true
left join lateral (
    select count(*)::integer as value
    from public.content_model_runs as run
    where run.batch_id = batch.batch_id
) as run_counts on true
left join public.content_releases as release on release.release_id = batch.release_id;

grant select on public.content_generation_batches,
    public.content_generation_batch_sources,
    public.content_generation_items,
    public.content_generation_evidence,
    public.content_model_runs,
    public.content_generation_overview
to authenticated;

grant select, insert, update on public.content_generation_batches to service_role;
grant select, insert on public.content_generation_batch_sources,
    public.content_generation_items,
    public.content_generation_evidence,
    public.content_model_runs
to service_role;

revoke all on function public.generation_entity_snapshot(public.content_entity_type, text) from public, anon, authenticated;
revoke all on function public.queue_catalog_url_sources(text[], integer, boolean) from public, anon;
revoke all on function public.create_content_generation_batch(uuid, text, text, text, integer, uuid[], integer) from public, anon;
revoke all on function public.enqueue_ready_content_generation(text, text, integer) from public, anon, authenticated;
revoke all on function public.claim_content_generation_batch(text, text, text) from public, anon, authenticated;
revoke all on function public.update_content_generation_progress(uuid, text, integer, text, jsonb) from public, anon, authenticated;
revoke all on function public.get_content_generation_fragments(uuid, text, integer) from public, anon, authenticated;
revoke all on function public.complete_content_generation_batch(uuid, text, jsonb, jsonb, jsonb, jsonb) from public, anon, authenticated;
revoke all on function public.fail_content_generation_batch(uuid, text, text, jsonb) from public, anon, authenticated;
revoke all on function public.approve_content_generation_batch(uuid, uuid, text) from public, anon;
revoke all on function public.reject_content_generation_batch(uuid, text) from public, anon;
revoke all on function public.sync_generation_release_status() from public;

grant execute on function public.generation_entity_snapshot(public.content_entity_type, text) to service_role;
grant execute on function public.queue_catalog_url_sources(text[], integer, boolean) to authenticated, service_role;
grant execute on function public.create_content_generation_batch(uuid, text, text, text, integer, uuid[], integer) to authenticated, service_role;
grant execute on function public.enqueue_ready_content_generation(text, text, integer) to service_role;
grant execute on function public.claim_content_generation_batch(text, text, text) to service_role;
grant execute on function public.update_content_generation_progress(uuid, text, integer, text, jsonb) to service_role;
grant execute on function public.get_content_generation_fragments(uuid, text, integer) to service_role;
grant execute on function public.complete_content_generation_batch(uuid, text, jsonb, jsonb, jsonb, jsonb) to service_role;
grant execute on function public.fail_content_generation_batch(uuid, text, text, jsonb) to service_role;
grant execute on function public.approve_content_generation_batch(uuid, uuid, text) to authenticated, service_role;
grant execute on function public.reject_content_generation_batch(uuid, text) to authenticated, service_role;

comment on table public.content_generation_batches is
    'One evidence-scoped app-content generation run. Candidate data stays isolated until one final approval atomically creates revisions and a release.';
comment on table public.content_generation_evidence is
    'Field-level lineage from generated candidate fields to immutable parsed source fragments.';
comment on function public.approve_content_generation_batch(uuid, uuid, text) is
    'The only final-review action: apply candidates, record passed validation and approval snapshots, freeze a scoped release, and queue clean SQLite build.';

commit;
