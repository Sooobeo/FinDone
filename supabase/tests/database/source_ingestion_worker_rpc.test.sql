begin;

create extension if not exists pgtap with schema extensions;
select plan(53);

select has_table('public', 'source_fragments', 'immutable source fragments table exists');
select has_table('public', 'source_element_candidates', 'source element candidate table exists');
select has_view('public', 'source_catalog_overview', 'source status overview exists');
select has_function('public', 'claim_source_ingestion_job', 'source worker claim RPC exists');
select has_function('public', 'update_source_ingestion_progress', 'source worker progress RPC exists');
select has_function('public', 'complete_source_ingestion_job', 'source worker completion RPC exists');
select has_function('public', 'fail_source_ingestion_job', 'source worker failure RPC exists');
select has_function('public', 'find_reusable_source_file', 'exact-hash Storage reuse RPC exists');
select ok(
    not has_function_privilege(
        'authenticated',
        'public.claim_source_ingestion_job(text)',
        'EXECUTE'
    ),
    'authenticated users cannot claim source jobs'
);
select ok(
    has_function_privilege(
        'service_role',
        'public.claim_source_ingestion_job(text)',
        'EXECUTE'
    ),
    'service role can claim source jobs'
);
select ok(
    has_function_privilege(
        'authenticated',
        'public.find_reusable_source_file(text,bigint)',
        'EXECUTE'
    ),
    'authenticated editors can check exact-hash archive reuse'
);
select ok(
    not has_function_privilege(
        'authenticated',
        'public.complete_source_ingestion_job(uuid,text,text,jsonb,jsonb,jsonb,boolean,jsonb)',
        'EXECUTE'
    ),
    'authenticated users cannot forge source completion'
);

insert into auth.users (
    id, aud, role, email, encrypted_password, email_confirmed_at,
    raw_app_meta_data, raw_user_meta_data, created_at, updated_at
) values (
    '90000000-0000-0000-0000-000000000001',
    'authenticated',
    'authenticated',
    'source-worker-test@example.invalid',
    '',
    clock_timestamp(),
    '{}'::jsonb,
    '{}'::jsonb,
    clock_timestamp(),
    clock_timestamp()
);

insert into public.domains (
    domain_id, name, description, display_order, color_token
) values (
    'TSW', 'Source worker test', '', 987654, 'research.default'
);
insert into public.elements (
    element_id, domain_id, element_number, title, topic_name, subtopic_name,
    mode, core_relation, scope_notes, display_order
) values (
    'TSW-01', 'TSW', 1, '현재가치와 할인율', '기업가치평가', 'DCF',
    'CALCULATION', 'PV = CF / (1 + r)', 'source worker RPC test', 987654
);

insert into public.sources (source_id, kind, label, locator, source_type) values
('SOURCE-WORKER-READY', 'file', 'ready.md', 'owner/sources/ready.md', 'text/markdown'),
('SOURCE-WORKER-FAILED', 'file', 'failed.pdf', 'owner/sources/failed.pdf', 'application/pdf'),
('SOURCE-WORKER-REVIEW', 'file', 'review.png', 'owner/sources/review.png', 'image/png'),
('SOURCE-WORKER-URL', 'url', 'example.com', 'https://example.com/source', 'web');

insert into public.source_versions (
    source_version_id, source_id, version_number, original_filename, mime_type,
    byte_size, sha256, parse_status, fetch_url, created_by
) values
(
    '91000000-0000-0000-0000-000000000001', 'SOURCE-WORKER-READY', 1,
    'ready.md', 'text/markdown', 128, repeat('a', 64), 'pending', null, null
),
(
    '91000000-0000-0000-0000-000000000002', 'SOURCE-WORKER-FAILED', 1,
    'failed.pdf', 'application/pdf', 256, repeat('b', 64), 'pending', null, null
),
(
    '91000000-0000-0000-0000-000000000003', 'SOURCE-WORKER-REVIEW', 1,
    'review.png', 'image/png', 512, repeat('c', 64), 'pending', null, null
),
(
    '91000000-0000-0000-0000-000000000004', 'SOURCE-WORKER-URL', 1,
    null, null, null, null, 'pending', 'https://example.com/source',
    '90000000-0000-0000-0000-000000000001'
);

