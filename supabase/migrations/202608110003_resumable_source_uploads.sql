begin;

-- Original source files inherit the project's global Storage limit. The
-- previous 100 MiB bucket cap prevented resumable uploads from accepting
-- larger files even when the hosted project allowed them.
update storage.buckets
set file_size_limit = null
where id = 'source-private';

create or replace function public.register_file_source(
    p_source_id text,
    p_source_version_id uuid,
    p_label text,
    p_object_path text,
    p_original_filename text,
    p_mime_type text,
    p_byte_size bigint,
    p_sha256 text
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
    job_id_value uuid;
begin
    if not public.has_admin_role(array['owner', 'editor']::public.admin_role[]) then
        raise exception using errcode = '42501', message = 'editor role required';
    end if;
    if auth.uid() is null or split_part(p_object_path, '/', 1) <> auth.uid()::text then
        raise exception using errcode = '42501', message = 'storage object must belong to the current admin';
    end if;
    if p_byte_size < 1
       or p_sha256 !~ '^[0-9a-f]{64}$'
       or nullif(btrim(p_original_filename), '') is null then
        raise exception using errcode = '22023', message = 'invalid source file metadata';
    end if;
    if not exists (
        select 1
        from storage.objects as object
        where object.bucket_id = 'source-private'
          and object.name = p_object_path
          and nullif(object.metadata ->> 'size', '')::bigint = p_byte_size
    ) then
        raise exception using errcode = 'P0002', message = 'uploaded storage object not found or size mismatch';
    end if;
    insert into public.sources (
        source_id, kind, label, locator, source_type, created_by
    ) values (
        p_source_id, 'file', p_label, p_object_path, coalesce(p_mime_type, 'application/octet-stream'), auth.uid()
    );
    insert into public.source_versions (
        source_version_id, source_id, version_number, original_filename,
        mime_type, byte_size, sha256, parse_status, created_by
    ) values (
        p_source_version_id, p_source_id, 1, p_original_filename,
        p_mime_type, p_byte_size, p_sha256, 'pending', auth.uid()
    );
    insert into public.source_files (
        source_version_id, file_role, object_path, original_filename,
        mime_type, byte_size, sha256, created_by
    ) values (
        p_source_version_id, 'original', p_object_path, p_original_filename,
        p_mime_type, p_byte_size, p_sha256, auth.uid()
    );
    insert into public.ingestion_jobs (
        job_kind, source_version_id, input, created_by
    ) values (
        'file_extract',
        p_source_version_id,
        jsonb_build_object('objectPath', p_object_path, 'originalFilename', p_original_filename),
        auth.uid()
    ) returning job_id into job_id_value;
    return jsonb_build_object('sourceVersionId', p_source_version_id, 'jobId', job_id_value);
end;
$$;

revoke all on function public.register_file_source(text, uuid, text, text, text, text, bigint, text) from public;
grant execute on function public.register_file_source(text, uuid, text, text, text, text, bigint, text) to authenticated;

commit;
