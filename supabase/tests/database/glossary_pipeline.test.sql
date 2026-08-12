begin;

create extension if not exists pgtap with schema extensions;
select plan(24);

select has_table('public', 'glossary_categories', 'glossary category catalog exists');
select has_table('public', 'glossary_terms', 'authored glossary terms exist');
select has_table('public', 'glossary_term_admin_references', 'private Admin references exist');
select has_table('public', 'glossary_releases', 'independent glossary releases exist');
select has_table('public', 'glossary_compile_jobs', 'independent glossary compile queue exists');
select has_function(
    'public', 'queue_glossary_compile', array['text', 'integer'],
    'owner glossary compile queue RPC exists'
);
select has_function(
    'public', 'archive_glossary_term_and_queue_compile', array['text', 'text'],
    'owner glossary archive RPC exists'
);
select has_function(
    'public', 'claim_glossary_compile_job', array['text'],
    'deterministic glossary worker claim RPC exists'
);
select has_function(
    'public', 'complete_glossary_compile_job',
    array['uuid','text','text','text','text','text','bigint','bigint','text','text','integer','jsonb'],
    'verified glossary publish RPC exists'
);
select ok(
    has_function_privilege(
        'authenticated', 'public.queue_glossary_compile(text,integer)', 'EXECUTE'
    ),
    'authenticated owner may invoke the guarded compile RPC'
);
select ok(
    not has_function_privilege(
        'anon', 'public.queue_glossary_compile(text,integer)', 'EXECUTE'
    ),
    'anonymous users cannot queue a glossary compile'
);
select ok(
    not has_function_privilege(
        'authenticated',
        'public.complete_glossary_compile_job(uuid,text,text,text,text,text,bigint,bigint,text,text,integer,jsonb)',
        'EXECUTE'
    ),
    'authenticated users cannot forge a compiled glossary'
);
select ok(
    has_function_privilege(
        'service_role',
        'public.complete_glossary_compile_job(uuid,text,text,text,text,text,bigint,bigint,text,text,integer,jsonb)',
        'EXECUTE'
    ),
    'service role can publish a verified glossary artifact'
);
select ok(
    has_table_privilege('service_role', 'public.glossary_release_channels', 'SELECT'),
    'stable endpoint service role can read the glossary channel'
);
select ok(
    not has_table_privilege('authenticated', 'public.glossary_terms', 'INSERT'),
    'authenticated users cannot bypass glossary authoring RPCs'
);

insert into auth.users (
    id, aud, role, email, encrypted_password, email_confirmed_at,
    raw_app_meta_data, raw_user_meta_data, created_at, updated_at
) values (
    'b0000000-0000-0000-0000-000000000001',
    'authenticated', 'authenticated', 'glossary-pipeline-test@example.invalid', '',
    clock_timestamp(), '{}'::jsonb, '{}'::jsonb, clock_timestamp(), clock_timestamp()
);
insert into public.admin_users(user_id, role, display_name, is_active) values
('b0000000-0000-0000-0000-000000000001', 'owner', 'Glossary test owner', true);

insert into public.glossary_categories(category_id, name, display_order)
select to_char(value, 'FM00'), '테스트 카테고리 ' || value::text, value - 1
from generate_series(1, 21) as value;
insert into public.glossary_sources(source_code, title, public_url) values
('S01', 'Official glossary', 'https://example.com/official-glossary');
insert into public.sources(source_id, kind, label, locator, source_type) values
('GLOSSARY-PRIVATE-PDF', 'file', 'Private glossary source',
 'owner/glossary/private.pdf', 'application/pdf');

