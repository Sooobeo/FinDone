-- Standalone glossary authoring and release pipeline. Glossary packs are versioned
-- independently from learning content so term edits never require a new APK.
begin;

create table public.glossary_categories (
    category_id text primary key,
    name text not null,
    display_order integer not null unique,
    created_at timestamptz not null default clock_timestamp(),
    created_by uuid references auth.users(id) on delete set null,
    updated_at timestamptz not null default clock_timestamp(),
    updated_by uuid references auth.users(id) on delete set null,
    constraint glossary_category_id_format check (category_id ~ '^(0[1-9]|1[0-9]|2[01])$'),
    constraint glossary_category_name_length check (length(trim(name)) between 1 and 160),
    constraint glossary_category_order_range check (display_order between 0 and 20)
);

create table public.glossary_sources (
    source_code text primary key,
    title text not null,
    public_url text not null,
    created_at timestamptz not null default clock_timestamp(),
    created_by uuid references auth.users(id) on delete set null,
    updated_at timestamptz not null default clock_timestamp(),
    updated_by uuid references auth.users(id) on delete set null,
    constraint glossary_source_code_format check (source_code ~ '^S[0-9]{2}$'),
    constraint glossary_source_title_length check (length(trim(title)) between 1 and 300),
    constraint glossary_source_public_https check (public_url ~ '^https://')
);

create table public.glossary_terms (
    term_id text primary key,
    category_id text not null references public.glossary_categories(category_id),
    display_order integer not null,
    canonical_name_en text not null,
    canonical_name_ko text not null,
    aliases text[] not null default '{}',
    concept_type text not null,
    one_line_definition_ko text not null,
    core_definition_ko text not null,
    practical_context_ko text not null,
    why_it_matters_ko text not null,
    example_ko text not null,
    limitations_ko text[] not null,
    source_codes text[] not null,
    jurisdictions text[] not null,
    as_of_date date not null,
    review_status text not null default 'agent_reviewed',
    review_flags text[] not null default '{}',
    related_term_ids text[] not null default '{}',
    formula_latex text not null default '',
    formula_notes_ko text not null default '',
    is_active boolean not null default true,
    content_revision bigint not null default 1,
    change_reason text not null default '용어집 초기 적재',
    archived_at timestamptz,
    archived_by uuid references auth.users(id) on delete set null,
    created_at timestamptz not null default clock_timestamp(),
    created_by uuid references auth.users(id) on delete set null,
    updated_at timestamptz not null default clock_timestamp(),
    updated_by uuid references auth.users(id) on delete set null,
    constraint glossary_term_id_format check (
        term_id ~ '^FIN-(0[1-9]|1[0-9]|2[01])-[0-9]{3}$'
    ),
    constraint glossary_term_category_matches check (substring(term_id from 5 for 2) = category_id),
    constraint glossary_term_order_nonnegative check (display_order >= 0),
    constraint glossary_term_names_present check (
        length(trim(canonical_name_en)) between 1 and 240
        and length(trim(canonical_name_ko)) between 1 and 240
        and canonical_name_en !~ '[|\r\n]'
        and canonical_name_ko !~ '[|\r\n]'
        and array_to_string(aliases, chr(31)) !~ '[|\r\n]'
    ),
    constraint glossary_term_copy_present check (
        length(trim(one_line_definition_ko)) >= 18
        and length(trim(core_definition_ko)) >= 35
        and length(trim(practical_context_ko)) >= 18
        and length(trim(why_it_matters_ko)) >= 12
        and length(trim(example_ko)) >= 15
    ),
    constraint glossary_term_arrays_present check (
        cardinality(limitations_ko) >= 1
        and cardinality(source_codes) >= 1
        and cardinality(jurisdictions) >= 1
    ),
    constraint glossary_term_source_code_format check (
        array_to_string(source_codes, ',') ~ '^S[0-9]{2}(,S[0-9]{2})*$'
    ),
    constraint glossary_term_jurisdiction_codes check (
        jurisdictions <@ array['GLOBAL','KR','US','EU','UK','JP','CN','MULTI']::text[]
    ),
    constraint glossary_term_related_id_format check (
        cardinality(related_term_ids) = 0
        or array_to_string(related_term_ids, ',') ~
            '^FIN-(0[1-9]|1[0-9]|2[01])-[0-9]{3}(,FIN-(0[1-9]|1[0-9]|2[01])-[0-9]{3})*$'
    ),
    constraint glossary_term_not_self_related check (not (term_id = any(related_term_ids))),
    constraint glossary_term_review_status check (review_status in ('agent_reviewed', 'approved')),
    constraint glossary_term_concept_type check (concept_type in (
        'INSTITUTION','BUSINESS_FUNCTION','ORG_UNIT','ROLE','ASSET_CLASS','INSTRUMENT',
        'STRATEGY','DEAL','PROCESS','ACTIVITY','METHODOLOGY','MODEL','METRIC',
        'ACCOUNTING_CONCEPT','RISK','EVENT','ARTIFACT','DISCLOSURE','REGULATION',
        'MARKET_INFRA','DATA_SOURCE','IDENTIFIER','TOOL_SKILL','SECTOR'
    )),
    constraint glossary_term_archival_consistent check (
        (is_active and archived_at is null and archived_by is null)
        or (not is_active and archived_at is not null)
    ),
    unique (category_id, display_order)
);

