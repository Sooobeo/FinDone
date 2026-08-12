begin;

create extension if not exists pgtap with schema extensions;
select plan(12);

select has_table('public', 'concept_question_review_decisions', 'concept question review audit table exists');
select has_function(
    'public',
    'submit_concept_question_review',
    array['text', 'text', 'text', 'text', 'text'],
    'owner review RPC exists'
);
select ok(
    (
        select relation.relrowsecurity
        from pg_catalog.pg_class as relation
        join pg_catalog.pg_namespace as namespace on namespace.oid = relation.relnamespace
        where namespace.nspname = 'public'
          and relation.relname = 'concept_question_review_decisions'
    ),
    'concept question review decisions use RLS'
);
select is(
    (
        select count(*)
        from pg_catalog.pg_policies
        where schemaname = 'public'
          and tablename = 'concept_question_review_decisions'
          and policyname = 'concept_question_review_decisions_admin_select'
    ),
    1::bigint,
    'review audit table exposes only the admin read policy'
);

select ok(has_table_privilege('authenticated', 'public.concept_question_review_decisions', 'SELECT'), 'authenticated admins can read review decisions');
select ok(not has_table_privilege('authenticated', 'public.concept_question_review_decisions', 'INSERT'), 'authenticated users cannot insert directly');
select ok(not has_table_privilege('authenticated', 'public.concept_question_review_decisions', 'UPDATE'), 'authenticated users cannot update decisions');
select ok(not has_table_privilege('authenticated', 'public.concept_question_review_decisions', 'DELETE'), 'authenticated users cannot delete decisions');

select ok(
    has_function_privilege(
        'authenticated',
        'public.submit_concept_question_review(text,text,text,text,text)',
        'EXECUTE'
    ),
    'authenticated Owner may call the review RPC'
);
select ok(
    not has_function_privilege(
        'anon',
        'public.submit_concept_question_review(text,text,text,text,text)',
        'EXECUTE'
    ),
    'anonymous users cannot call the review RPC'
);

select col_is_pk(
    'public',
    'concept_question_review_decisions',
    'concept_question_review_decision_id',
    'review decisions have an immutable identity'
);
select has_trigger(
    'public',
    'concept_question_review_decisions',
    'concept_question_review_decisions_append_only',
    'review decisions are append-only'
);

select * from finish();
rollback;
