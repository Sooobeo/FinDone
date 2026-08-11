begin;

create table public.audit_events (
    audit_event_id bigint generated always as identity primary key,
    table_name text not null,
    record_key text not null,
    operation public.revision_operation not null,
    old_data jsonb,
    new_data jsonb,
    transaction_id bigint not null default txid_current(),
    occurred_at timestamptz not null default clock_timestamp(),
    actor_id uuid references auth.users(id) on delete set null,
    constraint audit_events_table_not_blank check (btrim(table_name) <> ''),
    constraint audit_events_key_not_blank check (btrim(record_key) <> ''),
    constraint audit_events_old_object check (old_data is null or jsonb_typeof(old_data) = 'object'),
    constraint audit_events_new_object check (new_data is null or jsonb_typeof(new_data) = 'object')
);

create index audit_events_record_idx
    on public.audit_events(table_name, record_key, audit_event_id desc);
create index audit_events_actor_idx
    on public.audit_events(actor_id, audit_event_id desc)
    where actor_id is not null;

create or replace function public.compact_audit_payload(p_table_name text, p_value jsonb)
returns jsonb
language plpgsql
immutable
set search_path = ''
as $$
begin
    if p_value is null then
        return null;
    end if;

    if p_table_name = 'source_versions' then
        return (p_value - array['extracted_text', 'extraction_metadata'])
            || jsonb_build_object(
                '_large_fields',
                jsonb_build_object(
                    'extracted_text_bytes', octet_length(coalesce(p_value ->> 'extracted_text', '')),
                    'extraction_metadata_sha256', encode(
                        extensions.digest(
                            convert_to(coalesce((p_value -> 'extraction_metadata')::text, ''), 'UTF8'),
                            'sha256'
                        ),
                        'hex'
                    )
                )
            );
    elsif p_table_name = 'ingestion_jobs' then
        return (p_value - array['input', 'output'])
            || jsonb_build_object(
                '_large_fields',
                jsonb_build_object(
                    'input_sha256', encode(
                        extensions.digest(convert_to(coalesce((p_value -> 'input')::text, ''), 'UTF8'), 'sha256'),
                        'hex'
                    ),
                    'output_sha256', encode(
                        extensions.digest(convert_to(coalesce((p_value -> 'output')::text, ''), 'UTF8'), 'sha256'),
                        'hex'
                    )
                )
            );
    elsif p_table_name = 'content_releases' then
        return (p_value - 'manifest')
            || jsonb_build_object(
                '_large_fields',
                jsonb_build_object(
                    'manifest_sha256', coalesce(
                        p_value ->> 'manifest_sha256',
                        encode(
                            extensions.digest(convert_to(coalesce((p_value -> 'manifest')::text, ''), 'UTF8'), 'sha256'),
                            'hex'
                        )
                    )
                )
            );
    end if;

    return p_value;
end;
$$;

create or replace function public.record_audit_event()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
declare
    old_value jsonb := case when tg_op = 'INSERT' then null else to_jsonb(old) end;
    new_value jsonb := case when tg_op = 'DELETE' then null else to_jsonb(new) end;
    key_source jsonb := coalesce(new_value, old_value);
    key_part text;
    record_key_value text := '';
    operation_value public.revision_operation := lower(tg_op)::public.revision_operation;
begin
    old_value := public.compact_audit_payload(tg_table_name, old_value);
    new_value := public.compact_audit_payload(tg_table_name, new_value);
    key_source := coalesce(new_value, old_value);

    foreach key_part in array tg_argv loop
        record_key_value := concat_ws(
            '|',
            nullif(record_key_value, ''),
            key_part || '=' || coalesce(key_source ->> key_part, '<null>')
        );
    end loop;

    insert into public.audit_events (
        table_name,
        record_key,
        operation,
        old_data,
        new_data,
        actor_id
    ) values (
        tg_table_schema || '.' || tg_table_name,
        record_key_value,
        operation_value,
        old_value,
        new_value,
        auth.uid()
    );

    if tg_op = 'DELETE' then
        return old;
    end if;
    return new;
end;
$$;

create trigger audit_events_append_only
before update or delete on public.audit_events
for each row execute function public.prevent_row_mutation();

do $audit_triggers$
declare
    target record;
begin
    for target in
        select *
        from (values
            ('admin_users', array['user_id']),
            ('domains', array['domain_id']),
            ('sources', array['source_id']),
            ('source_versions', array['source_version_id']),
            ('source_files', array['source_file_id']),
            ('elements', array['element_id']),
            ('concepts', array['concept_id']),
            ('formulas', array['formula_id']),
            ('distractors', array['distractor_id']),
            ('element_sources', array['element_id', 'source_id']),
            ('content_evidence', array['evidence_id']),
            ('validation_runs', array['validation_run_id']),
            ('content_releases', array['release_id']),
            ('release_items', array['release_item_id']),
            ('release_artifacts', array['release_artifact_id']),
            ('release_channels', array['channel']),
            ('ingestion_jobs', array['job_id'])
        ) as configured(table_name, key_columns)
    loop
        execute format(
            'create trigger %I after insert or update or delete on public.%I '
            'for each row execute function public.record_audit_event(%s)',
            target.table_name || '_record_audit',
            target.table_name,
            (
                select string_agg(quote_literal(column_name), ', ')
                from unnest(target.key_columns) as column_name
            )
        );
    end loop;