create index glossary_terms_active_category_idx
    on public.glossary_terms(category_id, display_order) where is_active;
create index glossary_terms_updated_idx on public.glossary_terms(updated_at desc, term_id);

-- Private originals/evidence are linked for Admin review only. This table is
-- deliberately absent from claim_glossary_compile_job() and therefore from Android.
create table public.glossary_term_admin_references (
    term_id text not null references public.glossary_terms(term_id) on delete cascade,
    source_id text not null references public.sources(source_id) on delete restrict,
    created_at timestamptz not null default clock_timestamp(),
    created_by uuid references auth.users(id) on delete set null,
    primary key (term_id, source_id)
);
create index glossary_term_admin_references_source_idx
    on public.glossary_term_admin_references(source_id, term_id);

create table public.glossary_settings (
    setting_key text primary key,
    setting_value text not null,
    updated_at timestamptz not null default clock_timestamp()
);

create table public.glossary_releases (
    release_id uuid primary key default extensions.gen_random_uuid(),
    glossary_version bigint not null unique,
    version_name text not null unique,
    schema_version integer not null default 1,
    minimum_app_version integer not null default 1,
    status text not null default 'building',
    release_notes text not null default '',
    term_count integer not null,
    inventory_sha256 text,
    catalog_sha256 text,
    manifest_sha256 text,
    database_sha256 text,
    database_byte_size bigint,
    published_at timestamptz,
    created_at timestamptz not null default clock_timestamp(),
    created_by uuid references auth.users(id) on delete set null,
    updated_at timestamptz not null default clock_timestamp(),
    updated_by uuid references auth.users(id) on delete set null,
    constraint glossary_release_version_positive check (glossary_version > 0),
    constraint glossary_release_schema check (schema_version = 1),
    constraint glossary_release_app_version check (minimum_app_version > 0),
    constraint glossary_release_status check (status in ('building','published','failed','withdrawn')),
    constraint glossary_release_term_count check (term_count > 0),
    constraint glossary_release_hashes check (
        (status <> 'published') or (
            inventory_sha256 ~ '^[0-9a-f]{64}$'
            and catalog_sha256 ~ '^[0-9a-f]{64}$'
            and manifest_sha256 ~ '^[0-9a-f]{64}$'
            and database_sha256 ~ '^[0-9a-f]{64}$'
            and database_byte_size > 0
            and published_at is not null
        )
    )
);

create table public.glossary_compile_jobs (
    job_id uuid primary key default extensions.gen_random_uuid(),
    release_id uuid not null unique references public.glossary_releases(release_id),
    status text not null default 'queued',
    worker_id text,
    attempt_count integer not null default 0,
    progress_percent integer not null default 0,
    error_message text,
    output jsonb not null default '{}'::jsonb,
    claimed_at timestamptz,
    completed_at timestamptz,
    created_at timestamptz not null default clock_timestamp(),
    updated_at timestamptz not null default clock_timestamp(),
    constraint glossary_compile_status check (status in ('queued','running','succeeded','failed','cancelled')),
    constraint glossary_compile_attempt check (attempt_count >= 0),
    constraint glossary_compile_progress check (progress_percent between 0 and 100),
    constraint glossary_compile_worker_length check (worker_id is null or length(worker_id) between 1 and 128),
    constraint glossary_compile_error_length check (error_message is null or length(error_message) <= 2000)
);

create index glossary_compile_jobs_claim_idx
    on public.glossary_compile_jobs(status, created_at, job_id)
    where status in ('queued','running');

