begin;

create type public.revision_operation as enum ('insert', 'update', 'delete');
create type public.revision_state as enum (
    'draft',
    'validating',
    'validation_failed',
    'reviewed',
    'approved',
    'rejected',
    'published',
    'archived'
);
create type public.validation_target_type as enum ('revision', 'release', 'system');
create type public.validation_status as enum (
    'queued',
    'running',
    'passed',
    'failed',
    'cancelled'
);
create type public.validation_severity as enum ('info', 'warning', 'error');
create type public.review_decision_type as enum (
    'approved',
    'rejected',
    'changes_requested'
);

create table public.content_revisions (
    revision_id uuid primary key default gen_random_uuid(),
    entity_type public.content_entity_type not null,
    entity_key text not null,
    revision_number integer not null check (revision_number > 0),
    operation public.revision_operation not null,
    snapshot jsonb not null,
    content_hash text not null,
    change_reason text,
    created_at timestamptz not null default clock_timestamp(),
    created_by uuid references auth.users(id) on delete set null,
    constraint content_revisions_entity_key_not_blank check (btrim(entity_key) <> ''),
    constraint content_revisions_snapshot_object check (jsonb_typeof(snapshot) = 'object'),
    constraint content_revisions_hash_format check (content_hash ~ '^[0-9a-f]{64}$'),
    constraint content_revisions_entity_number_unique unique (
        entity_type,
        entity_key,
        revision_number
    )
);

create table public.revision_state_events (
    revision_state_event_id bigint generated always as identity primary key,
    revision_id uuid not null references public.content_revisions(revision_id) on delete restrict,
    state public.revision_state not null,
    note text,
    created_at timestamptz not null default clock_timestamp(),
    created_by uuid references auth.users(id) on delete set null
);

create table public.validation_runs (
    validation_run_id uuid primary key default gen_random_uuid(),
    target_type public.validation_target_type not null,
    revision_id uuid references public.content_revisions(revision_id) on delete restrict,
    release_id uuid,
    status public.validation_status not null default 'queued',
    validator_name text not null,
    validator_version text not null default '',
    checks_total integer not null default 0 check (checks_total >= 0),
    checks_passed integer not null default 0 check (checks_passed >= 0),
    checks_failed integer not null default 0 check (checks_failed >= 0),
    summary jsonb not null default '{}'::jsonb,
    started_at timestamptz,
    completed_at timestamptz,
    created_at timestamptz not null default clock_timestamp(),
    created_by uuid references auth.users(id) on delete set null,
    updated_at timestamptz not null default clock_timestamp(),
    updated_by uuid references auth.users(id) on delete set null,
    constraint validation_runs_validator_not_blank check (btrim(validator_name) <> ''),
    constraint validation_runs_summary_object check (jsonb_typeof(summary) = 'object'),
    constraint validation_runs_count_consistency check (
        checks_passed + checks_failed <= checks_total
    ),
    constraint validation_runs_target_shape check (
        (target_type = 'revision' and revision_id is not null and release_id is null)
        or (target_type = 'release' and revision_id is null and release_id is not null)
        or (target_type = 'system' and revision_id is null and release_id is null)
    )
);

create table public.validation_issues (
    validation_issue_id uuid primary key default gen_random_uuid(),
    validation_run_id uuid not null references public.validation_runs(validation_run_id) on delete restrict,
    severity public.validation_severity not null,
    code text not null,
    field_path text,
    message text not null,
    details jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default clock_timestamp(),
    created_by uuid references auth.users(id) on delete set null,
    constraint validation_issues_code_not_blank check (btrim(code) <> ''),
    constraint validation_issues_message_not_blank check (btrim(message) <> ''),
    constraint validation_issues_details_object check (jsonb_typeof(details) = 'object')
);

create table public.review_decisions (
    review_decision_id uuid primary key default gen_random_uuid(),
    revision_id uuid not null references public.content_revisions(revision_id) on delete restrict,
    decision public.review_decision_type not null,
    comment text not null default '',
    reviewer_id uuid not null references auth.users(id) on delete restrict,
    decided_at timestamptz not null default clock_timestamp()
);

