begin;

create table public.concept_question_edits (
    concept_question_edit_id uuid primary key default gen_random_uuid(),
    review_input_sha256 text not null,
    question_id text not null,
    question_fingerprint text not null,
    element_id text not null,
    stem text not null,
    explanation text not null,
    choices jsonb not null,
    comment text not null default '',
    editor_id uuid not null references auth.users(id) on delete restrict,
    edited_at timestamptz not null default clock_timestamp(),
    constraint concept_question_edit_input_sha256_shape
        check (review_input_sha256 ~ '^[0-9a-f]{64}$'),
    constraint concept_question_edit_fingerprint_shape
        check (question_fingerprint ~ '^[0-9a-f]{64}$'),
    constraint concept_question_edit_question_id_shape
        check (length(question_id) between 1 and 160 and question_id ~ '^[A-Za-z0-9_-]+$'),
    constraint concept_question_edit_element_id_shape
        check (length(element_id) between 1 and 80 and element_id ~ '^[A-Za-z0-9_-]+$'),
    constraint concept_question_edit_stem_length
        check (length(btrim(stem)) between 1 and 20000),
    constraint concept_question_edit_explanation_length
        check (length(btrim(explanation)) between 1 and 20000),
    constraint concept_question_edit_choices_shape
        check (jsonb_typeof(choices) = 'array' and jsonb_array_length(choices) = 5),
    constraint concept_question_edit_comment_length
        check (length(comment) <= 2000)
);

create index concept_question_edits_lookup_idx
on public.concept_question_edits (
    review_input_sha256,
    question_id,
    question_fingerprint,
    edited_at asc
);

create trigger concept_question_edits_append_only
before update or delete on public.concept_question_edits
for each row execute function public.prevent_row_mutation();

alter table public.concept_question_edits enable row level security;

create policy concept_question_edits_admin_select
on public.concept_question_edits for select to authenticated
using ((select public.is_admin()));

create or replace function public.submit_concept_question_edit(
    p_review_input_sha256 text,
    p_question_id text,
    p_question_fingerprint text,
    p_element_id text,
    p_stem text,
    p_explanation text,
    p_choices jsonb,
    p_comment text default ''
)
returns public.concept_question_edits
language plpgsql
security definer
set search_path = ''
as $$
declare
    result public.concept_question_edits%rowtype;
    normalized_stem text := btrim(coalesce(p_stem, ''));
    normalized_explanation text := btrim(coalesce(p_explanation, ''));
    normalized_comment text := btrim(coalesce(p_comment, ''));
begin
    if not public.has_admin_role(array['owner']::public.admin_role[]) then
        raise exception using errcode = '42501', message = 'owner role required';
    end if;
    if p_review_input_sha256 !~ '^[0-9a-f]{64}$'
       or p_question_fingerprint !~ '^[0-9a-f]{64}$'
       or length(coalesce(p_question_id, '')) not between 1 and 160
       or p_question_id !~ '^[A-Za-z0-9_-]+$'
       or length(coalesce(p_element_id, '')) not between 1 and 80
       or p_element_id !~ '^[A-Za-z0-9_-]+$' then
        raise exception using errcode = '22023', message = 'invalid concept question edit target';
    end if;
    if length(normalized_stem) > 20000 or normalized_stem = ''
       or length(normalized_explanation) > 20000 or normalized_explanation = '' then
        raise exception using errcode = '22023', message = 'concept question text is invalid';
    end if;
    if length(normalized_comment) > 2000 then
        raise exception using errcode = '22023', message = 'concept question edit comment is too long';
    end if;
    if p_choices is null
       or jsonb_typeof(p_choices) <> 'array'
       or jsonb_array_length(p_choices) <> 5 then
        raise exception using errcode = '22023', message = 'concept question edits require five choices';
    end if;
    if exists (
        select 1
        from jsonb_array_elements(p_choices) as item(value)
        where jsonb_typeof(item.value) <> 'object'
           or coalesce(item.value ->> 'key', '') not in ('A', 'B', 'C', 'D', 'E')
           or length(btrim(coalesce(item.value ->> 'elementId', ''))) not between 1 and 80
           or length(btrim(coalesce(item.value ->> 'text', ''))) not between 1 and 2000
           or length(btrim(coalesce(item.value ->> 'explanation', ''))) not between 1 and 2000
           or coalesce(item.value ->> 'isCorrect', '') not in ('true', 'false')
    ) then
        raise exception using errcode = '22023', message = 'concept question choice shape is invalid';
    end if;
    if (
        select count(distinct item.value ->> 'key')
        from jsonb_array_elements(p_choices) as item(value)
    ) <> 5 then
        raise exception using errcode = '22023', message = 'concept question choices must have unique A-E keys';
    end if;
    if (
        select count(*)
        from jsonb_array_elements(p_choices) as item(value)
        where item.value ->> 'isCorrect' = 'true'
    ) <> 1 then
        raise exception using errcode = '22023', message = 'concept question edits require one correct choice';
    end if;
    if not exists (
        select 1
        from jsonb_array_elements(p_choices) as item(value)
        where item.value ->> 'isCorrect' = 'true'
          and item.value ->> 'elementId' = p_element_id
    ) then
        raise exception using errcode = '22023', message = 'correct choice must target the question element';
    end if;

    insert into public.concept_question_edits (
        review_input_sha256,
        question_id,
        question_fingerprint,
        element_id,
        stem,
        explanation,
        choices,
        comment,
        editor_id
    ) values (
        p_review_input_sha256,
        p_question_id,
        p_question_fingerprint,
        p_element_id,
        normalized_stem,
        normalized_explanation,
        p_choices,
        normalized_comment,
        auth.uid()
    ) returning * into result;
    return result;
end;
$$;

revoke all on table public.concept_question_edits from public, anon, authenticated;
grant select on table public.concept_question_edits to authenticated;
grant select on table public.concept_question_edits to service_role;

revoke all on function public.submit_concept_question_edit(text, text, text, text, text, text, jsonb, text)
from public, anon;
grant execute on function public.submit_concept_question_edit(text, text, text, text, text, text, jsonb, text)
to authenticated, service_role;

comment on table public.concept_question_edits is
    'Append-only Owner edits bound to one automated-review input hash and exact pre-edit question fingerprint.';

commit;