create table public.glossary_release_artifacts (
    artifact_id uuid primary key default extensions.gen_random_uuid(),
    release_id uuid not null references public.glossary_releases(release_id) on delete cascade,
    artifact_kind text not null,
    bucket_id text not null default 'release-bundles',
    object_path text not null unique,
    sha256 text not null,
    byte_size bigint not null,
    created_at timestamptz not null default clock_timestamp(),
    constraint glossary_artifact_kind check (artifact_kind in ('glossary_database','manifest')),
    constraint glossary_artifact_bucket check (bucket_id = 'release-bundles'),
    constraint glossary_artifact_hash check (sha256 ~ '^[0-9a-f]{64}$'),
    constraint glossary_artifact_size check (byte_size > 0),
    unique (release_id, artifact_kind)
);

create table public.glossary_release_channels (
    channel text primary key,
    release_id uuid not null references public.glossary_releases(release_id),
    activated_at timestamptz not null default clock_timestamp(),
    activated_by uuid references auth.users(id) on delete set null,
    constraint glossary_channel_name check (channel ~ '^[a-z][a-z0-9_-]{1,31}$')
);

create trigger glossary_categories_audit
before insert or update on public.glossary_categories
for each row execute function public.set_audit_columns();
create trigger glossary_sources_audit
before insert or update on public.glossary_sources
for each row execute function public.set_audit_columns();
create trigger glossary_terms_audit
before insert or update on public.glossary_terms
for each row execute function public.set_audit_columns();
create trigger glossary_releases_audit
before insert or update on public.glossary_releases
for each row execute function public.set_audit_columns();

alter table public.glossary_categories enable row level security;
alter table public.glossary_sources enable row level security;
alter table public.glossary_terms enable row level security;
alter table public.glossary_term_admin_references enable row level security;
alter table public.glossary_settings enable row level security;
alter table public.glossary_releases enable row level security;
alter table public.glossary_compile_jobs enable row level security;
alter table public.glossary_release_artifacts enable row level security;
alter table public.glossary_release_channels enable row level security;

create policy glossary_categories_owner_select on public.glossary_categories
for select to authenticated using ((select public.is_admin()));
create policy glossary_sources_owner_select on public.glossary_sources
for select to authenticated using ((select public.is_admin()));
create policy glossary_terms_owner_select on public.glossary_terms
for select to authenticated using ((select public.is_admin()));
create policy glossary_term_admin_references_owner_select on public.glossary_term_admin_references
for select to authenticated using ((select public.is_admin()));
create policy glossary_settings_owner_select on public.glossary_settings
for select to authenticated using ((select public.is_admin()));
create policy glossary_releases_owner_select on public.glossary_releases
for select to authenticated using ((select public.is_admin()));
create policy glossary_compile_jobs_owner_select on public.glossary_compile_jobs
for select to authenticated using ((select public.is_admin()));
create policy glossary_artifacts_owner_select on public.glossary_release_artifacts
for select to authenticated using ((select public.is_admin()));
create policy glossary_channels_owner_select on public.glossary_release_channels
for select to authenticated using ((select public.is_admin()));

create or replace function public.glossary_text_array(p_value jsonb)
returns text[]
language sql
immutable
set search_path = ''
as $$
    select coalesce(array_agg(normalized.value order by normalized.first_ordinality), '{}'::text[])
    from (
        select trim(item.value) as value, min(item.ordinality) as first_ordinality
        from jsonb_array_elements_text(coalesce(p_value, '[]'::jsonb))
            with ordinality as item(value, ordinality)
        where trim(item.value) <> ''
        group by trim(item.value)
    ) as normalized;
$$;