create table public.approval_snapshots (
    approval_snapshot_id uuid primary key default gen_random_uuid(),
    revision_id uuid not null references public.content_revisions(revision_id) on delete restrict,
    review_decision_id uuid not null unique references public.review_decisions(review_decision_id) on delete restrict,
    entity_type public.content_entity_type not null,
    entity_key text not null,
    revision_number integer not null,
    content_hash text not null,
    snapshot jsonb not null,
    approved_at timestamptz not null,
    approved_by uuid not null references auth.users(id) on delete restrict,
    constraint approval_snapshots_hash_format check (content_hash ~ '^[0-9a-f]{64}$'),
    constraint approval_snapshots_snapshot_object check (jsonb_typeof(snapshot) = 'object')
);

create index content_revisions_entity_created_idx
    on public.content_revisions(entity_type, entity_key, revision_number desc);
create index revision_state_events_revision_idx
    on public.revision_state_events(revision_id, revision_state_event_id desc);
create index validation_runs_revision_idx
    on public.validation_runs(revision_id, created_at desc)
    where revision_id is not null;
create index validation_runs_release_idx
    on public.validation_runs(release_id, created_at desc)
    where release_id is not null;
create index validation_issues_run_severity_idx
    on public.validation_issues(validation_run_id, severity);
create index review_decisions_revision_idx
    on public.review_decisions(revision_id, decided_at desc);

create or replace function public.current_revision_state(p_revision_id uuid)
returns public.revision_state
language sql
stable
security definer
set search_path = ''
as $$
    select event.state
    from public.revision_state_events as event
    where event.revision_id = p_revision_id
    order by event.revision_state_event_id desc
    limit 1;
$$;

create or replace function public.validate_revision_state_transition()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
declare
    previous_state public.revision_state;
    revision_row public.content_revisions%rowtype;
begin
    perform pg_advisory_xact_lock(hashtextextended('revision-state:' || new.revision_id::text, 0));

    select * into revision_row
    from public.content_revisions
    where revision_id = new.revision_id;

    select event.state into previous_state
    from public.revision_state_events as event
    where event.revision_id = new.revision_id
    order by event.revision_state_event_id desc
    limit 1;

    if previous_state is null then
        if new.state <> 'draft' then
            raise exception using
                errcode = '23514',
                message = 'the first revision state must be draft';
        end if;
        return new;
    end if;

    if previous_state = new.state then
        raise exception using errcode = '23514', message = 'duplicate revision state';
    end if;

    if not (
        (previous_state = 'draft' and new.state in ('validating', 'archived'))
        or (previous_state = 'validating' and new.state in ('validation_failed', 'reviewed', 'rejected', 'archived'))
        or (previous_state = 'validation_failed' and new.state in ('validating', 'rejected', 'archived'))
        or (previous_state = 'reviewed' and new.state in ('approved', 'rejected', 'archived'))
        or (previous_state = 'approved' and new.state in ('published', 'archived'))
        or (previous_state = 'rejected' and new.state = 'archived')
        or (previous_state = 'published' and new.state = 'archived')
    ) then
        raise exception using
            errcode = '23514',
            message = format('invalid revision transition: %s -> %s', previous_state, new.state);
    end if;

    if new.state in ('reviewed', 'approved', 'published') and exists (
        select 1
        from public.content_revisions as newer
        where newer.entity_type = revision_row.entity_type
          and newer.entity_key = revision_row.entity_key
          and newer.revision_number > revision_row.revision_number
    ) then
        raise exception using
            errcode = '23514',
            message = 'an obsolete revision cannot be reviewed, approved, or published';
    end if;

    if new.state in ('reviewed', 'approved') and not exists (
        select 1
        from public.validation_runs as run
        where run.revision_id = new.revision_id
          and run.status = 'passed'
    ) then
        raise exception using
            errcode = '23514',
            message = 'successful validation is required before review or approval';
    end if;

    if new.state = 'approved' and not exists (
        select 1
        from public.review_decisions as decision
        where decision.revision_id = new.revision_id
          and decision.decision = 'approved'
    ) then
        raise exception using
            errcode = '23514',
            message = 'an approval decision is required before approval state';
    end if;

    new.created_by := coalesce(new.created_by, auth.uid());
    new.created_at := coalesce(new.created_at, clock_timestamp());
    return new;
end;
$$;

create or replace function public.record_content_revision()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
declare
    entity_type_value public.content_entity_type := tg_argv[0]::public.content_entity_type;
    entity_key_value text;
    revision_number_value integer;
    revision_id_value uuid;
    snapshot_value jsonb;
    operation_value public.revision_operation;
    change_reason_value text;