end;
$audit_triggers$;

do $enable_rls$
declare
    table_name text;
begin
    foreach table_name in array array[
        'admin_users', 'domains', 'sources', 'source_versions', 'source_files',
        'elements', 'concepts', 'formulas', 'distractors', 'element_sources',
        'content_evidence', 'content_revisions', 'revision_state_events',
        'validation_runs', 'validation_issues', 'review_decisions',
        'approval_snapshots', 'content_releases', 'release_items',
        'release_artifacts', 'release_events', 'release_channels',
        'ingestion_jobs', 'job_events', 'content_imports', 'audit_events'
    ] loop
        execute format('alter table public.%I enable row level security', table_name);
        execute format(
            'create policy %I on public.%I for select to authenticated '
            'using ((select public.is_admin()))',
            table_name || '_admin_select',
            table_name
        );
    end loop;
end;
$enable_rls$;

create policy admin_users_owner_insert
on public.admin_users for insert to authenticated
with check ((select public.has_admin_role(array['owner']::public.admin_role[])));
create policy admin_users_owner_update
on public.admin_users for update to authenticated
using ((select public.has_admin_role(array['owner']::public.admin_role[])))
with check ((select public.has_admin_role(array['owner']::public.admin_role[])));
create policy admin_users_owner_delete
on public.admin_users for delete to authenticated
using ((select public.has_admin_role(array['owner']::public.admin_role[])));

do $authoring_policies$
declare
    table_name text;
begin
    foreach table_name in array array[
        'domains', 'sources', 'source_versions', 'source_files', 'elements',
        'concepts', 'formulas', 'distractors', 'element_sources', 'content_evidence'
    ] loop
        execute format(
            'create policy %I on public.%I for all to authenticated '
            'using ((select public.has_admin_role(array[''owner'', ''editor'']::public.admin_role[]))) '
            'with check ((select public.has_admin_role(array[''owner'', ''editor'']::public.admin_role[])))',
            table_name || '_editor_write',
            table_name
        );
    end loop;
end;
$authoring_policies$;

create policy validation_runs_admin_write
on public.validation_runs for all to authenticated
using ((select public.has_admin_role(array['owner', 'editor', 'reviewer']::public.admin_role[])))
with check ((select public.has_admin_role(array['owner', 'editor', 'reviewer']::public.admin_role[])));
create policy validation_issues_admin_insert
on public.validation_issues for insert to authenticated
with check ((select public.has_admin_role(array['owner', 'editor', 'reviewer']::public.admin_role[])));
create policy review_decisions_reviewer_insert
on public.review_decisions for insert to authenticated
with check ((select public.has_admin_role(array['owner', 'reviewer']::public.admin_role[])));

do $release_policies$
declare
    table_name text;
begin
    foreach table_name in array array['content_releases', 'release_items', 'release_artifacts'] loop
        execute format(
            'create policy %I on public.%I for all to authenticated '
            'using ((select public.has_admin_role(array[''owner'', ''releaser'']::public.admin_role[]))) '
            'with check ((select public.has_admin_role(array[''owner'', ''releaser'']::public.admin_role[])))',
            table_name || '_releaser_write',
            table_name
        );
    end loop;
end;
$release_policies$;

create policy ingestion_jobs_admin_insert
on public.ingestion_jobs for insert to authenticated
with check ((select public.is_admin()));
create policy ingestion_jobs_admin_update
on public.ingestion_jobs for update to authenticated
using ((select public.is_admin()))
with check ((select public.is_admin()));
create policy job_events_admin_insert
on public.job_events for insert to authenticated
with check ((select public.is_admin()));

revoke all on all tables in schema public from anon, authenticated;
revoke all on all sequences in schema public from anon, authenticated;

grant select on table
    public.admin_users,
    public.domains,
    public.sources,
    public.source_versions,
    public.source_files,
    public.elements,
    public.concepts,
    public.formulas,
    public.distractors,
    public.element_sources,
    public.content_evidence,
    public.content_revisions,
    public.revision_state_events,
    public.validation_runs,
    public.validation_issues,
    public.review_decisions,
    public.approval_snapshots,
    public.content_releases,
    public.release_items,
    public.release_artifacts,
    public.release_events,
    public.release_channels,
    public.ingestion_jobs,
    public.job_events,
    public.content_imports,
    public.audit_events
to authenticated;

