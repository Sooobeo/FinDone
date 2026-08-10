begin;

create extension if not exists pgtap with schema extensions;
select plan(27);

select has_function('public', 'claim_ingestion_job', 'atomic job claim RPC exists');
select has_function(
    'public',
    'complete_content_validation_job',
    'atomic validation completion RPC exists'
);
select has_function('public', 'fail_ingestion_job', 'atomic worker failure RPC exists');
select like(
    pg_get_function_arguments(
        'public.start_revision_validation(uuid,text,text)'::regprocedure
    ),
    '%admin-v1%',
    'direct validation RPC defaults to the worker validator contract'
);
select ok(
    not has_function_privilege(
        'authenticated',
        'public.claim_ingestion_job(text, public.job_kind[])',
        'EXECUTE'
    ),
    'authenticated users cannot claim worker jobs'
);
select ok(
    has_function_privilege(
        'service_role',
        'public.claim_ingestion_job(text, public.job_kind[])',
        'EXECUTE'
    ),
    'service role can claim worker jobs'
);

insert into public.content_revisions (
    revision_id, entity_type, entity_key, revision_number, operation, snapshot, content_hash
) values
(
    '71000000-0000-0000-0000-000000000001',
    'element',
    'TST-01',
    1,
    'update',
    '{"element_id":"TST-01"}'::jsonb,
    encode(
        extensions.digest(
            convert_to('{"element_id":"TST-01"}'::jsonb::text, 'UTF8'),
            'sha256'
        ),
        'hex'
    )
),
(
    '71000000-0000-0000-0000-000000000002',
    'element',
    'TST-02',
    1,
    'update',
    '{"element_id":"TST-02"}'::jsonb,
    encode(
        extensions.digest(
            convert_to('{"element_id":"TST-02"}'::jsonb::text, 'UTF8'),
            'sha256'
        ),
        'hex'
    )
);

insert into public.revision_state_events (revision_id, state, note) values
('71000000-0000-0000-0000-000000000001', 'draft', 'worker RPC test'),
('71000000-0000-0000-0000-000000000002', 'draft', 'worker RPC failure test');

insert into public.validation_runs (
    validation_run_id, target_type, revision_id, validator_name, validator_version
) values
(
    '72000000-0000-0000-0000-000000000001',
    'revision',
    '71000000-0000-0000-0000-000000000001',
    'test-validator',
    '1'
),
(
    '72000000-0000-0000-0000-000000000002',
    'revision',
    '71000000-0000-0000-0000-000000000002',
    'test-validator',
    '1'
);

insert into public.ingestion_jobs (
    job_id, job_kind, revision_id, input
) values
(
    '73000000-0000-0000-0000-000000000001',
    'content_validation',
    '71000000-0000-0000-0000-000000000001',
    '{"validationRunId":"72000000-0000-0000-0000-000000000001"}'::jsonb
),
(
    '73000000-0000-0000-0000-000000000002',
    'content_validation',
    '71000000-0000-0000-0000-000000000002',
    '{"validationRunId":"72000000-0000-0000-0000-000000000002"}'::jsonb
);

select set_config('request.jwt.claim.role', 'service_role', true);
set local role service_role;

select is(
    (
        public.claim_ingestion_job(
            'validation-test-1',
            array['content_validation'::public.job_kind]
        )
    ).status::text,
    'running',
    'claim moves the selected job to running'
);
select is(
    (
        select attempt_count
        from public.ingestion_jobs
        where job_id = '73000000-0000-0000-0000-000000000001'
    ),
    1,
    'claim increments attempt count once'
);
select is(
    (
        select status::text
        from public.validation_runs
        where validation_run_id = '72000000-0000-0000-0000-000000000001'
    ),
    'running',
    'claim starts the matching validation run atomically'
);
select is(
    (
        public.claim_ingestion_job(
            'validation-test-1',
            array['content_validation'::public.job_kind]
        )
    ).job_id,
    '73000000-0000-0000-0000-000000000001'::uuid,
    'same worker id recovers an existing running claim'
);
select is(
    (
        select attempt_count
        from public.ingestion_jobs
        where job_id = '73000000-0000-0000-0000-000000000001'
    ),
    1,
    'claim recovery does not consume another attempt'
);

select is(
    public.complete_content_validation_job(
        '73000000-0000-0000-0000-000000000001',
        'validation-test-1',
        '72000000-0000-0000-0000-000000000001',
        'passed',
        2,
        2,
        0,
        '{"test":true}'::jsonb,
        '[]'::jsonb,
        '{"validatorVersion":"test"}'::jsonb
    ) ->> 'validationStatus',
    'passed',
    'completion seals a successful validation run'
);
select is(
    (
        select status::text
        from public.ingestion_jobs
        where job_id = '73000000-0000-0000-0000-000000000001'
    ),
    'succeeded',
    'content validation failure or pass is a successfully executed job'
);
select is(
    public.complete_content_validation_job(
        '73000000-0000-0000-0000-000000000001',
        'validation-test-1',
        '72000000-0000-0000-0000-000000000001',
        'passed',
        2,
        2,
        0,
        '{"test":true}'::jsonb,
        '[]'::jsonb,
        '{"validatorVersion":"test"}'::jsonb
    ) ->> 'alreadyTerminal',
    'true',
    'completion RPC safely reconciles a lost successful response'
);