begin
    if tg_op = 'DELETE' then
        snapshot_value := to_jsonb(old);
        operation_value := 'delete';
    else
        snapshot_value := to_jsonb(new);
        operation_value := lower(tg_op)::public.revision_operation;
    end if;

    entity_key_value := snapshot_value ->> tg_argv[1];
    if nullif(btrim(entity_key_value), '') is null then
        raise exception using errcode = '23514', message = 'revision entity key cannot be blank';
    end if;

    perform pg_advisory_xact_lock(
        hashtextextended(entity_type_value::text || ':' || entity_key_value, 0)
    );

    select coalesce(max(revision_number), 0) + 1
    into revision_number_value
    from public.content_revisions
    where entity_type = entity_type_value
      and entity_key = entity_key_value;

    change_reason_value := nullif(current_setting('app.change_reason', true), '');

    insert into public.content_revisions (
        entity_type,
        entity_key,
        revision_number,
        operation,
        snapshot,
        content_hash,
        change_reason,
        created_by
    ) values (
        entity_type_value,
        entity_key_value,
        revision_number_value,
        operation_value,
        snapshot_value,
        encode(extensions.digest(convert_to(snapshot_value::text, 'UTF8'), 'sha256'), 'hex'),
        change_reason_value,
        auth.uid()
    ) returning revision_id into revision_id_value;

    insert into public.revision_state_events (revision_id, state, note, created_by)
    values (revision_id_value, 'draft', change_reason_value, auth.uid());

    if tg_op = 'DELETE' then
        return old;
    end if;
    return new;
end;
$$;

create or replace function public.enforce_validation_run()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
    if tg_op = 'UPDATE' and (
        new.validation_run_id <> old.validation_run_id
        or new.target_type <> old.target_type
        or new.revision_id is distinct from old.revision_id
        or new.release_id is distinct from old.release_id
        or new.validator_name <> old.validator_name
        or new.validator_version <> old.validator_version
    ) then
        raise exception using errcode = '55000', message = 'validation target and validator are immutable';
    end if;

    if new.status = 'running' and new.started_at is null then
        new.started_at := clock_timestamp();
    end if;
    if new.status in ('passed', 'failed', 'cancelled') and new.completed_at is null then
        new.completed_at := clock_timestamp();
    end if;

    if new.status = 'passed' and exists (
        select 1
        from public.validation_issues as issue
        where issue.validation_run_id = new.validation_run_id
          and issue.severity = 'error'
    ) then
        raise exception using
            errcode = '23514',
            message = 'validation with error issues cannot pass';
    end if;
    return new;
end;
$$;

create or replace function public.sync_validation_revision_state()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
declare
    current_state public.revision_state;
begin
    if new.target_type <> 'revision' then
        return new;
    end if;

    current_state := public.current_revision_state(new.revision_id);
    if new.status in ('queued', 'running') and current_state in ('draft', 'validation_failed') then
        insert into public.revision_state_events (revision_id, state, note, created_by)
        values (new.revision_id, 'validating', 'validation started', auth.uid());
    elsif new.status = 'failed' and current_state = 'validating' then
        insert into public.revision_state_events (revision_id, state, note, created_by)
        values (new.revision_id, 'validation_failed', 'validation failed', auth.uid());
    end if;
    return new;
end;
$$;

create or replace function public.enforce_review_decision()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
    if not public.has_admin_role(array['owner', 'reviewer']::public.admin_role[]) then
        raise exception using errcode = '42501', message = 'reviewer role required';
    end if;

    new.reviewer_id := coalesce(auth.uid(), new.reviewer_id);
    if new.reviewer_id is null then
        raise exception using errcode = '23502', message = 'reviewer_id is required';
    end if;

    if new.decision = 'approved' and not exists (
        select 1
        from public.validation_runs
        where revision_id = new.revision_id and status = 'passed'
    ) then
        raise exception using errcode = '23514', message = 'successful validation is required';
    end if;
    return new;
end;
$$;

create or replace function public.apply_review_decision()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
declare
    current_state public.revision_state;
    revision_row public.content_revisions%rowtype;
