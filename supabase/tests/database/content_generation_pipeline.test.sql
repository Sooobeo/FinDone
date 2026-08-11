begin;

create extension if not exists pgtap with schema extensions;
select plan(31);

select has_table('public', 'content_generation_batches', 'content generation batches table exists');
select has_table('public', 'content_generation_batch_sources', 'generation source scope table exists');
select has_table('public', 'content_generation_items', 'isolated generation candidates table exists');
select has_table('public', 'content_generation_evidence', 'field evidence table exists');
select has_table('public', 'content_model_runs', 'model audit runs table exists');
select has_view('public', 'content_generation_overview', 'generation status overview exists');
select has_function('public', 'queue_catalog_url_sources', 'catalog URL queue RPC exists');
select has_function('public', 'create_content_generation_batch', 'manual generation queue RPC exists');
select has_function('public', 'enqueue_ready_content_generation', 'automatic ready-source queue RPC exists');
select has_function('public', 'claim_content_generation_batch', 'generation claim RPC exists');
select has_function('public', 'get_content_generation_fragments', 'bounded fragment sampling RPC exists');
select has_function('public', 'update_content_generation_progress', 'generation progress RPC exists');
select has_function('public', 'complete_content_generation_batch', 'generation completion RPC exists');
select has_function('public', 'approve_content_generation_batch', 'single final approval RPC exists');
select ok(
    not has_function_privilege(
        'authenticated',
        'public.claim_content_generation_batch(text,text,text)',
        'EXECUTE'
    ),
    'authenticated users cannot claim generation batches'
);
select ok(
    has_function_privilege(
        'service_role',
        'public.claim_content_generation_batch(text,text,text)',
        'EXECUTE'
    ),
    'service role can claim generation batches'
);
select ok(
    has_function_privilege(
        'service_role',
        'public.queue_catalog_url_sources(text[],integer,boolean)',
        'EXECUTE'
    ),
    'source worker can automatically queue initial catalog URLs'
);
select ok(
    not has_function_privilege(
        'authenticated',
        'public.complete_content_generation_batch(uuid,text,jsonb,jsonb,jsonb,jsonb)',
        'EXECUTE'
    ),
    'authenticated users cannot forge generated candidates'
);
select ok(
    has_function_privilege(
        'service_role',
        'public.complete_content_generation_batch(uuid,text,jsonb,jsonb,jsonb,jsonb)',
        'EXECUTE'
    ),
    'service role can atomically complete generation batches'
);
select ok(
    has_function_privilege(
        'authenticated',
        'public.approve_content_generation_batch(uuid,uuid,text)',
        'EXECUTE'
    ),
    'authenticated owner can invoke the guarded final approval RPC'
);
select ok(
    not has_function_privilege(
        'authenticated',
        'public.generation_entity_snapshot(public.content_entity_type,text)',
        'EXECUTE'
    ),
    'authenticated users cannot call the baseline helper directly'
);

insert into auth.users (
    id, aud, role, email, encrypted_password, email_confirmed_at,
    raw_app_meta_data, raw_user_meta_data, created_at, updated_at
) values (
    'a0000000-0000-0000-0000-000000000001',
    'authenticated',
    'authenticated',
    'generation-worker-test@example.invalid',
    '',
    clock_timestamp(),
    '{}'::jsonb,
    '{}'::jsonb,
    clock_timestamp(),
    clock_timestamp()
);

insert into public.admin_users (user_id, role, display_name, is_active)
values (
    'a0000000-0000-0000-0000-000000000001',
    'owner',
    'Generation worker test owner',
    true
);

select set_config('request.jwt.claim.role', 'service_role', true);
select set_config('request.jwt.claim.sub', 'a0000000-0000-0000-0000-000000000001', true);
set local role service_role;

insert into public.sources (
    source_id, kind, label, locator, source_type, created_by
) values (
    'CATALOG-AUTO-SOURCE', 'pdf', 'Catalog automatic source',
    'https://example.com/catalog-source.pdf', 'reference',
    'a0000000-0000-0000-0000-000000000001'
);

