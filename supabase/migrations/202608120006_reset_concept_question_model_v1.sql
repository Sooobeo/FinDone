begin;

-- The v1 question direction (description/formula -> term) was retired before
-- release. Its append-only decisions and edits cannot be applied to the v2
-- contract (term -> prose description), so this one-time migration removes
-- only those incompatible audit rows. The reviewed concept source data and
-- all unrelated Admin content remain untouched.
truncate table
    public.concept_question_edits,
    public.concept_question_review_decisions;

comment on table public.concept_question_review_decisions is
    'Append-only Owner decisions for the active concept-question contract; v1 rows were retired by migration 202608120006.';

comment on table public.concept_question_edits is
    'Append-only Owner edits for the active concept-question contract; v1 rows were retired by migration 202608120006.';

commit;
