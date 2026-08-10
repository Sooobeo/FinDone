begin;

create type public.source_kind as enum ('url', 'file', 'text', 'reference');
create type public.source_parse_status as enum (
    'pending',
    'fetching',
    'extracting',
    'ready',
    'failed',
    'archived'
);
create type public.source_file_role as enum (
    'original',
    'snapshot',
    'extracted_text',
    'ocr',
    'attachment'
);
create type public.content_entity_type as enum (
    'domain',
    'element',
    'concept',
    'formula',
    'distractor'
);

create table public.domains (
    domain_id text primary key,
    name text not null,
    description text not null default '',
    expected_element_count integer check (expected_element_count is null or expected_element_count >= 0),
    display_order integer not null,
    color_token text not null default 'research.default',
    is_active boolean not null default true,
    created_at timestamptz not null default clock_timestamp(),
    created_by uuid references auth.users(id) on delete set null,
    updated_at timestamptz not null default clock_timestamp(),
    updated_by uuid references auth.users(id) on delete set null,
    constraint domains_id_format check (domain_id ~ '^[A-Z][A-Z0-9_]{1,15}$'),
    constraint domains_name_not_blank check (btrim(name) <> ''),
    constraint domains_display_order_unique unique (display_order)
);

create table public.sources (
    source_id text primary key,
    kind public.source_kind not null,
    label text not null,
    locator text not null default '',
    source_type text not null default '',
    notes text not null default '',
    is_active boolean not null default true,
    created_at timestamptz not null default clock_timestamp(),
    created_by uuid references auth.users(id) on delete set null,
    updated_at timestamptz not null default clock_timestamp(),
    updated_by uuid references auth.users(id) on delete set null,
    constraint sources_id_not_blank check (btrim(source_id) <> ''),
    constraint sources_label_not_blank check (btrim(label) <> ''),
    constraint sources_url_locator check (
        kind <> 'url' or locator ~* '^https?://'
    )
);

create table public.source_versions (
    source_version_id uuid primary key default gen_random_uuid(),
    source_id text not null references public.sources(source_id) on delete restrict,
    version_number integer not null check (version_number > 0),
    fetch_url text,
    original_filename text,
    mime_type text,
    byte_size bigint check (byte_size is null or byte_size >= 0),
    sha256 text check (sha256 is null or sha256 ~ '^[0-9a-f]{64}$'),
    parse_status public.source_parse_status not null default 'pending',
    extracted_text text,
    extraction_metadata jsonb not null default '{}'::jsonb,
    failure_message text,
    captured_at timestamptz,
    created_at timestamptz not null default clock_timestamp(),
    created_by uuid references auth.users(id) on delete set null,
    updated_at timestamptz not null default clock_timestamp(),
    updated_by uuid references auth.users(id) on delete set null,
    constraint source_versions_source_number_unique unique (source_id, version_number),
    constraint source_versions_metadata_object check (jsonb_typeof(extraction_metadata) = 'object'),
    constraint source_versions_failure_message check (
        parse_status <> 'failed' or nullif(btrim(failure_message), '') is not null
    )
);

create table public.source_files (
    source_file_id uuid primary key default gen_random_uuid(),
    source_version_id uuid not null references public.source_versions(source_version_id) on delete restrict,
    file_role public.source_file_role not null,
    bucket_id text not null default 'source-private',
    object_path text not null,
    original_filename text,
    mime_type text,
    byte_size bigint check (byte_size is null or byte_size >= 0),
    sha256 text check (sha256 is null or sha256 ~ '^[0-9a-f]{64}$'),
    created_at timestamptz not null default clock_timestamp(),
    created_by uuid references auth.users(id) on delete set null,
    updated_at timestamptz not null default clock_timestamp(),
    updated_by uuid references auth.users(id) on delete set null,
    constraint source_files_private_bucket check (bucket_id = 'source-private'),
    constraint source_files_path_not_blank check (btrim(object_path) <> ''),
    constraint source_files_object_unique unique (bucket_id, object_path)
);

create table public.elements (
    element_id text primary key,
    domain_id text not null references public.domains(domain_id) on delete restrict,
    element_number integer not null check (element_number > 0),
    title text not null,
    topic_name text not null default '',
    subtopic_name text not null default '',
    mode text not null default 'CONCEPT',
    core_relation text not null default '',
    scope_notes text not null default '',
    source_label text not null default '',
    source_locator text not null default '',
    spec_section_locator text not null default '',
    display_order integer not null,
    is_active boolean not null default true,
    created_at timestamptz not null default clock_timestamp(),
    created_by uuid references auth.users(id) on delete set null,
    updated_at timestamptz not null default clock_timestamp(),
    updated_by uuid references auth.users(id) on delete set null,
    constraint elements_id_format check (element_id ~ '^[A-Z][A-Z0-9_]{1,15}-[0-9]{2,3}$'),
    constraint elements_title_not_blank check (btrim(title) <> ''),
    constraint elements_mode_not_blank check (btrim(mode) <> ''),
    constraint elements_domain_number_unique unique (domain_id, element_number),
    constraint elements_display_order_unique unique (display_order)
);

