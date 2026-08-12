-- Keep the glossary bootstrap compatible with Supabase's safe-update guard.
-- The prior function intentionally archived the whole active snapshot but did
-- not spell that target set out as a WHERE clause.

create or replace function public.import_glossary_snapshot(p_snapshot jsonb)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
    category_count integer;
    source_count integer;
    term_count integer;
    queued jsonb;
begin
    if jsonb_typeof(p_snapshot) <> 'object' then
        raise exception using errcode = '22023', message = 'glossary snapshot must be an object';
    end if;
    select count(*)::integer into category_count from jsonb_array_elements(p_snapshot->'categories');
    select count(*)::integer into source_count from jsonb_array_elements(p_snapshot->'sources');
    select count(*)::integer into term_count from jsonb_array_elements(p_snapshot->'terms');
    if category_count <> 21 or source_count < 1 or term_count < 1 then
        raise exception using errcode = '23514', message = 'glossary snapshot coverage is incomplete';
    end if;

    insert into public.glossary_categories (category_id, name, display_order)
    select item->>'categoryId', item->>'name', (item->>'displayOrder')::integer
    from jsonb_array_elements(p_snapshot->'categories') as item
    on conflict (category_id) do update set
        name = excluded.name,
        display_order = excluded.display_order;

    insert into public.glossary_sources (source_code, title, public_url)
    select item->>'sourceCode', item->>'title', item->>'url'
    from jsonb_array_elements(p_snapshot->'sources') as item
    on conflict (source_code) do update set
        title = excluded.title,
        public_url = excluded.public_url;

    update public.glossary_terms
    set is_active = false,
        archived_at = clock_timestamp(),
        archived_by = auth.uid(),
        change_reason = '용어집 snapshot 교체'
    where is_active = true;

    insert into public.glossary_terms (
        term_id, category_id, display_order, canonical_name_en, canonical_name_ko,
        aliases, concept_type, one_line_definition_ko, core_definition_ko,
        practical_context_ko, why_it_matters_ko, example_ko, limitations_ko,
        source_codes, jurisdictions, as_of_date, review_status, review_flags,
        related_term_ids, formula_latex, formula_notes_ko, is_active,
        content_revision, change_reason, archived_at, archived_by
    )
    select
        item->>'termId', item->>'categoryId', (item->>'displayOrder')::integer,
        item->>'canonicalNameEn', item->>'canonicalNameKo',
        public.glossary_text_array(item->'aliases'), item->>'conceptType',
        item->>'oneLineDefinitionKo', item->>'coreDefinitionKo',
        item->>'practicalContextKo', item->>'whyItMattersKo', item->>'exampleKo',
        public.glossary_text_array(item->'limitationsKo'),
        public.glossary_text_array(item->'sourceCodes'),
        public.glossary_text_array(item->'jurisdictions'),
        (item->>'asOfDate')::date, item->>'reviewStatus',
        public.glossary_text_array(item->'reviewFlags'),
        public.glossary_text_array(item->'relatedTermIds'),
        coalesce(item->>'formulaLatex', ''), coalesce(item->>'formulaNotesKo', ''),
        true, 1, '용어집 snapshot 적재', null, null
    from jsonb_array_elements(p_snapshot->'terms') as item
    on conflict (term_id) do update set
        category_id = excluded.category_id,
        display_order = excluded.display_order,
        canonical_name_en = excluded.canonical_name_en,
        canonical_name_ko = excluded.canonical_name_ko,
        aliases = excluded.aliases,
        concept_type = excluded.concept_type,
        one_line_definition_ko = excluded.one_line_definition_ko,
        core_definition_ko = excluded.core_definition_ko,
        practical_context_ko = excluded.practical_context_ko,
        why_it_matters_ko = excluded.why_it_matters_ko,
        example_ko = excluded.example_ko,
        limitations_ko = excluded.limitations_ko,
        source_codes = excluded.source_codes,
        jurisdictions = excluded.jurisdictions,
        as_of_date = excluded.as_of_date,
        review_status = excluded.review_status,
        review_flags = excluded.review_flags,
        related_term_ids = excluded.related_term_ids,
        formula_latex = excluded.formula_latex,
        formula_notes_ko = excluded.formula_notes_ko,
        is_active = true,
        content_revision = public.glossary_terms.content_revision + 1,
        change_reason = excluded.change_reason,
        archived_at = null,
        archived_by = null;

    insert into public.glossary_settings(setting_key, setting_value, updated_at) values
        ('inventory_sha256', p_snapshot->>'inventorySha256', clock_timestamp()),
        ('catalog_sha256', p_snapshot->>'catalogSha256', clock_timestamp()),
        ('generation_model', coalesce(p_snapshot->>'generationModel', 'codex-authoring-agent'), clock_timestamp())
    on conflict (setting_key) do update set
        setting_value = excluded.setting_value,
        updated_at = excluded.updated_at;

    queued := public.queue_glossary_compile('용어집 snapshot 적재', 1);
    return jsonb_build_object(
        'categories', category_count,
        'sources', source_count,
        'terms', term_count,
        'compile', queued
    );
end;
$$;

revoke all on function public.import_glossary_snapshot(jsonb) from public, anon, authenticated;
grant execute on function public.import_glossary_snapshot(jsonb) to service_role;