select throws_ok(
    $$select public.claim_ingestion_job(
        'validation-test-forbidden',
        array['url_fetch'::public.job_kind]
    )$$,
    '22023',
    'allowed job kinds must contain only non-network worker jobs',
    'claim RPC cannot claim SSRF-sensitive URL jobs'
);

select is(
    (
        public.claim_ingestion_job(
            'validation-test-2',
            array['content_validation'::public.job_kind]
        )
    ).job_id,
    '73000000-0000-0000-0000-000000000002'::uuid,
    'a second worker claims the next queued validation job'
);
update public.ingestion_jobs
set claimed_at = clock_timestamp() - interval '20 minutes'
where job_id = '73000000-0000-0000-0000-000000000002';
select is(
    (
        public.claim_ingestion_job(
            'validation-test-3',
            array['content_validation'::public.job_kind]
        )
    ).job_id,
    '73000000-0000-0000-0000-000000000002'::uuid,
    'a new worker atomically reclaims an expired running lease'
);
select is(
    (
        select attempt_count
        from public.ingestion_jobs
        where job_id = '73000000-0000-0000-0000-000000000002'
    ),
    2,
    'stale lease reclaim consumes one retry attempt'
);
select is(
    public.fail_ingestion_job(
        '73000000-0000-0000-0000-000000000002',
        'validation-test-3',
        'simulated worker failure',
        '{}'::jsonb
    ) ->> 'jobStatus',
    'failed',
    'worker failure atomically fails its claimed job'
);
select is(
    public.fail_ingestion_job(
        '73000000-0000-0000-0000-000000000002',
        'validation-test-3',
        'simulated lost failure response',
        '{}'::jsonb
    ) ->> 'alreadyTerminal',
    'true',
    'failure RPC safely reconciles a lost terminal response'
);
select is(
    (
        select status::text
        from public.validation_runs
        where validation_run_id = '72000000-0000-0000-0000-000000000002'
    ),
    'failed',
    'worker failure also fails the active validation run'
);
select is(
    (
        select count(*)
        from public.validation_issues
        where validation_run_id = '72000000-0000-0000-0000-000000000002'
          and code = 'worker_failure'
          and severity = 'error'
    ),
    1::bigint,
    'worker failure records one error issue while the run is active'
);

reset role;
insert into auth.users (
    id, aud, role, email, encrypted_password, email_confirmed_at,
    raw_app_meta_data, raw_user_meta_data, created_at, updated_at
) values (
    '74000000-0000-0000-0000-000000000001',
    'authenticated',
    'authenticated',
    'validation-worker-test@example.invalid',
    '',
    clock_timestamp(),
    '{}'::jsonb,
    '{}'::jsonb,
    clock_timestamp(),
    clock_timestamp()
);
select set_config('request.jwt.claim.role', 'service_role', true);
select set_config(
    'request.jwt.claim.sub',
    '74000000-0000-0000-0000-000000000001',
    true
);
set local role service_role;
select is(
    (
        public.submit_review(
            '71000000-0000-0000-0000-000000000001',
            'approved',
            'release schema assertion setup'
        )
    ).decision::text,
    'approved',
    'the passed revision can be approved for a release projection'
);
select is(
    (
        public.create_release_from_approved(
            '75000000-0000-0000-0000-000000000001',
            'validation-worker-test-release',
            'schema contract assertion',
            1
        )
    ).schema_version,
    1,
    'release creation uses packaged Android database schema version 1'
);
select is(
    (
        public.create_release_from_approved(
            '75000000-0000-0000-0000-000000000001',
            'ignored-idempotent-retry-name',
            'ignored idempotent retry notes',
            2
        )
    ).release_id,
    (
        select release_id
        from public.content_releases
        where create_request_key = '75000000-0000-0000-0000-000000000001'
    ),
    'the same release request UUID returns the original release'
);
select is(
    (
        select count(*)
        from public.ingestion_jobs as job
        join public.content_releases as release on release.release_id = job.release_id
        where release.create_request_key = '75000000-0000-0000-0000-000000000001'
          and job.job_kind = 'release_build'
    ),
    1::bigint,
    'idempotent release retries leave exactly one release_build job'
);

reset role;
select set_config('request.jwt.claim.role', 'authenticated', true);
set local role authenticated;
select throws_ok(
    $$select public.claim_ingestion_job(
        'validation-test-authenticated',
        array['content_validation'::public.job_kind]
    )$$,
    '42501',
    'permission denied for function claim_ingestion_job',
    'authenticated role cannot invoke the claim RPC'
);
reset role;

select * from finish();
rollback;
