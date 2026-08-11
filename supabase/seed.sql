-- FinDone deliberately does not create Auth users or passwords from source control.
-- New Auth accounts are provisioned as viewers. Promote exactly one trusted UUID
-- to owner with the statement in seed.example.sql.
do $$
begin
    raise notice 'No FinDone owner seeded. New Auth users become viewers; promote exactly one trusted UUID to owner.';
end;
$$;
