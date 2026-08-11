begin;

-- Viewer accounts can explore the product structure in the web UI, but actual
-- authoring records and private Storage objects remain owner-only.
create or replace function public.is_admin()
returns boolean
language sql
stable
security definer
set search_path = ''
as $$
    select
        coalesce(auth.role(), '') = 'service_role'
        or exists (
            select 1
            from public.admin_users as admin
            where admin.user_id = auth.uid()
              and admin.is_active
              and admin.role = 'owner'::public.admin_role
        );
$$;

revoke all on function public.is_admin() from public, anon;
grant execute on function public.is_admin() to authenticated, service_role;

comment on function public.is_admin() is
    'Returns true only for the active owner or service role. Viewer accounts receive static catalog guidance instead of authoring data.';

commit;
