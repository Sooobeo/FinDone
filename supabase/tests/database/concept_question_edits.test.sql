begin;

create extension if not exists pgtap with schema extensions;
select plan(12);

select has_table('public', 'concept_question_edits', 'concept question edit audit table exists');
select has_function(
    'public',
    'submit_concept_question_edit',
    array['text', 'text', 'text', 'text', 'text', 'text', 'jsonb', 'text'],
    'concept question edit RPC exists'
);
select ok(
    (
        select relation.relrowsecurity
        from pg_catalog.pg_class as relation
        join pg_catalog.pg_namespace as namespace on namespace.oid = relation.relnamespace
        where namespace.nspname = 'public'
          and relation.relname = 'concept_question_edits'
    ),
    'concept question edits use RLS'
);
select is(
    (
        select count(*)
        from pg_catalog.pg_policies
        where schemaname = 'public'
          and tablename = 'concept_question_edits'
          and policyname = 'concept_question_edits_admin_select'
    ),
    1::bigint,
    'edit audit table exposes only the admin read policy'
);
select ok(has_table_privilege('authenticated', 'public.concept_question_edits', 'SELECT'), 'authenticated admins can read edits');
select ok(not has_table_privilege('authenticated', 'public.concept_question_edits', 'INSERT'), 'authenticated users cannot insert edits directly');
select ok(not has_table_privilege('authenticated', 'public.concept_question_edits', 'UPDATE'), 'authenticated users cannot update edits');
select ok(not has_table_privilege('authenticated', 'public.concept_question_edits', 'DELETE'), 'authenticated users cannot delete edits');
select ok(
    has_function_privilege(
        'authenticated',
        'public.submit_concept_question_edit(text,text,text,text,text,text,jsonb,text)',
        'EXECUTE'
    ),
    'authenticated Owner may call the edit RPC'
);
select ok(
    not has_function_privilege(
        'anon',
        'public.submit_concept_question_edit(text,text,text,text,text,text,jsonb,text)',
        'EXECUTE'
    ),
    'anonymous users cannot call the edit RPC'
);
select col_is_pk(
    'public',
    'concept_question_edits',
    'concept_question_edit_id',
    'question edits have an immutable identity'
);
select has_trigger(
    'public',
    'concept_question_edits',
    'concept_question_edits_append_only',
    'question edits are append-only'
);

select * from finish();
rollback;
