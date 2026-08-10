begin;

create or replace function public.enforce_validation_run()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
    if tg_op = 'INSERT' and new.status <> 'queued' then
        raise exception using errcode = '23514', message = 'a validation run must start queued';
    end if;
    if tg_op = 'UPDATE' and (
        new.validation_run_id <> old.validation_run_id
        or new.target_type <> old.target_type
        or new.revision_id is distinct from old.revision_id
        or new.release_id is distinct from old.release_id
        or new.validator_name <> old.validator_name
        or new.validator_version <> old.validator_version
    ) then
        raise exception using errcode = '55000', message = 'validation target and validator are immutable';
    end if;
    if tg_op = 'UPDATE' and old.status in ('passed', 'failed', 'cancelled') then
        raise exception using errcode = '55000', message = 'a terminal validation run is immutable';
    end if;
    if tg_op = 'UPDATE' and old.status <> new.status and not (
        (old.status = 'queued' and new.status in ('running', 'failed', 'cancelled'))
        or (old.status = 'running' and new.status in ('passed', 'failed', 'cancelled'))
    ) then
        raise exception using
            errcode = '23514',
            message = format('invalid validation transition: %s -> %s', old.status, new.status);
    end if;

    if new.status = 'running' and new.started_at is null then
        new.started_at := clock_timestamp();
    end if;
    if new.status in ('passed', 'failed', 'cancelled') and new.completed_at is null then
        new.completed_at := clock_timestamp();
    end if;
    if new.status = 'passed' and (
        new.checks_total < 1
        or new.checks_failed <> 0
        or new.checks_passed <> new.checks_total
        or exists (
            select 1
            from public.validation_issues as issue
            where issue.validation_run_id = new.validation_run_id
              and issue.severity = 'error'
        )
    ) then
        raise exception using
            errcode = '23514',
            message = 'validation can pass only after all checks pass with no error issues';
    end if;
    return new;
end;
$$;

create or replace function public.sync_validation_revision_state()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
declare
    current_state public.revision_state;
begin
    if new.target_type <> 'revision' then
        return new;
    end if;
    current_state := public.current_revision_state(new.revision_id);
    if new.status in ('queued', 'running') and current_state in ('draft', 'validation_failed') then
        insert into public.revision_state_events (revision_id, state, note, created_by)
        values (new.revision_id, 'validating', 'validation started', auth.uid());
    elsif new.status = 'passed' and current_state = 'validating' then
        insert into public.revision_state_events (revision_id, state, note, created_by)
        values (new.revision_id, 'reviewed', 'automated validation passed', auth.uid());
    elsif new.status = 'failed' and current_state = 'validating' then
        insert into public.revision_state_events (revision_id, state, note, created_by)
        values (new.revision_id, 'validation_failed', 'validation failed', auth.uid());
    end if;
    return new;
end;
$$;

create or replace function public.enforce_validation_issue_insert()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
    if not exists (
        select 1 from public.validation_runs as run
        where run.validation_run_id = new.validation_run_id and run.status = 'running'
    ) then
        raise exception using errcode = '55000', message = 'issues can be added only while validation is running';
    end if;
    new.created_by := coalesce(new.created_by, auth.uid());
    return new;
end;
$$;

create trigger validation_runs_append_only_after_terminal
before delete on public.validation_runs
for each row execute function public.prevent_row_mutation();
create trigger validation_issues_require_running
before insert on public.validation_issues
for each row execute function public.enforce_validation_issue_insert();

create or replace function public.enforce_job_change()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
    if tg_op = 'INSERT' and new.status <> 'queued' then
        raise exception using errcode = '23514', message = 'a job must start queued';
    end if;
    if tg_op = 'UPDATE' and (
        new.job_id <> old.job_id
        or new.job_kind <> old.job_kind
        or new.source_version_id is distinct from old.source_version_id
        or new.revision_id is distinct from old.revision_id
        or new.release_id is distinct from old.release_id
    ) then
        raise exception using errcode = '55000', message = 'job identity and targets are immutable';
    end if;
    if tg_op = 'UPDATE' and old.status in ('succeeded', 'cancelled') then
        raise exception using errcode = '55000', message = 'a terminal job is immutable';
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

create trigger ingestion_jobs_no_delete
before delete on public.ingestion_jobs
for each row execute function public.prevent_row_mutation();

