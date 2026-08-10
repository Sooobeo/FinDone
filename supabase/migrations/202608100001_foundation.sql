begin;

create schema if not exists extensions;
create extension if not exists pgcrypto with schema extensions;

create type public.admin_role as enum (
    'owner',
    'editor',
    'reviewer',
    'releaser'
);

create table public.admin_users (
    user_id uuid primary key references auth.users(id) on delete cascade,
    role public.admin_role not null default 'editor',
    display_name text not null default '',
    is_active boolean not null default true,
    created_at timestamptz not null default clock_timestamp(),
    created_by uuid references auth.users(id) on delete set null,
    updated_at timestamptz not null default clock_timestamp(),
    updated_by uuid references auth.users(id) on delete set null,
    constraint admin_users_display_name_length check (length(display_name) <= 120)
);

comment on table public.admin_users is
    'Closed allowlist for pre-created Supabase Auth accounts. Auth existence alone never grants admin access.';

create or replace function public.is_admin()
returns boolean
language sql
stable
security definer
set search_path = ''
as $$
    select exists (
        select 1
        from public.admin_users as admin
        where admin.user_id = auth.uid()
          and admin.is_active
    );
$$;

create or replace function public.has_admin_role(p_roles public.admin_role[])
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
              and admin.role = any (p_roles)
        );
$$;

create or replace function public.set_audit_columns()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
    if tg_op = 'INSERT' then
        new.created_at := coalesce(new.created_at, clock_timestamp());
        new.created_by := coalesce(new.created_by, auth.uid());
    end if;

    new.updated_at := clock_timestamp();
    new.updated_by := auth.uid();
    return new;
end;
$$;

create or replace function public.prevent_column_update()
returns trigger
language plpgsql
set search_path = ''
as $$
declare
    column_name text;
begin
    foreach column_name in array tg_argv loop
        if (to_jsonb(new) -> column_name) is distinct from (to_jsonb(old) -> column_name) then
            raise exception using
                errcode = '55000',
                message = format('%I.%I is immutable', tg_table_name, column_name);
        end if;
    end loop;
    return new;
end;
$$;

create or replace function public.prevent_row_mutation()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
    raise exception using
        errcode = '55000',
        message = format('%I is append-only', tg_table_name);
end;
$$;

create or replace function public.protect_admin_allowlist()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
declare
    removing_last_owner boolean := false;
begin
    if tg_op = 'DELETE' then
        removing_last_owner := old.is_active and old.role = 'owner';
    elsif old.is_active and old.role = 'owner' then
        removing_last_owner := not new.is_active or new.role <> 'owner';
    end if;

    if removing_last_owner and (
        select count(*)
        from public.admin_users
        where is_active and role = 'owner'
    ) <= 1 then
        raise exception using
            errcode = '23514',
            message = 'the final active owner cannot be removed or demoted';
    end if;

    if tg_op = 'DELETE' then
        return old;
    end if;
    return new;
end;
$$;

create trigger admin_users_set_audit_columns
before insert or update on public.admin_users
for each row execute function public.set_audit_columns();

create trigger admin_users_immutable_user_id
before update on public.admin_users
for each row execute function public.prevent_column_update('user_id');

create trigger admin_users_protect_owner
before update or delete on public.admin_users
for each row execute function public.protect_admin_allowlist();

revoke all on function public.is_admin() from public;
revoke all on function public.has_admin_role(public.admin_role[]) from public;
revoke all on function public.set_audit_columns() from public;
revoke all on function public.prevent_column_update() from public;
revoke all on function public.prevent_row_mutation() from public;
revoke all on function public.protect_admin_allowlist() from public;

grant execute on function public.is_admin() to authenticated, service_role;
grant execute on function public.has_admin_role(public.admin_role[]) to authenticated, service_role;

commit;
