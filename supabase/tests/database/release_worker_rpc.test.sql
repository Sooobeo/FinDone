begin;

create extension if not exists pgtap with schema extensions;
select plan(20);

select has_function('public', 'complete_release_build_job', 'release build completion RPC exists');
select has_function('public', 'complete_release_validation_job', 'release validation completion RPC exists');
select has_function('public', 'fail_release_job', 'release worker failure RPC exists');
select ok(
    not has_function_privilege(
        'authenticated',
        'public.complete_release_build_job(uuid,text,jsonb,text,bigint,text,bigint,text,text,jsonb)',
        'EXECUTE'
    ),
    'authenticated users cannot complete release builds'
);
select ok(
    not has_function_privilege(
        'authenticated',
        'public.complete_release_validation_job(uuid,text,uuid,public.validation_status,integer,integer,integer,jsonb,jsonb,jsonb)',
        'EXECUTE'
    ),
    'authenticated users cannot complete release validation'
);
select ok(
    has_function_privilege(
        'service_role',
        'public.complete_release_build_job(uuid,text,jsonb,text,bigint,text,bigint,text,text,jsonb)',
        'EXECUTE'
    ),
    'service role can complete release builds'
);
select ok(
    has_function_privilege(
        'service_role',
        'public.complete_release_validation_job(uuid,text,uuid,public.validation_status,integer,integer,integer,jsonb,jsonb,jsonb)',
        'EXECUTE'
    ),
    'service role can complete release validation'
);

insert into auth.users (
    id, aud, role, email, encrypted_password, email_confirmed_at,
    raw_app_meta_data, raw_user_meta_data, created_at, updated_at
) values (
    '81000000-0000-0000-0000-000000000001',
    'authenticated',
    'authenticated',
    'release-worker-test@example.invalid',
    '',
    clock_timestamp(),
    '{}'::jsonb,
    '{}'::jsonb,
    clock_timestamp(),
    clock_timestamp()
);

select set_config('request.jwt.claim.role', 'service_role', true);
select set_config('request.jwt.claim.sub', '81000000-0000-0000-0000-000000000001', true);
set local role service_role;

insert into public.content_revisions (
    revision_id, entity_type, entity_key, revision_number, operation, snapshot, content_hash
) values (
    '81100000-0000-0000-0000-000000000001',
    'element',
    'TST-REL-01',
    1,
    'update',
    '{"element_id":"TST-REL-01"}'::jsonb,
    repeat('a', 64)
);
insert into public.revision_state_events (revision_id, state, note)
values ('81100000-0000-0000-0000-000000000001', 'draft', 'release worker RPC test');

insert into public.validation_runs (
    validation_run_id, target_type, revision_id, validator_name, validator_version
) values (
    '81200000-0000-0000-0000-000000000001',
    'revision',
    '81100000-0000-0000-0000-000000000001',
    'release-worker-test',
    '1'
);
update public.validation_runs
set status = 'running'
where validation_run_id = '81200000-0000-0000-0000-000000000001';
update public.validation_runs
set status = 'passed', checks_total = 1, checks_passed = 1, checks_failed = 0
where validation_run_id = '81200000-0000-0000-0000-000000000001';

select is(
    (
        public.submit_review(
            '81100000-0000-0000-0000-000000000001',
            'approved',
            'release worker RPC setup'
        )
    ).decision::text,
    'approved',
    'the test revision is approved through the normal review path'
);

select is(
    (
        public.create_release_from_approved(
            '81300000-0000-0000-0000-000000000001',
            'release-worker-rpc-test',
            'automatic stable publication test',
            1
        )
    ).status::text,
    'building',
    'release creation queues a building release'
);

select is(
    (
        public.claim_ingestion_job(
            'release-rpc-test',
            array['release_build'::public.job_kind]
        )
    ).status::text,
    'running',
    'release worker claims the build job'
);

insert into storage.objects (bucket_id, name)
select 'release-bundles', release.release_id::text || '/content.sqlite3'
from public.content_releases as release
where release.create_request_key = '81300000-0000-0000-0000-000000000001';
insert into storage.objects (bucket_id, name)
select 'release-bundles', release.release_id::text || '/content-manifest.json'
from public.content_releases as release
where release.create_request_key = '81300000-0000-0000-0000-000000000001';