insert into public.source_files (
    source_version_id, file_role, bucket_id, object_path, original_filename,
    mime_type, byte_size, sha256
) values
(
    '91000000-0000-0000-0000-000000000001', 'original', 'source-private',
    'owner/sources/ready.md', 'ready.md', 'text/markdown', 128, repeat('a', 64)
),
(
    '91000000-0000-0000-0000-000000000002', 'original', 'source-private',
    'owner/sources/failed.pdf', 'failed.pdf', 'application/pdf', 256, repeat('b', 64)
),
(
    '91000000-0000-0000-0000-000000000003', 'original', 'source-private',
    'owner/sources/review.png', 'review.png', 'image/png', 512, repeat('c', 64)
);

insert into public.ingestion_jobs (
    job_id, job_kind, source_version_id, input, created_at
) values
(
    '92000000-0000-0000-0000-000000000004', 'url_fetch',
    '91000000-0000-0000-0000-000000000004',
    '{"url":"https://example.com/source"}'::jsonb,
    '2026-08-11 00:00:04+00'
),
(
    '92000000-0000-0000-0000-000000000001', 'file_extract',
    '91000000-0000-0000-0000-000000000001',
    '{"objectPath":"owner/sources/ready.md"}'::jsonb,
    '2026-08-11 00:00:01+00'
),
(
    '92000000-0000-0000-0000-000000000002', 'file_extract',
    '91000000-0000-0000-0000-000000000002',
    '{"objectPath":"owner/sources/failed.pdf"}'::jsonb,
    '2026-08-11 00:00:02+00'
),
(
    '92000000-0000-0000-0000-000000000003', 'file_extract',
    '91000000-0000-0000-0000-000000000003',
    '{"objectPath":"owner/sources/review.png"}'::jsonb,
    '2026-08-11 00:00:03+00'
);

select set_config('request.jwt.claim.role', 'service_role', true);
set local role service_role;

select is(
    (public.claim_source_ingestion_job('source-rpc-test')).job_id,
    '92000000-0000-0000-0000-000000000001'::uuid,
    'claim selects the oldest file job and ignores an older URL job'
);
select is(
    (
        select status::text
        from public.ingestion_jobs
        where job_id = '92000000-0000-0000-0000-000000000001'
    ),
    'running',
    'claim moves the file job to running'
);
select is(
    (public.claim_source_ingestion_job('source-rpc-test')).job_id,
    '92000000-0000-0000-0000-000000000001'::uuid,
    'the same stable worker recovers its live claim'
);
select is(
    (
        select attempt_count
        from public.ingestion_jobs
        where job_id = '92000000-0000-0000-0000-000000000001'
    ),
    1,
    'claim recovery does not consume a retry'
);
select is(
    (
        select parse_status::text
        from public.source_versions
        where source_version_id = '91000000-0000-0000-0000-000000000001'
    ),
    'extracting',
    'claim marks the source version as extracting'
);
select is(
    public.update_source_ingestion_progress(
        '92000000-0000-0000-0000-000000000001',
        'source-rpc-test',
        46,
        'extracting',
        '{"page":2}'::jsonb
    ) ->> 'stage',
    'extracting',
    'progress RPC reports the real processing stage'
);
select is(
    (
        select progress_percent
        from public.ingestion_jobs
        where job_id = '92000000-0000-0000-0000-000000000001'
    ),
    46::smallint,
    'progress RPC persists the percentage'
);
select is(
    (
        select output ->> 'stage'
        from public.ingestion_jobs
        where job_id = '92000000-0000-0000-0000-000000000001'
    ),
    'extracting',
    'progress RPC persists the stage for the Admin UI'
);
select ok(
    exists (
        select 1
        from public.job_events
        where job_id = '92000000-0000-0000-0000-000000000001'
          and message = 'source processing stage: extracting'
    ),
    'a stage transition creates an append-only job event'
);
select is(
    public.complete_source_ingestion_job(
        '92000000-0000-0000-0000-000000000001',
        'source-rpc-test',
        '현재가치는 미래 현금흐름을 할인율로 할인한다. PV = CF / (1 + r)',
        '{"parserName":"test","route":"R0_DETERMINISTIC_MATCH"}'::jsonb,
        '[
          {"kind":"text","text":"현재가치는 미래 현금흐름을 할인율로 할인한다.","normalizedText":"현재가치는 미래 현금흐름을 할인율로 할인한다.","locator":{"line":1}},
          {"kind":"formula","text":"PV = CF / (1 + r)","normalizedText":"PV = CF / (1 + r)","locator":{"line":2}}
        ]'::jsonb,
        '[
          {"elementId":"TSW-01","rank":1,"score":0.97,"reason":"deterministic title match","matchedTerms":["현재가치","할인율"]}
        ]'::jsonb,
        false,
        '{"route":"R0_DETERMINISTIC_MATCH"}'::jsonb
    ) ->> 'parseStatus',
    'ready',
    'completion seals a deterministic source as ready'
);
select is(
    (
        select parse_status::text
        from public.source_versions
        where source_version_id = '91000000-0000-0000-0000-000000000001'
    ),
    'ready',
    'successful source version is ready'
);
select is(
    (
        select extracted_text
        from public.source_versions
        where source_version_id = '91000000-0000-0000-0000-000000000001'
    ),
    '현재가치는 미래 현금흐름을 할인율로 할인한다. PV = CF / (1 + r)',
    'completion stores normalized extraction output'
);
select is(
    (
        select jsonb_build_object('status', status::text, 'progress', progress_percent)
        from public.ingestion_jobs
        where job_id = '92000000-0000-0000-0000-000000000001'
    ),
    '{"status":"succeeded","progress":100}'::jsonb,
    'completion marks the job succeeded at 100 percent'
);
select is(
    (
        select count(*)
        from public.source_fragments
        where source_version_id = '91000000-0000-0000-0000-000000000001'
    ),
    2::bigint,
    'completion persists every bounded source fragment'
);
select is(
    (
        select count(*)
        from public.source_element_candidates
        where source_version_id = '91000000-0000-0000-0000-000000000001'
    ),
    1::bigint,
    'completion persists deterministic element candidates without approval'
);
select is(
    (
        select count(*)
        from public.element_sources
        where source_id = 'SOURCE-WORKER-READY'
          and element_id = 'TSW-01'
    ),
    1::bigint,
    'unambiguous R0 match automatically creates source lineage'
);
select is(
    (
        select latest_processing_stage
        from public.source_catalog_overview
        where source_id = 'SOURCE-WORKER-READY'
    ),
    'completed',
    'source overview exposes the completed stage'
);
select is(
    (
        select top_candidate_element_id
        from public.source_catalog_overview
        where source_id = 'SOURCE-WORKER-READY'
    ),
    'TSW-01',
    'source overview exposes the top deterministic candidate'
);
select is(
    public.complete_source_ingestion_job(
        '92000000-0000-0000-0000-000000000001',
        'source-rpc-test',
        'same safe retry payload',
        '{}'::jsonb,
        '[{"kind":"text","text":"same safe retry payload","locator":{}}]'::jsonb,
        '[]'::jsonb,
        false,
        '{}'::jsonb
    ) ->> 'alreadyTerminal',
    'true',
    'completion safely reconciles a lost successful response'
);
select is(
    (
        select count(*)
        from public.source_fragments
        where search_vector @@ plainto_tsquery('simple', '할인율')
          and source_version_id = '91000000-0000-0000-0000-000000000001'
    ),
    1::bigint,
    'normalized fragments are searchable through FTS'
);

