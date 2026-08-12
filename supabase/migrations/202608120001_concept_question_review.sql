begin;

create table public.concept_question_review_decisions (
    concept_question_review_decision_id uuid primary key default gen_random_uuid(),
    review_input_sha256 text not null,
    question_id text not null,
    question_fingerprint text not null,
    decision text not null,
    comment text not null default '',
    reviewer_id uuid not null references auth.users(id) on delete restrict,
    decided_at timestamptz not null default clock_timestamp(),
    constraint concept_question_review_input_sha256_shape
        check (review_input_sha256 ~ '^[0-9a-f]{64}$'),
    constraint concept_question_fingerprint_shape
        check (question_fingerprint ~ '^[0-9a-f]{64}$'),
    constraint concept_question_id_shape
        check (length(question_id) between 1 and 160 and question_id ~ '^[A-Za-z0-9_-]+$'),
    constraint concept_question_review_decision_value
        check (decision in ('approved', 'rejected')),
    constraint concept_question_review_comment_length
        check (length(comment) <= 2000),
    constraint concept_question_rejection_reason
        check (decision <> 'rejected' or btrim(comment) <> '')
);

create index concept_question_review_lookup_idx
on public.concept_question_review_decisions (
    review_input_sha256,
    question_id,
    question_fingerprint,
    decided_at desc
);

create trigger concept_question_review_decisions_append_only
before update or delete on public.concept_question_review_decisions
for each row execute function public.prevent_row_mutation();

alter table public.concept_question_review_decisions enable row level security;

create policy concept_question_review_decisions_admin_select
on public.concept_question_review_decisions for select to authenticated
using ((select public.is_admin()));

create or replace function public.submit_concept_question_review(
    p_review_input_sha256 text,
    p_question_id text,
    p_question_fingerprint text,
    p_decision text,
    p_comment text default ''
)
returns public.concept_question_review_decisions
language plpgsql
security definer
set search_path = ''
as $$
declare
    result public.concept_question_review_decisions%rowtype;
    normalized_comment text := btrim(coalesce(p_comment, ''));
begin
    if not public.has_admin_role(array['owner']::public.admin_role[]) then
        raise exception using errcode = '42501', message = 'owner role required';
    end if;
    if p_review_input_sha256 !~ '^[0-9a-f]{64}$'
       or p_question_fingerprint !~ '^[0-9a-f]{64}$'
       or length(coalesce(p_question_id, '')) not between 1 and 160
       or p_question_id !~ '^[A-Za-z0-9_-]+$' then
        raise exception using errcode = '22023', message = 'invalid concept question review target';
    end if;
    if p_decision not in ('approved', 'rejected') then
        raise exception using errcode = '22023', message = 'invalid concept question review decision';
    end if;
    if length(normalized_comment) > 2000 then
        raise exception using errcode = '22023', message = 'concept question review comment is too long';
    end if;
    if p_decision = 'rejected' and normalized_comment = '' then
        raise exception using errcode = '22023', message = 'rejection reason required';
    end if;

    insert into public.concept_question_review_decisions (
        review_input_sha256,
        question_id,
        question_fingerprint,
        decision,
        comment,
        reviewer_id
    ) values (
        p_review_input_sha256,
        p_question_id,
        p_question_fingerprint,
        p_decision,
        normalized_comment,
        auth.uid()
    ) returning * into result;
    return result;
end;
$$;

revoke all on table public.concept_question_review_decisions from public, anon, authenticated;
grant select on table public.concept_question_review_decisions to authenticated;
grant select on table public.concept_question_review_decisions to service_role;

revoke all on function public.submit_concept_question_review(text, text, text, text, text)
from public, anon;
grant execute on function public.submit_concept_question_review(text, text, text, text, text)
to authenticated, service_role;

comment on table public.concept_question_review_decisions is
    'Append-only Owner decisions bound to one automated-review input hash and exact question fingerprint.';

commit;
