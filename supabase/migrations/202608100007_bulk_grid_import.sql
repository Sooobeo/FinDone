begin;

create or replace function public.save_content_grid_rows(
    p_rows jsonb,
    p_change_reason text default null
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
    row_value jsonb;
    result_rows jsonb := '[]'::jsonb;
    row_count integer;
begin
    if not public.has_admin_role(array['owner', 'editor']::public.admin_role[]) then
        raise exception using errcode = '42501', message = 'editor role required';
    end if;
    if jsonb_typeof(p_rows) <> 'array' then
        raise exception using errcode = '22023', message = 'rows must be a JSON array';
    end if;
    row_count := jsonb_array_length(p_rows);
    if row_count < 1 or row_count > 135 then
        raise exception using errcode = '22023', message = 'bulk grid import requires 1..135 rows';
    end if;
    if exists (
        select 1
        from jsonb_array_elements(p_rows) as row_item(value)
        where jsonb_typeof(row_item.value) <> 'object'
           or nullif(btrim(row_item.value ->> 'elementId'), '') is null
           or jsonb_typeof(coalesce(row_item.value -> 'elementPatch', '{}'::jsonb)) <> 'object'
           or jsonb_typeof(coalesce(row_item.value -> 'conceptPatch', '{}'::jsonb)) <> 'object'
           or jsonb_typeof(coalesce(row_item.value -> 'formulaPatch', '{}'::jsonb)) <> 'object'
    ) then
        raise exception using errcode = '22023', message = 'each row requires an elementId and object patches';
    end if;
    if (
        select count(distinct row_item.value ->> 'elementId')
        from jsonb_array_elements(p_rows) as row_item(value)
    ) <> row_count then
        raise exception using errcode = '22023', message = 'bulk grid import contains duplicate element IDs';
    end if;

    for row_value in select value from jsonb_array_elements(p_rows) loop
        result_rows := result_rows || jsonb_build_array(
            public.save_content_grid_row(
                row_value ->> 'elementId',
                coalesce(row_value -> 'elementPatch', '{}'::jsonb),
                coalesce(row_value -> 'conceptPatch', '{}'::jsonb),
                coalesce(row_value -> 'formulaPatch', '{}'::jsonb),
                p_change_reason
            )
        );
    end loop;

    return jsonb_build_object('saved', row_count, 'rows', result_rows);
end;
$$;

revoke all on function public.save_content_grid_rows(jsonb, text) from public;
grant execute on function public.save_content_grid_rows(jsonb, text) to authenticated, service_role;

commit;
