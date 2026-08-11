begin;

create extension if not exists pgtap with schema extensions;
select plan(45);

select has_table('public', 'admin_users', 'admin allowlist exists');
select has_table('public', 'domains', 'domains exists');
select has_table('public', 'sources', 'sources exists');
select has_table('public', 'source_versions', 'source versions exist');
select has_table('public', 'source_files', 'source files exist');
select has_table('public', 'elements', 'elements exists');
select has_table('public', 'concepts', 'concepts exists');
select has_table('public', 'formulas', 'formulas exists');
select has_table('public', 'distractors', 'distractors exist');
select has_table('public', 'content_revisions', 'content revisions exist');
select has_table('public', 'revision_state_events', 'revision state events exist');
select has_table('public', 'validation_runs', 'validation runs exist');
select has_table('public', 'validation_issues', 'validation issues exist');
select has_table('public', 'review_decisions', 'review decisions exist');
select has_table('public', 'content_releases', 'content releases exist');
select has_table('public', 'ingestion_jobs', 'ingestion jobs exist');
select has_table('public', 'audit_events', 'audit events exist');

select has_view('public', 'admin_content_grid', 'admin grid view exists');
select has_view('public', 'content_revision_status', 'revision status view exists');
select has_view('public', 'release_overview', 'release overview view exists');

select has_function('public', 'import_content_snapshot', 'snapshot import RPC exists');
select has_function('public', 'save_content_grid_row', 'grid save RPC exists');
select has_function('public', 'save_content_grid_rows', 'atomic bulk grid save RPC exists');
select has_function('public', 'is_safe_public_source_url', 'source URL safety function exists');
select has_function('public', 'release_validation_fingerprint', 'release fingerprint function exists');
select has_function('public', 'start_release_validation', 'release validation RPC exists');
select has_function('public', 'register_url_source', 'atomic URL registration RPC exists');
select has_function('public', 'register_file_source', 'atomic file registration RPC exists');
select has_function('public', 'create_release_from_approved', 'approved release creation RPC exists');
select is(
    public.is_safe_public_source_url('http://169.254.169.254/latest/meta-data'),
    false,
    'metadata IP URL is rejected'
);
select has_function('public', 'start_revision_validation', 'validation RPC exists');
select has_function('public', 'submit_review', 'review RPC exists');
select has_function('public', 'activate_release', 'release activation RPC exists');
select has_function('public', 'provision_viewer_membership', 'viewer provisioning trigger function exists');

select ok(
    not exists (
        select 1
        from pg_catalog.pg_class as relation
        join pg_catalog.pg_namespace as namespace on namespace.oid = relation.relnamespace
        where namespace.nspname = 'public'
          and relation.relkind in ('r', 'p')
          and not relation.relrowsecurity
    ),
    'every public table has RLS enabled'
);

select is(
    (select count(*) from storage.buckets where id in ('source-private', 'exports-private', 'release-bundles')),
    3::bigint,
    'all private storage buckets exist'
);
select is(
    (select count(*) from storage.buckets where id in ('source-private', 'exports-private', 'release-bundles') and public),
    0::bigint,
    'no FinDone storage bucket is public'
);

insert into public.content_revisions (
    revision_id, entity_type, entity_key, revision_number, operation, snapshot, content_hash
) values (
    '10000000-0000-0000-0000-000000000001',
    'element',
    'TEST-01',
    1,
    'insert',
    '{}'::jsonb,
    repeat('0', 64)
);
select throws_ok(
    $$update public.content_revisions set change_reason = 'tampered' where revision_id = '10000000-0000-0000-0000-000000000001'$$,
    '55000',
    'content_revisions is append-only',
    'content revisions cannot be mutated'
);

insert into public.audit_events (table_name, record_key, operation)
values ('public.test', 'id=1', 'insert');
select throws_ok(
    $$update public.audit_events set record_key = 'id=2' where table_name = 'public.test'$$,
    '55000',
    'audit_events is append-only',
    'audit events cannot be mutated'
);

insert into public.sources (source_id, kind, label)
values ('AUDIT-TEST-SOURCE', 'reference', 'Audit redaction test');
insert into public.source_versions (
    source_id, version_number, parse_status, extracted_text, extraction_metadata
) values (
    'AUDIT-TEST-SOURCE', 1, 'pending', repeat('x', 1024), '{"large":"metadata"}'::jsonb
);
select ok(
    (
        select
            not (event.new_data ? 'extracted_text')
            and not (event.new_data ? 'extraction_metadata')
            and (event.new_data #>> '{_large_fields,extracted_text_bytes}')::integer = 1024
        from public.audit_events as event
        where event.table_name = 'public.source_versions'
        order by event.audit_event_id desc
        limit 1
    ),
    'large extracted source payload is summarized in audit log'
);

insert into public.domains (
    domain_id, name, description, display_order, color_token
) values ('TST', 'RLS test domain', '', 999999, 'research.default');

set local role anon;
select throws_ok(
    $$select * from public.domains where domain_id = 'TST'$$,
    '42501',
    'permission denied for table domains',
    'anon has no authoring table privilege'
);
reset role;

insert into auth.users (
    id, aud, role, email, encrypted_password, email_confirmed_at,
    raw_app_meta_data, raw_user_meta_data, created_at, updated_at
) values (
    '20000000-0000-0000-0000-000000000002',
    'authenticated',
    'authenticated',
    'viewer-rls-test@example.invalid',
    '',
    clock_timestamp(),
    '{}'::jsonb,
    '{"display_name":"Viewer RLS test"}'::jsonb,
    clock_timestamp(),
    clock_timestamp()
);
select is(
    (
        select role::text
        from public.admin_users
        where user_id = '20000000-0000-0000-0000-000000000002'
    ),
    'viewer',
    'new Auth user is automatically provisioned as viewer'
);

select set_config('request.jwt.claim.sub', '20000000-0000-0000-0000-000000000002', true);
set local role authenticated;
select is(
    (select count(*) from public.domains where domain_id = 'TST'),
    1::bigint,
    'viewer can read authoring content'
);
select lives_ok(
    $$update public.domains set name = 'viewer tampered' where domain_id = 'TST'$$,
    'viewer write is safely filtered by RLS'
);
select is(
    (select name from public.domains where domain_id = 'TST'),
    'RLS test domain',
    'viewer cannot modify authoring content'
);
reset role;

select * from finish();
rollback;