grant insert, update, delete on table public.admin_users to authenticated;
grant insert, update, delete on table
    public.domains,
    public.sources,
    public.source_versions,
    public.source_files,
    public.elements,
    public.concepts,
    public.formulas,
    public.distractors,
    public.element_sources,
    public.content_evidence
to authenticated;
grant insert, update, delete on table public.validation_runs to authenticated;
grant insert on table public.validation_issues, public.review_decisions to authenticated;
grant insert, update, delete on table
    public.content_releases,
    public.release_items,
    public.release_artifacts
to authenticated;
grant insert, update on table public.ingestion_jobs to authenticated;
grant insert on table public.job_events to authenticated;
grant usage, select on all sequences in schema public to authenticated;

revoke all on table
    public.admin_content_grid,
    public.content_revision_status,
    public.source_catalog_overview,
    public.release_overview
from anon, authenticated;
grant select on table
    public.admin_content_grid,
    public.content_revision_status,
    public.source_catalog_overview,
    public.release_overview
to authenticated;

grant execute on function public.import_content_snapshot(jsonb, boolean) to authenticated, service_role;
grant execute on function public.save_content_grid_row(text, jsonb, jsonb, jsonb, text) to authenticated, service_role;
grant execute on function public.start_revision_validation(uuid, text, text) to authenticated, service_role;
grant execute on function public.submit_review(uuid, public.review_decision_type, text) to authenticated, service_role;
grant execute on function public.set_release_status(uuid, public.release_status, text) to authenticated, service_role;
grant execute on function public.activate_release(uuid, text) to authenticated, service_role;

insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values
    (
        'source-private',
        'source-private',
        false,
        104857600,
        array[
            'application/pdf', 'application/json', 'application/x-ndjson',
            'application/vnd.sqlite3', 'application/x-sqlite3', 'application/msword',
            'application/vnd.ms-excel', 'application/vnd.ms-powerpoint',
            'application/vnd.openxmlformats-officedocument.presentationml.presentation',
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            'image/jpeg', 'image/png', 'image/webp', 'text/csv', 'text/html',
            'text/markdown', 'text/plain'
        ]::text[]
    ),
    (
        'exports-private',
        'exports-private',
        false,
        104857600,
        array[
            'application/json', 'application/octet-stream',
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            'application/x-sqlite3', 'text/csv', 'text/plain'
        ]::text[]
    ),
    (
        'release-bundles',
        'release-bundles',
        false,
        104857600,
        array['application/json', 'application/octet-stream', 'application/x-sqlite3', 'text/plain']::text[]
    )
on conflict (id) do update set
    public = false,
    file_size_limit = excluded.file_size_limit,
    allowed_mime_types = excluded.allowed_mime_types;

-- Supabase owns the Storage catalog tables and keeps their RLS enabled.  Hosted
-- projects do not grant a project role ownership of storage.buckets/objects,
-- so migrations must not ALTER those tables or install bucket-level policies.
-- Bucket metadata is provisioned above; object access is constrained below.

create policy findone_admin_object_read
on storage.objects for select to authenticated
using (
    bucket_id in ('source-private', 'exports-private', 'release-bundles')
    and (select public.is_admin())
);
create policy findone_admin_object_insert
on storage.objects for insert to authenticated
with check (
    (storage.foldername(name))[1] = auth.uid()::text
    and (
        (bucket_id = 'source-private' and (select public.has_admin_role(array['owner', 'editor']::public.admin_role[])))
        or (bucket_id = 'exports-private' and (select public.is_admin()))
        or (bucket_id = 'release-bundles' and (select public.has_admin_role(array['owner', 'releaser']::public.admin_role[])))
    )
);
create policy findone_admin_object_update
on storage.objects for update to authenticated
using (
    (storage.foldername(name))[1] = auth.uid()::text
    and bucket_id in ('source-private', 'exports-private', 'release-bundles')
    and (select public.is_admin())
)
with check (
    (storage.foldername(name))[1] = auth.uid()::text
    and (
        (bucket_id = 'source-private' and (select public.has_admin_role(array['owner', 'editor']::public.admin_role[])))
        or (bucket_id = 'exports-private' and (select public.is_admin()))
        or (bucket_id = 'release-bundles' and (select public.has_admin_role(array['owner', 'releaser']::public.admin_role[])))
    )
);
create policy findone_admin_object_delete
on storage.objects for delete to authenticated
using (
    (storage.foldername(name))[1] = auth.uid()::text
    and (
        (bucket_id = 'source-private' and (select public.has_admin_role(array['owner', 'editor']::public.admin_role[])))
        or (bucket_id = 'exports-private' and (select public.is_admin()))
        or (bucket_id = 'release-bundles' and (select public.has_admin_role(array['owner', 'releaser']::public.admin_role[])))
    )
);

revoke all on function public.record_audit_event() from public;
revoke all on function public.compact_audit_payload(text, jsonb) from public;

commit;