insert into public.glossary_terms(
    term_id, category_id, display_order, canonical_name_en, canonical_name_ko,
    aliases, concept_type, one_line_definition_ko, core_definition_ko,
    practical_context_ko, why_it_matters_ko, example_ko, limitations_ko,
    source_codes, jurisdictions, as_of_date, review_status, related_term_ids
) values
(
    'FIN-01-001', '01', 0, 'Archived Term', '삭제 대상 용어', '{}', 'INSTRUMENT',
    '삭제 동기화 검증에 사용하는 충분히 긴 한 문장 용어 정의이다.',
    '이 용어는 Admin에서 보관 처리한 항목이 다음 앱용 정적 데이터베이스에서 제외되는지를 검증하기 위한 테스트 항목이다.',
    '관리자가 용어를 삭제하고 새 오프라인 데이터베이스를 컴파일하는 실제 흐름을 모사한다.',
    '삭제된 항목이 앱 검색에 계속 남는 오류를 방지하는 데 중요하다.',
    '관리자가 이 용어를 삭제하면 후속 stable 용어집 검색에서는 결과가 나오지 않는다.',
    array['테스트 전용 항목이며 실제 금융 정의가 아니다.'], array['S01'], array['GLOBAL'],
    '2026-08-12', 'agent_reviewed', array['FIN-01-002']
),
(
    'FIN-01-002', '01', 1, 'Remaining Term', '잔존 용어', '{}', 'INSTRUMENT',
    '삭제 이후에도 남아야 하는 충분히 긴 한 문장 용어 정의이다.',
    '이 용어는 한 항목을 삭제한 후에도 나머지 활성 용어가 앱용 정적 데이터베이스 snapshot에 유지되는지를 검증한다.',
    '컴파일 Worker가 활성 용어만 읽고 유효한 최소 용어집을 만드는 실제 흐름을 모사한다.',
    '부분 삭제가 전체 용어집을 비우지 않는다는 점을 확인하는 데 중요하다.',
    '첫 번째 용어가 삭제된 뒤 Worker snapshot에는 이 두 번째 용어만 포함된다.',
    array['테스트 전용 항목이며 실제 금융 정의가 아니다.'], array['S01'], array['GLOBAL'],
    '2026-08-12', 'agent_reviewed', '{}'
);
insert into public.glossary_term_admin_references(term_id, source_id) values
('FIN-01-001', 'GLOSSARY-PRIVATE-PDF');

select set_config('request.jwt.claim.role', 'authenticated', true);
select set_config('request.jwt.claim.sub', 'b0000000-0000-0000-0000-000000000001', true);
set local role authenticated;

select is(
    public.archive_glossary_term_and_queue_compile(
        'FIN-01-001', 'pgTAP deletion propagation test'
    ) ->> 'archived',
    'true',
    'Admin deletion archives the requested glossary term'
);
select is(
    (select is_active from public.glossary_terms where term_id = 'FIN-01-001'),
    false,
    'archived term is no longer active'
);
select is(
    (select count(*) from public.glossary_compile_jobs where status = 'queued'),
    1::bigint,
    'Admin deletion atomically queues one glossary compile'
);
select is(
    (
        select release.term_count
        from public.glossary_releases as release
        join public.glossary_compile_jobs as job on job.release_id = release.release_id
        where job.status = 'queued'
    ),
    1,
    'queued release records the remaining active term count'
);
select is(
    (select count(*) from public.glossary_term_admin_references where term_id = 'FIN-01-001'),
    1::bigint,
    'private source evidence remains in Admin audit storage after soft deletion'
);

reset role;
select set_config('request.jwt.claim.role', 'service_role', true);
select set_config(
    'test.glossary_claim',
    public.claim_glossary_compile_job('glossary-pgtap-worker')::text,
    true
);
set local role service_role;

select is(
    jsonb_array_length(current_setting('test.glossary_claim')::jsonb #> '{snapshot,terms}'),
    1,
    'worker snapshot contains active terms only'
);
select is(
    current_setting('test.glossary_claim')::jsonb #>> '{snapshot,terms,0,termId}',
    'FIN-01-002',
    'archived term is absent from the app compile snapshot'
);
select ok(
    not ((current_setting('test.glossary_claim')::jsonb #> '{snapshot,terms,0}')
        ? 'adminReferenceSourceIds'),
    'private Admin reference IDs are absent from the app compile snapshot'
);
select ok(
    position('GLOSSARY-PRIVATE-PDF' in current_setting('test.glossary_claim')) = 0,
    'private PDF identity never crosses the glossary compile boundary'
);

select * from finish();
rollback;