select is(
    public.complete_release_build_job(
        (
            select job.job_id from public.ingestion_jobs as job
            join public.content_releases as release on release.release_id = job.release_id
            where release.create_request_key = '81300000-0000-0000-0000-000000000001'
              and job.job_kind = 'release_build'
        ),
        'release-rpc-test',
        jsonb_build_object(
            'manifestVersion', 1,
            'schemaVersion', 1,
            'contentDbVersion', (
                select content_version from public.content_releases
                where create_request_key = '81300000-0000-0000-0000-000000000001'
            ),
            'databaseAsset', 'content.sqlite3',
            'sha256', repeat('d', 64),
            'byteSize', 1234,
            'rowCounts', '{}'::jsonb,
            'domainElementCounts', '{}'::jsonb
        ),
        repeat('c', 64),
        321,
        repeat('d', 64),
        1234,
        (
            select release_id::text || '/content.sqlite3' from public.content_releases
            where create_request_key = '81300000-0000-0000-0000-000000000001'
        ),
        (
            select release_id::text || '/content-manifest.json' from public.content_releases
            where create_request_key = '81300000-0000-0000-0000-000000000001'
        ),
        '{}'::jsonb
    ) ->> 'jobStatus',
    'succeeded',
    'build completion seals both artifacts'
);
select is(
    (
        select count(*) from public.release_artifacts as artifact
        join public.content_releases as release on release.release_id = artifact.release_id
        where release.create_request_key = '81300000-0000-0000-0000-000000000001'
    ),
    2::bigint,
    'build completion records database and manifest artifacts'
);
select is(
    (
        select status::text from public.ingestion_jobs as job
        join public.content_releases as release on release.release_id = job.release_id
        where release.create_request_key = '81300000-0000-0000-0000-000000000001'
          and job.job_kind = 'release_validation'
    ),
    'queued',
    'build completion automatically queues release validation'
);
select is(
    (
        public.claim_ingestion_job(
            'release-rpc-test',
            array['release_validation'::public.job_kind]
        )
    ).job_kind::text,
    'release_validation',
    'the same worker run can immediately claim automatic validation'
);
select is(
    public.complete_release_validation_job(
        (
            select job.job_id from public.ingestion_jobs as job
            join public.content_releases as release on release.release_id = job.release_id
            where release.create_request_key = '81300000-0000-0000-0000-000000000001'
              and job.job_kind = 'release_validation'
        ),
        'release-rpc-test',
        (
            select (job.input ->> 'validationRunId')::uuid
            from public.ingestion_jobs as job
            join public.content_releases as release on release.release_id = job.release_id
            where release.create_request_key = '81300000-0000-0000-0000-000000000001'
              and job.job_kind = 'release_validation'
        ),
        'passed',
        2,
        2,
        0,
        '{"database":"verified"}'::jsonb,
        '[]'::jsonb,
        '{}'::jsonb
    ) ->> 'releaseStatus',
    'published',
    'passing validation automatically publishes the release'
);
select is(
    (
        select status::text from public.content_releases
        where create_request_key = '81300000-0000-0000-0000-000000000001'
    ),
    'published',
    'the release reaches published state'
);
select is(
    (
        select channel.release_id from public.release_channels as channel
        where channel.channel = 'stable'
    ),
    (
        select release_id from public.content_releases
        where create_request_key = '81300000-0000-0000-0000-000000000001'
    ),
    'stable points to the validated release'
);
select is(
    public.current_revision_state('81100000-0000-0000-0000-000000000001')::text,
    'published',
    'frozen approved revisions are marked published'
);
select is(
    public.complete_release_build_job(
        (
            select job.job_id from public.ingestion_jobs as job
            join public.content_releases as release on release.release_id = job.release_id
            where release.create_request_key = '81300000-0000-0000-0000-000000000001'
              and job.job_kind = 'release_build'
        ),
        'release-rpc-test',
        '{}'::jsonb,
        repeat('c', 64),
        1,
        repeat('d', 64),
        1,
        (
            select release_id::text || '/content.sqlite3' from public.content_releases
            where create_request_key = '81300000-0000-0000-0000-000000000001'
        ),
        (
            select release_id::text || '/content-manifest.json' from public.content_releases
            where create_request_key = '81300000-0000-0000-0000-000000000001'
        ),
        '{}'::jsonb
    ) ->> 'alreadyTerminal',
    'true',
    'a retried build completion returns its terminal state'
);
select is(
    public.complete_release_validation_job(
        (
            select job.job_id from public.ingestion_jobs as job
            join public.content_releases as release on release.release_id = job.release_id
            where release.create_request_key = '81300000-0000-0000-0000-000000000001'
              and job.job_kind = 'release_validation'
        ),
        'release-rpc-test',
        (
            select (job.input ->> 'validationRunId')::uuid
            from public.ingestion_jobs as job
            join public.content_releases as release on release.release_id = job.release_id
            where release.create_request_key = '81300000-0000-0000-0000-000000000001'
              and job.job_kind = 'release_validation'
        ),
        'passed',
        1,
        1,
        0,
        '{}'::jsonb,
        '[]'::jsonb,
        '{}'::jsonb
    ) ->> 'alreadyTerminal',
    'true',
    'a retried validation completion returns its terminal state'
);

reset role;
select * from finish();
rollback;
