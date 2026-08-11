begin;

alter type public.admin_role add value if not exists 'viewer';

commit;

begin;

-- FinDone now has two effective permission levels: one owner and read-only viewers.
-- Legacy role values stay in the enum for migration compatibility, but no longer
-- receive write capabilities through has_admin_role().
update public.admin_users
set role = 'viewer'::public.admin_role
where role <> 'owner'::public.admin_role;

create or replace function public.has_admin_role(p_roles public.admin_role[])
returns boolean
language sql
stable
security definer
set search_path = ''
as $$
    select
        coalesce(auth.role(), '') = 'service_role'
        or (
            'owner'::public.admin_role = any (p_roles)
            and exists (
                select 1
                from public.admin_users as admin
                where admin.user_id = auth.uid()
                  and admin.is_active
                  and admin.role = 'owner'::public.admin_role
            )
        );
$$;

create or replace function public.provision_viewer_membership()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
declare
    viewer_name text;
begin
    viewer_name := left(
        coalesce(
            nullif(new.raw_user_meta_data ->> 'display_name', ''),
            nullif(new.raw_user_meta_data ->> 'full_name', ''),
            nullif(split_part(coalesce(new.email, ''), '@', 1), ''),
            'Viewer'
        ),
        120
    );

    insert into public.admin_users (user_id, role, display_name, is_active)
    values (new.id, 'viewer'::public.admin_role, viewer_name, true)
    on conflict (user_id) do nothing;

    return new;
end;
$$;

revoke all on function public.provision_viewer_membership() from public, anon, authenticated;

drop trigger if exists findone_provision_viewer on auth.users;
create trigger findone_provision_viewer
after insert on auth.users
for each row execute function public.provision_viewer_membership();

-- Existing Auth accounts that are not already the owner become viewers as well.
insert into public.admin_users (user_id, role, display_name, is_active)
select
    account.id,
    'viewer'::public.admin_role,
    left(
        coalesce(
            nullif(account.raw_user_meta_data ->> 'display_name', ''),
            nullif(account.raw_user_meta_data ->> 'full_name', ''),
            nullif(split_part(coalesce(account.email, ''), '@', 1), ''),
            'Viewer'
        ),
        120
    ),
    true
from auth.users as account
on conflict (user_id) do nothing;

drop policy if exists admin_users_admin_select on public.admin_users;
create policy admin_users_member_select
on public.admin_users for select to authenticated
using (
    user_id = auth.uid()
    or (select public.has_admin_role(array['owner']::public.admin_role[]))
);

-- Viewer may read private source metadata/files but can never create, replace,
-- or delete a Storage object. All three write policies are owner-only.
drop policy if exists findone_admin_object_insert on storage.objects;
create policy findone_admin_object_insert
on storage.objects for insert to authenticated
with check (
    (storage.foldername(name))[1] = auth.uid()::text
    and bucket_id in ('source-private', 'exports-private', 'release-bundles')
    and (select public.has_admin_role(array['owner']::public.admin_role[]))
);

drop policy if exists findone_admin_object_update on storage.objects;
create policy findone_admin_object_update
on storage.objects for update to authenticated
using (
    (storage.foldername(name))[1] = auth.uid()::text
    and bucket_id in ('source-private', 'exports-private', 'release-bundles')
    and (select public.has_admin_role(array['owner']::public.admin_role[]))
)
with check (
    (storage.foldername(name))[1] = auth.uid()::text
    and bucket_id in ('source-private', 'exports-private', 'release-bundles')
    and (select public.has_admin_role(array['owner']::public.admin_role[]))
);

drop policy if exists findone_admin_object_delete on storage.objects;
create policy findone_admin_object_delete
on storage.objects for delete to authenticated
using (
    (storage.foldername(name))[1] = auth.uid()::text
    and bucket_id in ('source-private', 'exports-private', 'release-bundles')
    and (select public.has_admin_role(array['owner']::public.admin_role[]))
);

comment on table public.admin_users is
    'Owner and read-only viewer memberships. New Auth accounts are provisioned as viewer only.';
comment on function public.provision_viewer_membership() is
    'Creates an immutable-default read-only viewer membership for every new Auth account.';

commit;