create table public.concepts (
    concept_id text primary key,
    element_id text not null unique references public.elements(element_id) on delete restrict,
    title text not null,
    definition_markdown text not null,
    intuition_markdown text not null,
    learning_notes_markdown text not null,
    checklist_markdown text not null,
    glossary_terms jsonb not null default '[]'::jsonb,
    created_at timestamptz not null default clock_timestamp(),
    created_by uuid references auth.users(id) on delete set null,
    updated_at timestamptz not null default clock_timestamp(),
    updated_by uuid references auth.users(id) on delete set null,
    constraint concepts_id_not_blank check (btrim(concept_id) <> ''),
    constraint concepts_title_not_blank check (btrim(title) <> ''),
    constraint concepts_definition_not_blank check (btrim(definition_markdown) <> ''),
    constraint concepts_intuition_not_blank check (btrim(intuition_markdown) <> ''),
    constraint concepts_learning_notes_not_blank check (btrim(learning_notes_markdown) <> ''),
    constraint concepts_checklist_not_blank check (btrim(checklist_markdown) <> ''),
    constraint concepts_glossary_array check (jsonb_typeof(glossary_terms) = 'array')
);

create table public.formulas (
    formula_id text primary key,
    element_id text not null references public.elements(element_id) on delete restrict,
    formula_key text not null default 'primary',
    title text not null,
    expression_markdown text not null,
    assumptions_markdown text not null,
    notes_markdown text not null,
    variables jsonb not null default '[]'::jsonb,
    display_order integer not null default 0,
    is_primary boolean not null default false,
    created_at timestamptz not null default clock_timestamp(),
    created_by uuid references auth.users(id) on delete set null,
    updated_at timestamptz not null default clock_timestamp(),
    updated_by uuid references auth.users(id) on delete set null,
    constraint formulas_id_not_blank check (btrim(formula_id) <> ''),
    constraint formulas_key_not_blank check (btrim(formula_key) <> ''),
    constraint formulas_title_not_blank check (btrim(title) <> ''),
    constraint formulas_expression_not_blank check (btrim(expression_markdown) <> ''),
    constraint formulas_variables_array check (jsonb_typeof(variables) = 'array'),
    constraint formulas_element_key_unique unique (element_id, formula_key)
);

create unique index formulas_one_primary_per_element_idx
    on public.formulas(element_id)
    where is_primary;

create table public.distractors (
    distractor_id uuid primary key default gen_random_uuid(),
    element_id text not null references public.elements(element_id) on delete restrict,
    distractor_key text not null,
    text text not null,
    explanation text not null default '',
    misconception_type text not null default '',
    difficulty smallint not null default 2 check (difficulty between 1 and 5),
    display_order integer not null default 0,
    is_enabled boolean not null default true,
    created_at timestamptz not null default clock_timestamp(),
    created_by uuid references auth.users(id) on delete set null,
    updated_at timestamptz not null default clock_timestamp(),
    updated_by uuid references auth.users(id) on delete set null,
    constraint distractors_key_not_blank check (btrim(distractor_key) <> ''),
    constraint distractors_text_not_blank check (btrim(text) <> ''),
    constraint distractors_element_key_unique unique (element_id, distractor_key)
);

comment on table public.distractors is
    'Curated concept-answer distractor list only. Random problem-template authoring is intentionally out of scope.';

create table public.element_sources (
    element_id text not null references public.elements(element_id) on delete restrict,
    source_id text not null references public.sources(source_id) on delete restrict,
    ordinal integer not null check (ordinal >= 0),
    created_at timestamptz not null default clock_timestamp(),
    created_by uuid references auth.users(id) on delete set null,
    updated_at timestamptz not null default clock_timestamp(),
    updated_by uuid references auth.users(id) on delete set null,
    primary key (element_id, source_id),
    constraint element_sources_element_ordinal_unique unique (element_id, ordinal)
);

create table public.content_evidence (
    evidence_id uuid primary key default gen_random_uuid(),
    entity_type public.content_entity_type not null,
    entity_key text not null,
    source_version_id uuid not null references public.source_versions(source_version_id) on delete restrict,
    locator jsonb not null default '{}'::jsonb,
    quote_markdown text not null default '',
    ordinal integer not null default 0 check (ordinal >= 0),
    created_at timestamptz not null default clock_timestamp(),
    created_by uuid references auth.users(id) on delete set null,
    updated_at timestamptz not null default clock_timestamp(),
    updated_by uuid references auth.users(id) on delete set null,
    constraint content_evidence_entity_key_not_blank check (btrim(entity_key) <> ''),
    constraint content_evidence_locator_object check (jsonb_typeof(locator) = 'object'),
    constraint content_evidence_entity_ordinal_unique unique (entity_type, entity_key, ordinal)
);