create or replace function public.queue_glossary_compile(
    p_release_notes text default 'Admin 용어집 변경',
    p_minimum_app_version integer default 1
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
    existing_job public.glossary_compile_jobs%rowtype;
    release_row public.glossary_releases%rowtype;
    next_version bigint;
    active_count integer;
begin
    if not public.has_admin_role(array['owner']::public.admin_role[]) then
        raise exception using errcode = '42501', message = 'owner role required';
    end if;
    if p_minimum_app_version < 1 then
        raise exception using errcode = '22023', message = 'minimum app version must be positive';
    end if;
    select count(*)::integer into active_count from public.glossary_terms where is_active;
    if active_count < 1 then
        raise exception using errcode = '23514', message = 'cannot compile an empty glossary';
    end if;

    lock table public.glossary_releases in share row exclusive mode;

    select job.* into existing_job
    from public.glossary_compile_jobs as job
    where job.status = 'queued'
    order by job.created_at desc
    limit 1
    for update;
    if found then
        update public.glossary_releases
        set release_notes = left(coalesce(nullif(trim(p_release_notes), ''), release_notes), 2000),
            minimum_app_version = p_minimum_app_version,
            term_count = active_count
        where release_id = existing_job.release_id
        returning * into release_row;
        return jsonb_build_object(
            'jobId', existing_job.job_id,
            'releaseId', release_row.release_id,
            'glossaryDbVersion', release_row.glossary_version,
            'status', existing_job.status,
            'coalesced', true
        );
    end if;

    select coalesce(max(glossary_version), 0) + 1 into next_version
    from public.glossary_releases;
    insert into public.glossary_releases (
        glossary_version, version_name, minimum_app_version, status,
        release_notes, term_count, created_by, updated_by
    ) values (
        next_version, 'glossary-v' || next_version::text, p_minimum_app_version, 'building',
        left(coalesce(p_release_notes, ''), 2000), active_count, auth.uid(), auth.uid()
    ) returning * into release_row;
    insert into public.glossary_compile_jobs (release_id)
    values (release_row.release_id)
    returning * into existing_job;
    return jsonb_build_object(
        'jobId', existing_job.job_id,
        'releaseId', release_row.release_id,
        'glossaryDbVersion', release_row.glossary_version,
        'status', existing_job.status,
        'coalesced', false
    );
end;
$$;

create or replace function public.save_glossary_term_and_queue_compile(
    p_term_id text,
    p_term jsonb,
    p_change_reason text default 'Admin 용어 수정'
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
    saved public.glossary_terms%rowtype;
    queued jsonb;
    source_values text[];
begin
    if not public.has_admin_role(array['owner']::public.admin_role[]) then
        raise exception using errcode = '42501', message = 'owner role required';
    end if;
    if p_term_id !~ '^FIN-(0[1-9]|1[0-9]|2[01])-[0-9]{3}$'
       or coalesce(p_term->>'termId', '') <> p_term_id then
        raise exception using errcode = '22023', message = 'term ID does not match the request';
    end if;
    source_values := public.glossary_text_array(p_term->'sourceCodes');
    if exists (
        select 1 from unnest(source_values) as code
        where not exists (select 1 from public.glossary_sources where source_code = code)
    ) then
        raise exception using errcode = '23503', message = 'term contains an unknown source code';
    end if;

    update public.glossary_terms
    set category_id = p_term->>'categoryId',
        display_order = (p_term->>'displayOrder')::integer,
        canonical_name_en = p_term->>'canonicalNameEn',
        canonical_name_ko = p_term->>'canonicalNameKo',
        aliases = public.glossary_text_array(p_term->'aliases'),
        concept_type = p_term->>'conceptType',
        one_line_definition_ko = p_term->>'oneLineDefinitionKo',
        core_definition_ko = p_term->>'coreDefinitionKo',
        practical_context_ko = p_term->>'practicalContextKo',
        why_it_matters_ko = p_term->>'whyItMattersKo',
        example_ko = p_term->>'exampleKo',
        limitations_ko = public.glossary_text_array(p_term->'limitationsKo'),
        source_codes = source_values,
        jurisdictions = public.glossary_text_array(p_term->'jurisdictions'),
        as_of_date = (p_term->>'asOfDate')::date,
        review_status = p_term->>'reviewStatus',
        review_flags = public.glossary_text_array(p_term->'reviewFlags'),
        related_term_ids = public.glossary_text_array(p_term->'relatedTermIds'),
        formula_latex = coalesce(p_term->>'formulaLatex', ''),
        formula_notes_ko = coalesce(p_term->>'formulaNotesKo', ''),
        is_active = true,
        content_revision = content_revision + 1,
        change_reason = left(coalesce(nullif(trim(p_change_reason), ''), 'Admin 용어 수정'), 500),
        archived_at = null,
        archived_by = null
    where term_id = p_term_id
    returning * into saved;
    if not found then
        raise exception using errcode = 'P0002', message = 'glossary term not found';
    end if;
    if exists (
        select 1
        from unnest(public.glossary_text_array(p_term->'adminReferenceSourceIds')) as requested(source_id)
        where not exists (
            select 1 from public.sources
            where sources.source_id = requested.source_id and sources.is_active
        )
    ) then
        raise exception using errcode = '23503', message = 'term contains an unknown private Admin reference';
    end if;
    delete from public.glossary_term_admin_references where term_id = p_term_id;
    insert into public.glossary_term_admin_references(term_id, source_id, created_by)
    select p_term_id, requested.source_id, auth.uid()
    from unnest(public.glossary_text_array(p_term->'adminReferenceSourceIds')) as requested(source_id);
    queued := public.queue_glossary_compile('용어 수정 · ' || p_term_id, 1);
    return jsonb_build_object('term', to_jsonb(saved), 'compile', queued);
end;
$$;

create or replace function public.archive_glossary_term_and_queue_compile(
    p_term_id text,
    p_change_reason text default 'Admin 용어 삭제'
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
    archived public.glossary_terms%rowtype;
    queued jsonb;
begin
    if not public.has_admin_role(array['owner']::public.admin_role[]) then
        raise exception using errcode = '42501', message = 'owner role required';
    end if;
    update public.glossary_terms
    set is_active = false,
        content_revision = content_revision + 1,
        change_reason = left(coalesce(nullif(trim(p_change_reason), ''), 'Admin 용어 삭제'), 500),
        archived_at = clock_timestamp(),
        archived_by = auth.uid()
    where term_id = p_term_id and is_active
    returning * into archived;
    if not found then
        raise exception using errcode = 'P0002', message = 'active glossary term not found';
    end if;
    queued := public.queue_glossary_compile('용어 삭제 · ' || p_term_id, 1);
    return jsonb_build_object('termId', archived.term_id, 'archived', true, 'compile', queued);
end;
$$;

create or replace function public.import_glossary_snapshot(p_snapshot jsonb)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
    category_count integer;
    source_count integer;
    term_count integer;
    queued jsonb;
begin
    if jsonb_typeof(p_snapshot) <> 'object' then
        raise exception using errcode = '22023', message = 'glossary snapshot must be an object';
    end if;
    select count(*)::integer into category_count from jsonb_array_elements(p_snapshot->'categories');
    select count(*)::integer into source_count from jsonb_array_elements(p_snapshot->'sources');
    select count(*)::integer into term_count from jsonb_array_elements(p_snapshot->'terms');
    if category_count <> 21 or source_count < 1 or term_count < 1 then
        raise exception using errcode = '23514', message = 'glossary snapshot coverage is incomplete';
    end if;

    insert into public.glossary_categories (category_id, name, display_order)
    select item->>'categoryId', item->>'name', (item->>'displayOrder')::integer
    from jsonb_array_elements(p_snapshot->'categories') as item
    on conflict (category_id) do update set
        name = excluded.name,
        display_order = excluded.display_order;

    insert into public.glossary_sources (source_code, title, public_url)
    select item->>'sourceCode', item->>'title', item->>'url'
    from jsonb_array_elements(p_snapshot->'sources') as item
    on conflict (source_code) do update set
        title = excluded.title,
        public_url = excluded.public_url;

    update public.glossary_terms
    set is_active = false,
        archived_at = clock_timestamp(),
        archived_by = auth.uid(),
        change_reason = '용어집 snapshot 교체'
    where is_active = true;

    insert into public.glossary_terms (
        term_id, category_id, display_order, canonical_name_en, canonical_name_ko,
        aliases, concept_type, one_line_definition_ko, core_definition_ko,
        practical_context_ko, why_it_matters_ko, example_ko, limitations_ko,
        source_codes, jurisdictions, as_of_date, review_status, review_flags,
        related_term_ids, formula_latex, formula_notes_ko, is_active,
        content_revision, change_reason, archived_at, archived_by
    )
    select
        item->>'termId', item->>'categoryId', (item->>'displayOrder')::integer,
        item->>'canonicalNameEn', item->>'canonicalNameKo',
        public.glossary_text_array(item->'aliases'), item->>'conceptType',
        item->>'oneLineDefinitionKo', item->>'coreDefinitionKo',
        item->>'practicalContextKo', item->>'whyItMattersKo', item->>'exampleKo',
        public.glossary_text_array(item->'limitationsKo'),
        public.glossary_text_array(item->'sourceCodes'),
        public.glossary_text_array(item->'jurisdictions'),
        (item->>'asOfDate')::date, item->>'reviewStatus',
        public.glossary_text_array(item->'reviewFlags'),
        public.glossary_text_array(item->'relatedTermIds'),
        coalesce(item->>'formulaLatex', ''), coalesce(item->>'formulaNotesKo', ''),
        true, 1, '용어집 snapshot 적재', null, null
    from jsonb_array_elements(p_snapshot->'terms') as item
    on conflict (term_id) do update set
        category_id = excluded.category_id,
        display_order = excluded.display_order,
        canonical_name_en = excluded.canonical_name_en,
        canonical_name_ko = excluded.canonical_name_ko,
        aliases = excluded.aliases,
        concept_type = excluded.concept_type,
        one_line_definition_ko = excluded.one_line_definition_ko,
        core_definition_ko = excluded.core_definition_ko,
        practical_context_ko = excluded.practical_context_ko,
        why_it_matters_ko = excluded.why_it_matters_ko,
        example_ko = excluded.example_ko,
        limitations_ko = excluded.limitations_ko,
        source_codes = excluded.source_codes,
        jurisdictions = excluded.jurisdictions,
        as_of_date = excluded.as_of_date,
        review_status = excluded.review_status,
        review_flags = excluded.review_flags,
        related_term_ids = excluded.related_term_ids,
        formula_latex = excluded.formula_latex,
        formula_notes_ko = excluded.formula_notes_ko,
        is_active = true,
        content_revision = public.glossary_terms.content_revision + 1,
        change_reason = excluded.change_reason,
        archived_at = null,
        archived_by = null;

    insert into public.glossary_settings(setting_key, setting_value, updated_at) values
        ('inventory_sha256', p_snapshot->>'inventorySha256', clock_timestamp()),
        ('catalog_sha256', p_snapshot->>'catalogSha256', clock_timestamp()),
        ('generation_model', coalesce(p_snapshot->>'generationModel', 'codex-authoring-agent'), clock_timestamp())
    on conflict (setting_key) do update set
        setting_value = excluded.setting_value,
        updated_at = excluded.updated_at;

    queued := public.queue_glossary_compile('용어집 snapshot 적재', 1);
    return jsonb_build_object(
        'categories', category_count,
        'sources', source_count,
        'terms', term_count,
        'compile', queued
    );
end;
$$;

create or replace function public.claim_glossary_compile_job(p_worker_id text)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
    claimed public.glossary_compile_jobs%rowtype;
    release_row public.glossary_releases%rowtype;
    snapshot jsonb;
begin
    if length(coalesce(p_worker_id, '')) not between 1 and 128 then
        raise exception using errcode = '22023', message = 'worker ID is invalid';
    end if;
    update public.glossary_compile_jobs
    set status = 'queued', worker_id = null, claimed_at = null,
        error_message = 'stale worker lease reclaimed', updated_at = clock_timestamp()
    where status = 'running' and claimed_at < clock_timestamp() - interval '30 minutes';

    select * into claimed
    from public.glossary_compile_jobs
    where status = 'queued'
    order by created_at, job_id
    limit 1
    for update skip locked;
    if not found then return null; end if;
    update public.glossary_compile_jobs
    set status = 'running', worker_id = p_worker_id, claimed_at = clock_timestamp(),
        attempt_count = attempt_count + 1, progress_percent = 5,
        error_message = null, updated_at = clock_timestamp()
    where job_id = claimed.job_id
    returning * into claimed;
    select * into release_row from public.glossary_releases where release_id = claimed.release_id;

    snapshot := jsonb_build_object(
        'inventorySha256', coalesce((select setting_value from public.glossary_settings where setting_key = 'inventory_sha256'), repeat('0', 64)),
        'categories', coalesce((
            select jsonb_agg(jsonb_build_object(
                'categoryId', category_id, 'name', name, 'displayOrder', display_order
            ) order by display_order)
            from public.glossary_categories
        ), '[]'::jsonb),
        'sources', coalesce((
            select jsonb_agg(jsonb_build_object(
                'sourceCode', source_code, 'title', title, 'url', public_url
            ) order by source_code)
            from public.glossary_sources
        ), '[]'::jsonb),
        'terms', coalesce((
            select jsonb_agg(jsonb_build_object(
                'termId', term_id, 'categoryId', category_id, 'displayOrder', display_order,
                'canonicalNameEn', canonical_name_en, 'canonicalNameKo', canonical_name_ko,
                'aliases', to_jsonb(aliases), 'conceptType', concept_type,
                'oneLineDefinitionKo', one_line_definition_ko,
                'coreDefinitionKo', core_definition_ko,
                'practicalContextKo', practical_context_ko,
                'whyItMattersKo', why_it_matters_ko, 'exampleKo', example_ko,
                'limitationsKo', to_jsonb(limitations_ko), 'sourceCodes', to_jsonb(source_codes),
                'jurisdictions', to_jsonb(jurisdictions), 'asOfDate', as_of_date::text,
                'reviewStatus', review_status, 'reviewFlags', to_jsonb(review_flags),
                'relatedTermIds', to_jsonb(related_term_ids), 'formulaLatex', formula_latex,
                'formulaNotesKo', formula_notes_ko
            ) order by category_id, display_order)
            from public.glossary_terms where is_active
        ), '[]'::jsonb)
    );
    return jsonb_build_object(
        'jobId', claimed.job_id,
        'releaseId', release_row.release_id,
        'glossaryDbVersion', release_row.glossary_version,
        'versionName', release_row.version_name,
        'schemaVersion', release_row.schema_version,
        'minimumAppVersion', release_row.minimum_app_version,
        'releaseNotes', release_row.release_notes,
        'snapshot', snapshot
    );
end;
$$;

create or replace function public.complete_glossary_compile_job(
    p_job_id uuid,
    p_worker_id text,
    p_inventory_sha256 text,
    p_catalog_sha256 text,
    p_manifest_sha256 text,
    p_database_sha256 text,
    p_database_byte_size bigint,
    p_manifest_byte_size bigint,
    p_database_object_path text,
    p_manifest_object_path text,
    p_term_count integer,
    p_output jsonb default '{}'::jsonb
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
    job_row public.glossary_compile_jobs%rowtype;
    release_row public.glossary_releases%rowtype;
    current_version bigint;
    activated boolean := false;
begin
    select * into job_row from public.glossary_compile_jobs where job_id = p_job_id for update;
    if not found or job_row.status <> 'running' or job_row.worker_id <> p_worker_id then
        raise exception using errcode = '55000', message = 'glossary compile job lease is not active';
    end if;
    select * into release_row from public.glossary_releases where release_id = job_row.release_id for update;
    if p_inventory_sha256 !~ '^[0-9a-f]{64}$' or p_catalog_sha256 !~ '^[0-9a-f]{64}$'
       or p_manifest_sha256 !~ '^[0-9a-f]{64}$' or p_database_sha256 !~ '^[0-9a-f]{64}$'
       or p_database_byte_size < 1 or p_manifest_byte_size < 1 or p_term_count < 1 then
        raise exception using errcode = '22023', message = 'compiled glossary metadata is invalid';
    end if;
    if p_term_count <> release_row.term_count then
        raise exception using errcode = '40001', message = 'compiled glossary snapshot is stale';
    end if;
    if p_database_object_path <> ('glossary/' || release_row.release_id::text || '/glossary.sqlite3')
       or p_manifest_object_path <> ('glossary/' || release_row.release_id::text || '/glossary-manifest.json') then
        raise exception using errcode = '22023', message = 'glossary artifact path is invalid';
    end if;
    if not exists (
        select 1 from storage.objects where bucket_id = 'release-bundles' and name = p_database_object_path
    ) or not exists (
        select 1 from storage.objects where bucket_id = 'release-bundles' and name = p_manifest_object_path
    ) then
        raise exception using errcode = 'P0002', message = 'uploaded glossary artifacts were not found';
    end if;

    insert into public.glossary_release_artifacts(
        release_id, artifact_kind, object_path, sha256, byte_size
    ) values
        (release_row.release_id, 'glossary_database', p_database_object_path, p_database_sha256, p_database_byte_size),
        (release_row.release_id, 'manifest', p_manifest_object_path, p_manifest_sha256, p_manifest_byte_size)
    on conflict (release_id, artifact_kind) do update set
        object_path = excluded.object_path,
        sha256 = excluded.sha256,
        byte_size = excluded.byte_size;

    update public.glossary_releases
    set status = 'published', inventory_sha256 = p_inventory_sha256,
        catalog_sha256 = p_catalog_sha256, manifest_sha256 = p_manifest_sha256,
        database_sha256 = p_database_sha256, database_byte_size = p_database_byte_size,
        term_count = p_term_count, published_at = clock_timestamp()
    where release_id = release_row.release_id
    returning * into release_row;
    update public.glossary_compile_jobs
    set status = 'succeeded', progress_percent = 100, output = coalesce(p_output, '{}'::jsonb),
        completed_at = clock_timestamp(), updated_at = clock_timestamp()
    where job_id = p_job_id;

    select release.glossary_version into current_version
    from public.glossary_release_channels channel
    join public.glossary_releases release on release.release_id = channel.release_id
    where channel.channel = 'stable';
    if current_version is null or current_version <= release_row.glossary_version then
        insert into public.glossary_release_channels(channel, release_id, activated_at, activated_by)
        values ('stable', release_row.release_id, clock_timestamp(), null)
        on conflict (channel) do update set
            release_id = excluded.release_id,
            activated_at = excluded.activated_at,
            activated_by = excluded.activated_by;
        activated := true;
    end if;
    return jsonb_build_object(
        'jobId', p_job_id, 'releaseId', release_row.release_id,
        'glossaryDbVersion', release_row.glossary_version,
        'status', 'published', 'stableActivated', activated
    );
end;
$$;

create or replace function public.fail_glossary_compile_job(
    p_job_id uuid,
    p_worker_id text,
    p_error_message text
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
    job_row public.glossary_compile_jobs%rowtype;
begin
    select * into job_row from public.glossary_compile_jobs where job_id = p_job_id for update;
    if not found or job_row.status <> 'running' or job_row.worker_id <> p_worker_id then
        raise exception using errcode = '55000', message = 'glossary compile job lease is not active';
    end if;
    update public.glossary_compile_jobs
    set status = 'failed', error_message = left(coalesce(p_error_message, 'unknown error'), 2000),
        completed_at = clock_timestamp(), updated_at = clock_timestamp()
    where job_id = p_job_id;
    update public.glossary_releases set status = 'failed' where release_id = job_row.release_id;
    return jsonb_build_object('jobId', p_job_id, 'status', 'failed');
end;
$$;

revoke all on table public.glossary_categories from public, anon, authenticated;
revoke all on table public.glossary_sources from public, anon, authenticated;
revoke all on table public.glossary_terms from public, anon, authenticated;
revoke all on table public.glossary_term_admin_references from public, anon, authenticated;
revoke all on table public.glossary_settings from public, anon, authenticated;
revoke all on table public.glossary_releases from public, anon, authenticated;
revoke all on table public.glossary_compile_jobs from public, anon, authenticated;
revoke all on table public.glossary_release_artifacts from public, anon, authenticated;
revoke all on table public.glossary_release_channels from public, anon, authenticated;
grant select on public.glossary_categories, public.glossary_sources, public.glossary_terms,
    public.glossary_term_admin_references, public.glossary_settings,
    public.glossary_releases, public.glossary_compile_jobs,
    public.glossary_release_artifacts, public.glossary_release_channels to authenticated;
grant select on public.glossary_releases, public.glossary_release_artifacts,
    public.glossary_release_channels to service_role;

revoke all on function public.glossary_text_array(jsonb) from public, anon, authenticated;
revoke all on function public.queue_glossary_compile(text, integer) from public, anon;
revoke all on function public.save_glossary_term_and_queue_compile(text, jsonb, text) from public, anon;
revoke all on function public.archive_glossary_term_and_queue_compile(text, text) from public, anon;
revoke all on function public.import_glossary_snapshot(jsonb) from public, anon, authenticated;
revoke all on function public.claim_glossary_compile_job(text) from public, anon, authenticated;
revoke all on function public.complete_glossary_compile_job(
    uuid,text,text,text,text,text,bigint,bigint,text,text,integer,jsonb
) from public, anon, authenticated;
revoke all on function public.fail_glossary_compile_job(uuid,text,text) from public, anon, authenticated;

grant execute on function public.queue_glossary_compile(text, integer) to authenticated;
grant execute on function public.save_glossary_term_and_queue_compile(text, jsonb, text) to authenticated;
grant execute on function public.archive_glossary_term_and_queue_compile(text, text) to authenticated;
grant execute on function public.import_glossary_snapshot(jsonb) to service_role;
grant execute on function public.claim_glossary_compile_job(text) to service_role;
grant execute on function public.complete_glossary_compile_job(
    uuid,text,text,text,text,text,bigint,bigint,text,text,integer,jsonb
) to service_role;
grant execute on function public.fail_glossary_compile_job(uuid,text,text) to service_role;

commit;
