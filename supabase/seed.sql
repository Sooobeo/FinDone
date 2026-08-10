-- FinDone deliberately does not create Auth users or passwords from source control.
-- Create the local owner in Supabase Studio > Authentication > Users, then copy the
-- commented statement from seed.example.sql and replace the UUID before running it.
do $$
begin
    raise notice 'No FinDone admin seeded. Create an Auth user, then add its UUID to public.admin_users.';
end;
$$;