create index source_versions_source_created_idx
    on public.source_versions(source_id, created_at desc);
create index source_files_version_idx
    on public.source_files(source_version_id, file_role);
create index elements_domain_order_idx
    on public.elements(domain_id, display_order);
create index distractors_element_order_idx
    on public.distractors(element_id, is_enabled, display_order);
create index element_sources_source_idx
    on public.element_sources(source_id, element_id);
create index content_evidence_source_version_idx
    on public.content_evidence(source_version_id);

create or replace function public.assert_content_entity_exists()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
declare
    entity_exists boolean;
begin
    case new.entity_type
        when 'domain' then
            select exists(select 1 from public.domains where domain_id = new.entity_key) into entity_exists;
        when 'element' then
            select exists(select 1 from public.elements where element_id = new.entity_key) into entity_exists;
        when 'concept' then
            select exists(select 1 from public.concepts where concept_id = new.entity_key) into entity_exists;
        when 'formula' then
            select exists(select 1 from public.formulas where formula_id = new.entity_key) into entity_exists;
        when 'distractor' then
            select exists(
                select 1 from public.distractors where distractor_id::text = new.entity_key
            ) into entity_exists;
    end case;

    if not coalesce(entity_exists, false) then
        raise exception using
            errcode = '23503',
            message = format('unknown %s entity: %s', new.entity_type, new.entity_key);
    end if;
    return new;
end;
$$;

create or replace function public.protect_terminal_source_version()
returns trigger
language plpgsql
set search_path = ''
as $$
declare
    old_payload jsonb;
    new_payload jsonb;
begin
    if old.parse_status not in ('ready', 'archived') then
        return new;
    end if;

    old_payload := to_jsonb(old) - array['parse_status', 'updated_at', 'updated_by'];
    new_payload := to_jsonb(new) - array['parse_status', 'updated_at', 'updated_by'];

    if old_payload is distinct from new_payload
       or not (old.parse_status = 'ready' and new.parse_status = 'archived') then
        raise exception using
            errcode = '55000',
            message = 'ready or archived source versions are immutable; create a new version';
    end if;
    return new;
end;
$$;

create trigger content_evidence_validate_entity
before insert or update on public.content_evidence
for each row execute function public.assert_content_entity_exists();

create trigger source_versions_protect_terminal
before update on public.source_versions
for each row execute function public.protect_terminal_source_version();

do $triggers$
declare
    table_name text;
begin
    foreach table_name in array array[
        'domains', 'sources', 'source_versions', 'source_files', 'elements',
        'concepts', 'formulas', 'distractors', 'element_sources', 'content_evidence'
    ] loop
        execute format(
            'create trigger %I before insert or update on public.%I '
            'for each row execute function public.set_audit_columns()',
            table_name || '_set_audit_columns',
            table_name
        );
    end loop;
end;
$triggers$;

create trigger domains_immutable_id
before update on public.domains
for each row execute function public.prevent_column_update('domain_id');
create trigger sources_immutable_id
before update on public.sources
for each row execute function public.prevent_column_update('source_id');
create trigger source_versions_immutable_id
before update on public.source_versions
for each row execute function public.prevent_column_update('source_version_id', 'source_id', 'version_number');
create trigger source_files_immutable_id
before update on public.source_files
for each row execute function public.prevent_column_update('source_file_id', 'source_version_id', 'bucket_id', 'object_path');
create trigger elements_immutable_id
before update on public.elements
for each row execute function public.prevent_column_update('element_id');
create trigger concepts_immutable_id
before update on public.concepts
for each row execute function public.prevent_column_update('concept_id', 'element_id');
create trigger formulas_immutable_id
before update on public.formulas
for each row execute function public.prevent_column_update('formula_id', 'element_id', 'formula_key');
create trigger distractors_immutable_id
before update on public.distractors
for each row execute function public.prevent_column_update('distractor_id', 'element_id', 'distractor_key');
create trigger element_sources_immutable_identity
before update on public.element_sources
for each row execute function public.prevent_column_update('element_id', 'source_id');
create trigger content_evidence_immutable_id
before update on public.content_evidence
for each row execute function public.prevent_column_update('evidence_id');

revoke all on function public.assert_content_entity_exists() from public;
revoke all on function public.protect_terminal_source_version() from public;

commit;