reset role;
select throws_ok(
    $$update public.source_fragments set content_text = 'tampered' where source_version_id = '91000000-0000-0000-0000-000000000001'$$,
    '55000',
    'source_fragments is append-only',
    'persisted parser evidence cannot be mutated'
);
set local role service_role;

select is(
    (public.claim_source_ingestion_job('source-rpc-test')).job_id,
    '92000000-0000-0000-0000-000000000002'::uuid,
    'worker claims the next file after successful completion'
);
select is(
    public.fail_source_ingestion_job(
        '92000000-0000-0000-0000-000000000002',
        'source-rpc-test',
        'damaged PDF signature',
        '{"failureType":"SourceWorkerError"}'::jsonb
    ) ->> 'jobStatus',
    'failed',
    'failure RPC safely terminates a claimed source job'
);
select is(
    (
        select parse_status::text
        from public.source_versions
        where source_version_id = '91000000-0000-0000-0000-000000000002'
    ),
    'failed',
    'failed extraction marks the source version failed'
);
select is(
    (
        select failure_message
        from public.source_versions
        where source_version_id = '91000000-0000-0000-0000-000000000002'
    ),
    'damaged PDF signature',
    'source failure keeps a bounded operator-facing reason'
);
select is(
    (
        select jsonb_build_object(
            'status', status::text,
            'progress', progress_percent,
            'stage', output ->> 'stage'
        )
        from public.ingestion_jobs
        where job_id = '92000000-0000-0000-0000-000000000002'
    ),
    '{"status":"failed","progress":100,"stage":"failed"}'::jsonb,
    'failed job is terminal and cannot leave an eternal spinner'
);
select is(
    (
        select latest_job_error_message
        from public.source_catalog_overview
        where source_id = 'SOURCE-WORKER-FAILED'
    ),
    'damaged PDF signature',
    'source overview exposes the real processing failure'
);
select is(
    (public.claim_source_ingestion_job('source-rpc-test')).job_id,
    '92000000-0000-0000-0000-000000000003'::uuid,
    'worker claims the remaining file source'
);
select is(
    public.complete_source_ingestion_job(
        '92000000-0000-0000-0000-000000000003',
        'source-rpc-test',
        '',
        '{"reviewReasons":["ocr_confidence_below_0.90"]}'::jsonb,
        '[]'::jsonb,
        '[]'::jsonb,
        true,
        '{"route":"REVIEW_OCR"}'::jsonb
    ) ->> 'parseStatus',
    'needs_review',
    'low-confidence or empty extraction finishes as review-required'
);
select is(
    (
        select parse_status::text
        from public.source_versions
        where source_version_id = '91000000-0000-0000-0000-000000000003'
    ),
    'needs_review',
    'review-required is distinct from processing and failure'
);
select is(
    (
        select latest_processing_stage
        from public.source_catalog_overview
        where source_id = 'SOURCE-WORKER-REVIEW'
    ),
    'needs_review',
    'source overview exposes the terminal review-required stage'
);
select is(
    (public.claim_source_ingestion_job('source-rpc-test')).job_id,
    '92000000-0000-0000-0000-000000000004'::uuid,
    'dedicated source worker claims URL jobs after file jobs'
);
select is(
    (
        select parse_status::text
        from public.source_versions
        where source_version_id = '91000000-0000-0000-0000-000000000004'
    ),
    'fetching',
    'URL claim exposes a real fetching state'
);
select is(
    public.update_source_ingestion_progress(
        '92000000-0000-0000-0000-000000000004',
        'source-rpc-test',
        40,
        'archiving',
        '{"bytesArchived":128}'::jsonb
    ) ->> 'stage',
    'archiving',
    'URL snapshot archive stage is accepted and visible'
);
select is(
    public.complete_source_ingestion_job(
        '92000000-0000-0000-0000-000000000004',
        'source-rpc-test',
        '공개 웹 원본의 현재가치 설명',
        '{
          "sourceByteSize":128,
          "sourceSha256":"dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd",
          "snapshotObjectPath":"90000000-0000-0000-0000-000000000001/sources/SOURCE-WORKER-URL/91000000-0000-0000-0000-000000000004/url-snapshot/source.html",
          "originalFilename":"source.html",
          "mimeType":"text/html",
          "requestedUrl":"https://example.com/source",
          "finalUrl":"https://example.com/final",
          "redirectChain":["https://example.com/source","https://example.com/final"]
        }'::jsonb,
        '[{"kind":"text","text":"공개 웹 원본의 현재가치 설명","locator":{"selector":"main"}}]'::jsonb,
        '[]'::jsonb,
        false,
        '{"route":"R0_URL_CAPTURE"}'::jsonb
    ) ->> 'parseStatus',
    'ready',
    'safe URL capture completes through the same extraction contract'
);
select is(
    (
        select jsonb_build_object('bytes', byte_size, 'sha256', sha256, 'mime', mime_type)
        from public.source_versions
        where source_version_id = '91000000-0000-0000-0000-000000000004'
    ),
    '{"bytes":128,"sha256":"dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd","mime":"text/html"}'::jsonb,
    'URL completion persists reproducible snapshot metadata'
);
select is(
    (
        select count(*)
        from public.source_files
        where source_version_id = '91000000-0000-0000-0000-000000000004'
          and file_role = 'snapshot'
          and bucket_id = 'source-private'
    ),
    1::bigint,
    'URL raw snapshot is registered in private Storage evidence'
);
select is(
    (
        select count(*)
        from public.source_fragments
        where source_version_id = '91000000-0000-0000-0000-000000000004'
    ),
    1::bigint,
    'URL parser output is persisted as immutable evidence'
);
select is(
    (
        select latest_processing_stage
        from public.source_catalog_overview
        where source_id = 'SOURCE-WORKER-URL'
    ),
    'completed',
    'Admin overview shows URL processing completion'
);
select is(
    (
        select status::text
        from public.ingestion_jobs
        where job_id = '92000000-0000-0000-0000-000000000004'
    ),
    'succeeded',
    'URL ingestion job is terminal after successful capture'
);
select ok(
    public.claim_source_ingestion_job('source-rpc-test') is null,
    'source worker returns idle when no file or URL jobs remain'
);

select * from finish();
rollback;