create or replace function public.register_url_source(
    p_source_id text,
    p_label text,
    p_url text,
    p_source_type text default 'web'
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
    version_id uuid;
    job_id_value uuid;
begin
    if not public.has_admin_role(array['owner', 'editor']::public.admin_role[]) then
        raise exception using errcode = '42501', message = 'editor role required';
    end if;
    if not public.is_safe_public_source_url(p_url) then
        raise exception using errcode = '22023', message = 'unsafe source URL';
    end if;
    insert into public.sources (source_id, kind, label, locator, source_type, created_by)
    values (p_source_id, 'url', p_label, p_url, coalesce(p_source_type, 'web'), auth.uid());
    insert into public.source_versions (
        source_id, version_number, fetch_url, parse_status, created_by
    ) values (
        p_source_id, 1, p_url, 'pending', auth.uid()
    ) returning source_version_id into version_id;
    insert into public.ingestion_jobs (
        job_kind, source_version_id, input, created_by
    ) values (
        'url_fetch', version_id, jsonb_build_object('url', p_url), auth.uid()
    ) returning job_id into job_id_value;
    return jsonb_build_object('sourceVersionId', version_id, 'jobId', job_id_value);
end;
$$;

create or replace function public.register_file_source(
    p_source_id text,
    p_source_version_id uuid,
    p_label text,
    p_object_path text,
    p_original_filename text,
    p_mime_type text,
    p_byte_size bigint,
    p_sha256 text
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
    job_id_value uuid;
begin
    if not public.has_admin_role(array['owner', 'editor']::public.admin_role[]) then
        raise exception using errcode = '42501', message = 'editor role required';
    end if;
    if auth.uid() is null or split_part(p_object_path, '/', 1) <> auth.uid()::text then
        raise exception using errcode = '42501', message = 'storage object must belong to the current admin';
    end if;
    if p_byte_size < 1 or p_byte_size > 104857600
       or p_sha256 !~ '^[0-9a-f]{64}$'
       or nullif(btrim(p_original_filename), '') is null then
        raise exception using errcode = '22023', message = 'invalid source file metadata';
    end if;
    if not exists (
        select 1
        from storage.objects as object
        where object.bucket_id = 'source-private'
          and object.name = p_object_path
    ) then
        raise exception using errcode = 'P0002', message = 'uploaded storage object not found';
    end if;
    insert into public.sources (
        source_id, kind, label, locator, source_type, created_by
    ) values (
        p_source_id, 'file', p_label, p_object_path, coalesce(p_mime_type, 'application/octet-stream'), auth.uid()
    );
    insert into public.source_versions (
        source_version_id, source_id, version_number, original_filename,
        mime_type, byte_size, sha256, parse_status, created_by
    ) values (
        p_source_version_id, p_source_id, 1, p_original_filename,
        p_mime_type, p_byte_size, p_sha256, 'pending', auth.uid()
    );
    insert into public.source_files (
        source_version_id, file_role, object_path, original_filename,
        mime_type, byte_size, sha256, created_by
    ) values (
        p_source_version_id, 'original', p_object_path, p_original_filename,
        p_mime_type, p_byte_size, p_sha256, auth.uid()
    );
    insert into public.ingestion_jobs (
        job_kind, source_version_id, input, created_by
    ) values (
        'file_extract',
        p_source_version_id,
        jsonb_build_object('objectPath', p_object_path, 'originalFilename', p_original_filename),
        auth.uid()
    ) returning job_id into job_id_value;
    return jsonb_build_object('sourceVersionId', p_source_version_id, 'jobId', job_id_value);
end;
$$;

create or replace function public.skip_noop_authoring_update()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
    if to_jsonb(new) is not distinct from to_jsonb(old) then
        return null;
    end if;
    return new;
end;
$$;

create trigger domains_avoid_noop before update on public.domains
for each row execute function public.skip_noop_authoring_update();
create trigger elements_avoid_noop before update on public.elements
for each row execute function public.skip_noop_authoring_update();
create trigger concepts_avoid_noop before update on public.concepts
for each row execute function public.skip_noop_authoring_update();
create trigger formulas_avoid_noop before update on public.formulas
for each row execute function public.skip_noop_authoring_update();
create trigger distractors_avoid_noop before update on public.distractors
for each row execute function public.skip_noop_authoring_update();

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
    perform pg_advisory_xact_lock(hashtextextended('release-build:' || target_release_id::text, 0));
    select status into release_state
    from public.content_releases
    where release_id = target_release_id
    for update;
    if release_state not in ('draft', 'building') then
        raise exception using errcode = '55000', message = 'release contents and artifacts are sealed';
    end if;
    if tg_op = 'DELETE' then return old; end if;
    return new;
end;
$$;

create or replace function public.authorize_release_status_change()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
    if new.status is distinct from old.status
       and coalesce(current_setting('app.release_transition_authorized', true), '') <> '1' then
        raise exception using errcode = '42501', message = 'use a release transition RPC';
    end if;
    return new;
end;
$$;

create trigger content_releases_status_rpc_only
before update of status on public.content_releases
for each row execute function public.authorize_release_status_change();

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
    if p_status = 'published' then
        raise exception using errcode = '23514', message = 'publish with activate_release';
    end if;
    perform pg_advisory_xact_lock(hashtextextended('release-build:' || p_release_id::text, 0));
    perform set_config('app.release_note', coalesce(p_note, ''), true);
    perform set_config('app.release_transition_authorized', '1', true);
    update public.content_releases set status = p_status
    where release_id = p_release_id returning * into result;
    if not found then
        raise exception using errcode = 'P0002', message = 'release not found';
    end if;
    if p_status = 'withdrawn' then
        delete from public.release_channels where release_id = p_release_id;
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
    perform pg_advisory_xact_lock(hashtextextended('release-build:' || p_release_id::text, 0));
    select status into release_state from public.content_releases
    where release_id = p_release_id for update;
    if not found then raise exception using errcode = 'P0002', message = 'release not found'; end if;
    if release_state = 'ready' then
        perform set_config('app.release_transition_authorized', '1', true);
        update public.content_releases set status = 'published' where release_id = p_release_id;
    elsif release_state <> 'published' then
        raise exception using errcode = '23514', message = 'only ready or published releases can be activated';
    end if;
    insert into public.release_channels (channel, release_id, activated_at, activated_by)
    values (p_channel, p_release_id, clock_timestamp(), auth.uid())
    on conflict (channel) do update set
        release_id = excluded.release_id,
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

alter table public.content_releases
    add column create_request_key uuid;

create unique index content_releases_create_request_key_unique
    on public.content_releases(create_request_key);

create trigger content_releases_create_request_key_immutable
before update on public.content_releases
for each row execute function public.prevent_column_update('create_request_key');

create or replace function public.create_release_from_approved(
    p_request_key uuid,
    p_version_name text default null,
    p_release_notes text default '',
    p_minimum_app_version integer default 1
)
returns public.content_releases
language plpgsql
security definer
set search_path = ''
as $$
declare
    next_version integer;
    result public.content_releases%rowtype;
    item_count integer;
begin
    if not public.has_admin_role(array['owner', 'releaser']::public.admin_role[]) then
        raise exception using errcode = '42501', message = 'releaser role required';
    end if;
    if p_minimum_app_version < 1 then
        raise exception using errcode = '22023', message = 'minimum app version must be positive';
    end if;
    if p_request_key is null then
        raise exception using errcode = '22023', message = 'release request key is required';
    end if;
    perform pg_advisory_xact_lock(hashtextextended('release-request:' || p_request_key::text, 0));
    select * into result
    from public.content_releases
    where create_request_key = p_request_key;
    if found then
        if result.created_by is distinct from auth.uid() then
            raise exception using errcode = '42501', message = 'release request key belongs to another actor';
        end if;
        return result;
    end if;
    perform pg_advisory_xact_lock(hashtextextended('findone-content-version', 0));
    select coalesce(max(content_version), 5) + 1 into next_version from public.content_releases;
    insert into public.content_releases (
        content_version, version_name, schema_version, minimum_app_version,
        status, release_notes, create_request_key, created_by
    ) values (
        next_version,
        coalesce(nullif(btrim(p_version_name), ''), 'content-v' || next_version::text),
        1,
        p_minimum_app_version,
        'draft',
        coalesce(p_release_notes, ''), p_request_key,
        auth.uid()
    ) returning * into result;

    insert into public.release_items (
        release_id, revision_id, entity_type, entity_key,
        revision_number, content_hash, created_by
    )
    select
        result.release_id, revision.revision_id, revision.entity_type, revision.entity_key,
        revision.revision_number, revision.content_hash, auth.uid()
    from public.content_revisions as revision
    where public.current_revision_state(revision.revision_id) = 'approved'
      and not exists (
          select 1 from public.content_revisions as newer
          where newer.entity_type = revision.entity_type
            and newer.entity_key = revision.entity_key
            and newer.revision_number > revision.revision_number
      );
    get diagnostics item_count = row_count;
    if item_count < 1 then
        raise exception using errcode = '55000', message = 'no latest approved revisions are available';
    end if;

    perform set_config('app.release_transition_authorized', '1', true);
    update public.content_releases set status = 'building'
    where release_id = result.release_id returning * into result;
    insert into public.ingestion_jobs (job_kind, release_id, input, created_by)
    values (
        'release_build', result.release_id,
        jsonb_build_object('releaseId', result.release_id, 'contentVersion', next_version),
        auth.uid()
    );
    return result;
end;
$$;

create trigger release_items_immutable_projection
before update on public.release_items
for each row execute function public.prevent_column_update(
    'entity_type', 'entity_key', 'revision_number', 'content_hash'
);

drop view public.admin_content_grid;
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
    greatest(element.updated_at, concept.updated_at, formula.updated_at) as updated_at,
    latest_revision.revision_id as latest_revision_id,
    case
        when latest_revision.change_reason like 'initial SQLite content import %' then 'published'
        else coalesce(latest_revision.state::text, 'published')
    end as revision_status,
    coalesce(latest_revision.issue_count, 0) as issue_count,
    latest_revision.created_by as updated_by
from public.elements as element
join public.domains as domain on domain.domain_id = element.domain_id
left join public.concepts as concept on concept.element_id = element.element_id
left join public.formulas as formula
    on formula.element_id = element.element_id and formula.is_primary
left join lateral (
    select
        revision.revision_id,
        revision.change_reason,
        revision.created_by,
        status.state,
        (
            select count(*)::integer
            from public.validation_runs as run
            join public.validation_issues as issue
              on issue.validation_run_id = run.validation_run_id
            where run.revision_id = revision.revision_id
              and issue.severity in ('warning', 'error')
        ) as issue_count
    from public.content_revisions as revision
    left join public.content_revision_status as status on status.revision_id = revision.revision_id
    where (revision.entity_type = 'element' and revision.entity_key = element.element_id)
       or (revision.entity_type = 'concept' and revision.entity_key = concept.concept_id)
       or (revision.entity_type = 'formula' and revision.entity_key = formula.formula_id)
    order by revision.created_at desc, revision.revision_id desc
    limit 1
) as latest_revision on true
left join lateral (
    select
        count(*) filter (where distractor.is_enabled)::integer as enabled_count,
        count(*)::integer as total_count
    from public.distractors as distractor
    where distractor.element_id = element.element_id
) as distractor_counts on true;

create or replace view public.source_catalog_overview
with (security_invoker = true)
as
select
    source.*,
    coalesce(version_counts.version_count, 0) as version_count,
    version_counts.latest_version_at,
    coalesce(version_counts.latest_parse_status, 'ready'::public.source_parse_status) as latest_parse_status,
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

drop policy validation_runs_admin_write on public.validation_runs;
drop policy validation_issues_admin_insert on public.validation_issues;
drop policy ingestion_jobs_admin_insert on public.ingestion_jobs;
drop policy ingestion_jobs_admin_update on public.ingestion_jobs;
drop policy job_events_admin_insert on public.job_events;

revoke insert, update, delete on public.validation_runs from authenticated;
revoke insert on public.validation_issues from authenticated;
revoke insert, update on public.ingestion_jobs from authenticated;
revoke insert on public.job_events from authenticated;
revoke insert on public.review_decisions from authenticated;
revoke insert, update, delete on
    public.content_releases, public.release_items, public.release_artifacts
from authenticated;
revoke delete on public.domains, public.elements, public.concepts, public.formulas from authenticated;
revoke insert on public.sources, public.source_versions, public.source_files from authenticated;

grant select, insert, update on public.validation_runs to service_role;
grant select, insert on public.validation_issues to service_role;
grant select, insert, update on public.ingestion_jobs to service_role;
grant select, insert on public.job_events to service_role;
grant select, insert, update, delete on
    public.content_releases, public.release_items, public.release_artifacts
to service_role;

revoke all on function public.enforce_validation_issue_insert() from public;
revoke all on function public.register_url_source(text, text, text, text) from public;
revoke all on function public.register_file_source(text, uuid, text, text, text, text, bigint, text) from public;
revoke all on function public.skip_noop_authoring_update() from public;
revoke all on function public.authorize_release_status_change() from public;
revoke all on function public.create_release_from_approved(uuid, text, text, integer) from public;
grant execute on function public.register_url_source(text, text, text, text) to authenticated, service_role;
grant execute on function public.register_file_source(text, uuid, text, text, text, text, bigint, text) to authenticated;
grant execute on function public.create_release_from_approved(uuid, text, text, integer) to authenticated, service_role;

grant select on public.admin_content_grid, public.source_catalog_overview to authenticated;

commit;
