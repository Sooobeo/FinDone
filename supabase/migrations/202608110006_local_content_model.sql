-- Make the generation queue an implementation detail of the checked-in local
-- compiler. Admin users review/approve candidates but cannot start conversion.

alter table public.content_generation_batches
    alter column model_name set default 'findone-local-content-v1',
    alter column prompt_version set default 'findone-local-schema-v1';

revoke execute on function public.create_content_generation_batch(
    uuid, text, text, text, integer, uuid[], integer
) from authenticated;
grant execute on function public.create_content_generation_batch(
    uuid, text, text, text, integer, uuid[], integer
) to service_role;

comment on table public.content_generation_batches is
    'Checked-in local transformer batches. Admin is final-review only; service_role code enqueues and compiles.';
comment on table public.content_model_runs is
    'Deterministic local-rules execution audit. Token counts remain zero because no external LLM is called.';

update storage.buckets
set allowed_mime_types = (
    select array_agg(distinct mime_type order by mime_type)
    from unnest(
        coalesce(allowed_mime_types, '{}'::text[])
        || array[
            'application/json', 'application/x-ndjson',
            'application/vnd.sqlite3', 'application/x-sqlite3'
        ]::text[]
    ) as accepted(mime_type)
)
where id = 'source-private';
