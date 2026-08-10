begin;

create table public.content_imports (
    content_import_id uuid primary key default gen_random_uuid(),
    export_format text not null,
    database_sha256 text not null unique,
    source_sha256 text,
    schema_version integer not null check (schema_version > 0),
    content_version integer not null check (content_version > 0),
    row_counts jsonb not null,
    source_metadata jsonb not null,
    imported_at timestamptz not null default clock_timestamp(),
    imported_by uuid references auth.users(id) on delete set null,
    constraint content_imports_database_hash_format check (database_sha256 ~ '^[0-9a-f]{64}$'),
    constraint content_imports_source_hash_format check (
        source_sha256 is null or source_sha256 ~ '^[0-9a-f]{64}$'
    ),
    constraint content_imports_counts_object check (jsonb_typeof(row_counts) = 'object'),
    constraint content_imports_metadata_object check (jsonb_typeof(source_metadata) = 'object')
);

create trigger content_imports_append_only
before update or delete on public.content_imports
for each row execute function public.prevent_row_mutation();

create or replace function public.import_content_snapshot(
    p_snapshot jsonb,
    p_allow_overwrite boolean default false
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
    tables_value jsonb;
    content_value jsonb;
    row_value jsonb;
    database_hash text;
    existing_import_id uuid;
    domain_count integer;
    source_count integer;
    element_count integer;
    concept_count integer;
    formula_count integer;
    link_count integer;
begin
    if not public.has_admin_role(array['owner', 'editor']::public.admin_role[]) then
        raise exception using errcode = '42501', message = 'editor role required';
    end if;
    if p_allow_overwrite
       and not public.has_admin_role(array['owner']::public.admin_role[]) then
        raise exception using errcode = '42501', message = 'owner role required for overwrite import';
    end if;
    if p_snapshot ->> 'exportFormat' <> 'findone-admin-content-v1' then
        raise exception using errcode = '22023', message = 'unsupported content export format';
    end if;

    tables_value := p_snapshot -> 'tables';
    content_value := p_snapshot -> 'content';
    if jsonb_typeof(tables_value) <> 'object' or jsonb_typeof(content_value) <> 'object' then
        raise exception using errcode = '22023', message = 'snapshot tables and content must be objects';
    end if;
    if exists (
        select 1
        from unnest(array[
            'domains', 'sources', 'elements', 'concept_cards', 'formula_cards', 'element_sources'
        ]) as required_table(name)
        where jsonb_typeof(tables_value -> required_table.name) <> 'array'
    ) then
        raise exception using errcode = '22023', message = 'snapshot is missing a required table array';
    end if;

    database_hash := content_value ->> 'databaseSha256';
    if database_hash is null or database_hash !~ '^[0-9a-f]{64}$' then
        raise exception using errcode = '22023', message = 'snapshot databaseSha256 is invalid';
    end if;

    perform pg_advisory_xact_lock(hashtextextended('findone-content-import', 0));
    select content_import_id into existing_import_id
    from public.content_imports
    where database_sha256 = database_hash;
    if found then
        return jsonb_build_object(
            'status', 'already_imported',
            'contentImportId', existing_import_id,
            'databaseSha256', database_hash
        );
    end if;

    if not p_allow_overwrite and (
        exists(select 1 from public.elements)
        or exists(select 1 from public.concepts)
        or exists(select 1 from public.formulas)
    ) then
        raise exception using
            errcode = '55000',
            message = 'authoring content already exists; use a reviewed edit or explicit owner overwrite';
    end if;

    domain_count := jsonb_array_length(tables_value -> 'domains');
    source_count := jsonb_array_length(tables_value -> 'sources');
    element_count := jsonb_array_length(tables_value -> 'elements');
    concept_count := jsonb_array_length(tables_value -> 'concept_cards');
    formula_count := jsonb_array_length(tables_value -> 'formula_cards');
    link_count := jsonb_array_length(tables_value -> 'element_sources');

    if domain_count < 1 or element_count < 1 then
        raise exception using errcode = '22023', message = 'snapshot must contain domains and elements';
    end if;
    if concept_count <> element_count or formula_count <> element_count then
        raise exception using errcode = '22023', message = 'snapshot requires one concept and formula per element';
    end if;
    if exists (
        select 1
        from jsonb_array_elements(tables_value -> 'elements') as element(row_data)
        where not exists (
            select 1
            from jsonb_array_elements(tables_value -> 'concept_cards') as concept(row_data)
            where concept.row_data ->> 'element_id' = element.row_data ->> 'element_id'
        ) or not exists (
            select 1
            from jsonb_array_elements(tables_value -> 'formula_cards') as formula(row_data)
            where formula.row_data ->> 'element_id' = element.row_data ->> 'element_id'
        )
    ) then
        raise exception using errcode = '22023', message = 'concept/formula element IDs do not match elements';
    end if;

    perform set_config('app.change_reason', 'initial SQLite content import ' || database_hash, true);

    for row_value in select value from jsonb_array_elements(tables_value -> 'domains') loop
        insert into public.domains (
            domain_id, name, description, expected_element_count, display_order, color_token
        ) values (
            row_value ->> 'domain_id',
            row_value ->> 'name',
            coalesce(row_value ->> 'description', ''),
            (row_value ->> 'element_count')::integer,
            (row_value ->> 'display_order')::integer,
            coalesce(row_value ->> 'color_token', 'research.default')
        )
        on conflict (domain_id) do update set
            name = excluded.name,
            description = excluded.description,
            expected_element_count = excluded.expected_element_count,
            display_order = excluded.display_order,
            color_token = excluded.color_token
        where p_allow_overwrite;
    end loop;

    for row_value in select value from jsonb_array_elements(tables_value -> 'sources') loop
        insert into public.sources (
            source_id, kind, label, locator, source_type, notes
        ) values (
            row_value ->> 'source_id',
            case
                when coalesce(row_value ->> 'locator', '') ~* '^https?://'
                    then 'url'::public.source_kind
                else 'reference'::public.source_kind
            end,
            row_value ->> 'label',
            coalesce(row_value ->> 'locator', ''),
            coalesce(row_value ->> 'source_type', ''),
            coalesce(row_value ->> 'notes', '')
        )
        on conflict (source_id) do update set
            kind = excluded.kind,
            label = excluded.label,
            locator = excluded.locator,
            source_type = excluded.source_type,
            notes = excluded.notes
        where p_allow_overwrite;
    end loop;

    for row_value in select value from jsonb_array_elements(tables_value -> 'elements') loop
        insert into public.elements (
            element_id, domain_id, element_number, title, mode, core_relation,
            scope_notes, source_label, source_locator, spec_section_locator, display_order
        ) values (
            row_value ->> 'element_id',
            row_value ->> 'domain_id',
            (row_value ->> 'element_number')::integer,
            row_value ->> 'title',
            row_value ->> 'mode',
            coalesce(row_value ->> 'core_relation', ''),
            coalesce(row_value ->> 'scope_notes', ''),
            coalesce(row_value ->> 'source_label', ''),
            coalesce(row_value ->> 'source_locator', ''),
            coalesce(row_value ->> 'spec_section_locator', ''),
            (row_value ->> 'display_order')::integer
        )
        on conflict (element_id) do update set
            domain_id = excluded.domain_id,
            element_number = excluded.element_number,
            title = excluded.title,
            mode = excluded.mode,
            core_relation = excluded.core_relation,
            scope_notes = excluded.scope_notes,
            source_label = excluded.source_label,
            source_locator = excluded.source_locator,
            spec_section_locator = excluded.spec_section_locator,
            display_order = excluded.display_order
        where p_allow_overwrite;
    end loop;

    for row_value in select value from jsonb_array_elements(tables_value -> 'concept_cards') loop
        insert into public.concepts (
            concept_id, element_id, title, definition_markdown, intuition_markdown,
            learning_notes_markdown, checklist_markdown
        ) values (
            row_value ->> 'concept_id',
            row_value ->> 'element_id',
            row_value ->> 'title',
            row_value ->> 'definition',
            row_value ->> 'intuition',
            row_value ->> 'scope_notes',
            coalesce(
                (
                    select formula_row.value ->> 'notes'
                    from jsonb_array_elements(tables_value -> 'formula_cards') as formula_row(value)
                    where formula_row.value ->> 'element_id' = row_value ->> 'element_id'
                    limit 1
                ),
                row_value ->> 'scope_notes'
            )
        )
        on conflict (concept_id) do update set
            title = excluded.title,
            definition_markdown = excluded.definition_markdown,
            intuition_markdown = excluded.intuition_markdown,
            learning_notes_markdown = excluded.learning_notes_markdown,
            checklist_markdown = excluded.checklist_markdown
        where p_allow_overwrite;
    end loop;

    for row_value in select value from jsonb_array_elements(tables_value -> 'formula_cards') loop
        insert into public.formulas (
            formula_id, element_id, formula_key, title, expression_markdown,
            assumptions_markdown, notes_markdown, variables, is_primary
        ) values (
            row_value ->> 'formula_id',
            row_value ->> 'element_id',
            'primary',
            row_value ->> 'title',
            row_value ->> 'expression',
            row_value ->> 'assumptions',
            row_value ->> 'notes',
            '[]'::jsonb,
            true
        )
        on conflict (formula_id) do update set
            title = excluded.title,
            expression_markdown = excluded.expression_markdown,
            assumptions_markdown = excluded.assumptions_markdown,
            notes_markdown = excluded.notes_markdown,
            is_primary = true
        where p_allow_overwrite;
    end loop;

    for row_value in select value from jsonb_array_elements(tables_value -> 'element_sources') loop
        insert into public.element_sources (element_id, source_id, ordinal)
        values (
            row_value ->> 'element_id',
            row_value ->> 'source_id',
            (row_value ->> 'ordinal')::integer
        )
        on conflict (element_id, source_id) do update set ordinal = excluded.ordinal
        where p_allow_overwrite;
    end loop;

    insert into public.content_imports (
        export_format,
        database_sha256,
        source_sha256,
        schema_version,
        content_version,
        row_counts,
        source_metadata,
        imported_by
    ) values (
        p_snapshot ->> 'exportFormat',
        database_hash,
        nullif(content_value ->> 'sourceSha256', ''),
        (content_value ->> 'schemaVersion')::integer,
        (content_value ->> 'contentDbVersion')::integer,
        jsonb_build_object(
            'domains', domain_count,
            'sources', source_count,
            'elements', element_count,
            'concept_cards', concept_count,
            'formula_cards', formula_count,
            'element_sources', link_count
        ),
        content_value,
        auth.uid()
    ) returning content_import_id into existing_import_id;

    return jsonb_build_object(
        'status', 'imported',
        'contentImportId', existing_import_id,
        'databaseSha256', database_hash,
        'rowCounts', jsonb_build_object(
            'domains', domain_count,
            'sources', source_count,
            'elements', element_count,
            'conceptCards', concept_count,
            'formulaCards', formula_count,
            'elementSources', link_count
        )
    );
end;
$$;

create or replace function public.save_content_grid_row(
    p_element_id text,
    p_element_patch jsonb default '{}'::jsonb,
    p_concept_patch jsonb default '{}'::jsonb,
    p_formula_patch jsonb default '{}'::jsonb,
    p_change_reason text default null
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
    result jsonb;
begin
    if not public.has_admin_role(array['owner', 'editor']::public.admin_role[]) then
        raise exception using errcode = '42501', message = 'editor role required';
    end if;
    if jsonb_typeof(p_element_patch) <> 'object'
       or jsonb_typeof(p_concept_patch) <> 'object'
       or jsonb_typeof(p_formula_patch) <> 'object' then
        raise exception using errcode = '22023', message = 'content patches must be JSON objects';
    end if;

    perform set_config('app.change_reason', coalesce(p_change_reason, ''), true);

    if p_element_patch <> '{}'::jsonb then
        update public.elements
        set domain_id = coalesce(p_element_patch ->> 'domain_id', domain_id),
            element_number = coalesce((p_element_patch ->> 'element_number')::integer, element_number),
            title = coalesce(p_element_patch ->> 'title', title),
            topic_name = coalesce(p_element_patch ->> 'topic_name', topic_name),
            subtopic_name = coalesce(p_element_patch ->> 'subtopic_name', subtopic_name),
            mode = coalesce(p_element_patch ->> 'mode', mode),
            core_relation = coalesce(p_element_patch ->> 'core_relation', core_relation),
            scope_notes = coalesce(p_element_patch ->> 'scope_notes', scope_notes),
            source_label = coalesce(p_element_patch ->> 'source_label', source_label),
            source_locator = coalesce(p_element_patch ->> 'source_locator', source_locator),
            spec_section_locator = coalesce(p_element_patch ->> 'spec_section_locator', spec_section_locator),
            display_order = coalesce((p_element_patch ->> 'display_order')::integer, display_order),
            is_active = coalesce((p_element_patch ->> 'is_active')::boolean, is_active)
        where element_id = p_element_id;
        if not found then
            raise exception using errcode = 'P0002', message = 'element not found';
        end if;
    end if;

    if p_concept_patch <> '{}'::jsonb then
        update public.concepts
        set title = coalesce(p_concept_patch ->> 'title', title),
            definition_markdown = coalesce(p_concept_patch ->> 'definition_markdown', definition_markdown),
            intuition_markdown = coalesce(p_concept_patch ->> 'intuition_markdown', intuition_markdown),
            learning_notes_markdown = coalesce(p_concept_patch ->> 'learning_notes_markdown', learning_notes_markdown),
            checklist_markdown = coalesce(p_concept_patch ->> 'checklist_markdown', checklist_markdown),
            glossary_terms = case
                when p_concept_patch ? 'glossary_terms' then p_concept_patch -> 'glossary_terms'
                else glossary_terms
            end
        where element_id = p_element_id;
        if not found then
            raise exception using errcode = 'P0002', message = 'concept not found';
        end if;
    end if;

    if p_formula_patch <> '{}'::jsonb then
        update public.formulas
        set title = coalesce(p_formula_patch ->> 'title', title),
            expression_markdown = coalesce(p_formula_patch ->> 'expression_markdown', expression_markdown),
            assumptions_markdown = coalesce(p_formula_patch ->> 'assumptions_markdown', assumptions_markdown),
            notes_markdown = coalesce(p_formula_patch ->> 'notes_markdown', notes_markdown),
            variables = case
                when p_formula_patch ? 'variables' then p_formula_patch -> 'variables'
                else variables
            end
        where element_id = p_element_id and is_primary;
        if not found then
            raise exception using errcode = 'P0002', message = 'primary formula not found';
        end if;
    end if;

    select to_jsonb(grid) into result
    from (
        select
            element.*,
            concept.concept_id,
            concept.definition_markdown,
            concept.intuition_markdown,
            concept.learning_notes_markdown,
            concept.checklist_markdown,
            concept.glossary_terms,
            formula.formula_id,
            formula.expression_markdown,
            formula.assumptions_markdown,
            formula.notes_markdown,
            formula.variables
        from public.elements as element
        left join public.concepts as concept on concept.element_id = element.element_id
        left join public.formulas as formula
            on formula.element_id = element.element_id and formula.is_primary
        where element.element_id = p_element_id
    ) as grid;
    return result;
end;
$$;

create or replace function public.start_revision_validation(
    p_revision_id uuid,
    p_validator_name text default 'findone-content-validator',
    p_validator_version text default ''
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

create view public.content_revision_status
with (security_invoker = true)
as
select
    revision.revision_id,
    revision.entity_type,
    revision.entity_key,
    revision.revision_number,
    revision.operation,
    revision.content_hash,
    revision.change_reason,
    revision.created_at,
    revision.created_by,
    state.state,
    state.note as state_note,
    state.created_at as state_changed_at,
    state.created_by as state_changed_by
from public.content_revisions as revision
left join lateral (
    select event.state, event.note, event.created_at, event.created_by
    from public.revision_state_events as event
    where event.revision_id = revision.revision_id
    order by event.revision_state_event_id desc
    limit 1
) as state on true;

create view public.admin_content_grid
with (security_invoker = true)
as
select
    element.element_id,
    element.domain_id,
    domain.name as domain_name,
    domain.display_order as domain_display_order,
    element.element_number,
    element.title,
    element.topic_name,
    element.subtopic_name,
    element.mode,
    element.core_relation,
    element.scope_notes as element_scope_notes,
    element.source_label,
    element.source_locator,
    element.spec_section_locator,
    element.display_order,
    element.is_active,
    concept.concept_id,
    concept.title as concept_title,
    concept.definition_markdown,
    concept.intuition_markdown,
    concept.learning_notes_markdown,
    concept.checklist_markdown,
    concept.glossary_terms,
    formula.formula_id,
    formula.title as formula_title,
    formula.expression_markdown,
    formula.assumptions_markdown,
    formula.notes_markdown,
    formula.variables,
    coalesce(distractor_counts.enabled_count, 0) as enabled_distractor_count,
    coalesce(distractor_counts.total_count, 0) as distractor_count,
    greatest(element.updated_at, concept.updated_at, formula.updated_at) as updated_at
from public.elements as element
join public.domains as domain on domain.domain_id = element.domain_id
left join public.concepts as concept on concept.element_id = element.element_id
left join public.formulas as formula
    on formula.element_id = element.element_id and formula.is_primary
left join lateral (
    select
        count(*) filter (where distractor.is_enabled)::integer as enabled_count,
        count(*)::integer as total_count
    from public.distractors as distractor
    where distractor.element_id = element.element_id
) as distractor_counts on true;

create view public.source_catalog_overview
with (security_invoker = true)
as
select
    source.*,
    coalesce(version_counts.version_count, 0) as version_count,
    version_counts.latest_version_at,
    version_counts.latest_parse_status,
    coalesce(element_counts.element_count, 0) as linked_element_count
from public.sources as source
left join lateral (
    select
        count(*)::integer as version_count,
        max(version.created_at) as latest_version_at,
        (array_agg(version.parse_status order by version.version_number desc))[1] as latest_parse_status
    from public.source_versions as version
    where version.source_id = source.source_id
) as version_counts on true
left join lateral (
    select count(*)::integer as element_count
    from public.element_sources as link
    where link.source_id = source.source_id
) as element_counts on true;

create view public.release_overview
with (security_invoker = true)
as
select
    release.*,
    coalesce(item_count.value, 0) as item_count,
    coalesce(artifact_count.value, 0) as artifact_count,
    coalesce(channels.value, array[]::text[]) as active_channels
from public.content_releases as release
left join lateral (
    select count(*)::integer as value
    from public.release_items as item
    where item.release_id = release.release_id
) as item_count on true
left join lateral (
    select count(*)::integer as value
    from public.release_artifacts as artifact
    where artifact.release_id = release.release_id
) as artifact_count on true
left join lateral (
    select array_agg(channel.channel order by channel.channel) as value
    from public.release_channels as channel
    where channel.release_id = release.release_id
) as channels on true;

comment on view public.admin_content_grid is
    'Spreadsheet-shaped read model. Write changes with save_content_grid_row or the normalized tables.';

revoke all on function public.import_content_snapshot(jsonb, boolean) from public;
revoke all on function public.save_content_grid_row(text, jsonb, jsonb, jsonb, text) from public;
revoke all on function public.start_revision_validation(uuid, text, text) from public;

commit;