begin
    current_state := public.current_revision_state(new.revision_id);

    if new.decision = 'approved' then
        if current_state = 'validating' then
            insert into public.revision_state_events (revision_id, state, note, created_by)
            values (new.revision_id, 'reviewed', new.comment, new.reviewer_id);
        end if;
        insert into public.revision_state_events (revision_id, state, note, created_by)
        values (new.revision_id, 'approved', new.comment, new.reviewer_id);

        select * into revision_row
        from public.content_revisions
        where revision_id = new.revision_id;

        insert into public.approval_snapshots (
            revision_id,
            review_decision_id,
            entity_type,
            entity_key,
            revision_number,
            content_hash,
            snapshot,
            approved_at,
            approved_by
        ) values (
            revision_row.revision_id,
            new.review_decision_id,
            revision_row.entity_type,
            revision_row.entity_key,
            revision_row.revision_number,
            revision_row.content_hash,
            revision_row.snapshot,
            new.decided_at,
            new.reviewer_id
        );
    else
        insert into public.revision_state_events (revision_id, state, note, created_by)
        values (new.revision_id, 'rejected', new.comment, new.reviewer_id);
    end if;
    return new;
end;
$$;

create or replace function public.submit_review(
    p_revision_id uuid,
    p_decision public.review_decision_type,
    p_comment text default ''
)
returns public.review_decisions
language plpgsql
security definer
set search_path = ''
as $$
declare
    result public.review_decisions%rowtype;
begin
    if not public.has_admin_role(array['owner', 'reviewer']::public.admin_role[]) then
        raise exception using errcode = '42501', message = 'reviewer role required';
    end if;

    insert into public.review_decisions (revision_id, decision, comment, reviewer_id)
    values (p_revision_id, p_decision, coalesce(p_comment, ''), auth.uid())
    returning * into result;
    return result;
end;
$$;

create trigger revision_state_events_validate_transition
before insert on public.revision_state_events
for each row execute function public.validate_revision_state_transition();

create trigger content_revisions_append_only
before update or delete on public.content_revisions
for each row execute function public.prevent_row_mutation();
create trigger revision_state_events_append_only
before update or delete on public.revision_state_events
for each row execute function public.prevent_row_mutation();
create trigger validation_issues_append_only
before update or delete on public.validation_issues
for each row execute function public.prevent_row_mutation();
create trigger review_decisions_append_only
before update or delete on public.review_decisions
for each row execute function public.prevent_row_mutation();
create trigger approval_snapshots_append_only
before update or delete on public.approval_snapshots
for each row execute function public.prevent_row_mutation();

create trigger validation_runs_set_audit_columns
before insert or update on public.validation_runs
for each row execute function public.set_audit_columns();
create trigger validation_runs_enforce
before insert or update on public.validation_runs
for each row execute function public.enforce_validation_run();
create trigger validation_runs_sync_revision_state
after insert or update of status on public.validation_runs
for each row execute function public.sync_validation_revision_state();

create trigger review_decisions_enforce
before insert on public.review_decisions
for each row execute function public.enforce_review_decision();
create trigger review_decisions_apply
after insert on public.review_decisions
for each row execute function public.apply_review_decision();

create trigger domains_record_revision
after insert or update or delete on public.domains
for each row execute function public.record_content_revision('domain', 'domain_id');
create trigger elements_record_revision
after insert or update or delete on public.elements
for each row execute function public.record_content_revision('element', 'element_id');
create trigger concepts_record_revision
after insert or update or delete on public.concepts
for each row execute function public.record_content_revision('concept', 'concept_id');
create trigger formulas_record_revision
after insert or update or delete on public.formulas
for each row execute function public.record_content_revision('formula', 'formula_id');
create trigger distractors_record_revision
after insert or update or delete on public.distractors
for each row execute function public.record_content_revision('distractor', 'distractor_id');

revoke all on function public.current_revision_state(uuid) from public;
revoke all on function public.validate_revision_state_transition() from public;
revoke all on function public.record_content_revision() from public;
revoke all on function public.enforce_validation_run() from public;
revoke all on function public.sync_validation_revision_state() from public;
revoke all on function public.enforce_review_decision() from public;
revoke all on function public.apply_review_decision() from public;
revoke all on function public.submit_review(uuid, public.review_decision_type, text) from public;

grant execute on function public.current_revision_state(uuid) to authenticated, service_role;

commit;