select is(
    public.queue_catalog_url_sources(
        array['CATALOG-AUTO-SOURCE']::text[], 10, false
    ) ->> 'queuedCount',
    '1',
    'source worker automatically queues a public catalog locator regardless of display kind'
);
select is(
    public.queue_catalog_url_sources(
        array['CATALOG-AUTO-SOURCE']::text[], 10, false
    ) ->> 'queuedCount',
    '0',
    'automatic catalog bootstrap never requeues a source that already has an attempted version'
);

insert into public.sources (
    source_id, kind, label, locator, source_type, created_by
) values (
    'GENERATION-PIPELINE-SOURCE', 'url', 'Generation pipeline source',
    'https://example.com/generation-source', 'web',
    'a0000000-0000-0000-0000-000000000001'
);
insert into public.source_versions (
    source_version_id, source_id, version_number, fetch_url, parse_status,
    extracted_text, created_at, created_by
) values (
    'a1000000-0000-0000-0000-000000000001',
    'GENERATION-PIPELINE-SOURCE', 1,
    'https://example.com/generation-source', 'ready',
    'Evidence fragment for a no-change generation test.',
    clock_timestamp() - interval '1 minute',
    'a0000000-0000-0000-0000-000000000001'
);
insert into public.source_fragments (
    source_fragment_id, source_version_id, ordinal, fragment_kind,
    locator, content_text, normalized_text, content_sha256, created_by
) values (
    'a2000000-0000-0000-0000-000000000001',
    'a1000000-0000-0000-0000-000000000001', 0, 'text',
    '{"section":"test"}'::jsonb,
    'Evidence fragment for a no-change generation test.',
    'Evidence fragment for a no-change generation test.',
    repeat('a', 64),
    'a0000000-0000-0000-0000-000000000001'
);

select is(
    (
        public.create_content_generation_batch(
            'a3000000-0000-0000-0000-000000000001',
            'generation-test-model',
            'findone-content-v1',
            'pgTAP no-change generation',
            1,
            array['a1000000-0000-0000-0000-000000000001']::uuid[],
            10
        )
    ).status::text,
    'queued',
    'a ready immutable source creates an isolated queued generation batch'
);

select is(
    (
        public.claim_content_generation_batch(
            'generation:test:1', 'generation-test-model', 'findone-content-v1'
        )
    ).status::text,
    'running',
    'the generation worker atomically claims the queued batch'
);

select is(
    (
        select count(*)::integer
        from public.get_content_generation_fragments(
            (select batch_id from public.content_generation_batches
             where request_key = 'a3000000-0000-0000-0000-000000000001'),
            'generation:test:1',
            20
        )
    ),
    1,
    'the claimed worker receives a bounded immutable fragment sample'
);

select is(
    (
        public.update_content_generation_progress(
            (select batch_id from public.content_generation_batches
             where request_key = 'a3000000-0000-0000-0000-000000000001'),
            'generation:test:1', 40, 'structured_generation',
            '{"processedElementCount":0}'::jsonb
        )
    ).progress_percent,
    40,
    'generation progress and visible processing stage are persisted'
);

select is(
    public.complete_content_generation_batch(
        (select batch_id from public.content_generation_batches
         where request_key = 'a3000000-0000-0000-0000-000000000001'),
        'generation:test:1',
        '[]'::jsonb,
        '[]'::jsonb,
        '[]'::jsonb,
        '{"targetElementCount":0}'::jsonb
    ) ->> 'status',
    'no_changes',
    'a valid evidence batch with no supported changes terminates explicitly'
);

select is(
    (select count(*)::integer from public.content_generation_items
     where batch_id = (select batch_id from public.content_generation_batches
                       where request_key = 'a3000000-0000-0000-0000-000000000001')),
    0,
    'no-change completion does not invent candidate rows'
);
select is(
    (select count(*)::integer from public.content_generation_evidence),
    0,
    'no-change completion does not invent evidence links'
);
select is(
    (select source_count from public.content_generation_overview
     where request_key = 'a3000000-0000-0000-0000-000000000001'),
    1,
    'generation overview reports the frozen source scope'
);

select * from finish();
rollback;
