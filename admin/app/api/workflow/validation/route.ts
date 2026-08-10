import { NextResponse } from "next/server";
import { getAdminCapabilities } from "@/lib/data";
import { getServerSupabase } from "@/lib/supabase/server";

export async function POST(request: Request) {
  const capabilities = await getAdminCapabilities();
  if (!capabilities.canValidateRevision) {
    return NextResponse.json({ error: "revision 검증을 요청할 권한이 없습니다." }, { status: 403 });
  }

  const body = (await request.json()) as { revisionId?: string };
  if (!body.revisionId) {
    return NextResponse.json({ error: "revision ID가 필요합니다." }, { status: 400 });
  }
  const supabase = await getServerSupabase();
  if (!supabase) return NextResponse.json({ error: "Supabase 연결이 없습니다." }, { status: 503 });

  const { data: revision, error: revisionError } = await supabase
    .from("content_revision_status")
    .select("revision_id,state")
    .eq("revision_id", body.revisionId)
    .maybeSingle();
  if (revisionError || !revision) {
    return NextResponse.json({ error: revisionError?.message ?? "revision을 찾을 수 없습니다." }, { status: 404 });
  }
  if (revision.state !== "draft" && revision.state !== "validation_failed") {
    return NextResponse.json({ error: "초안 또는 검증 실패 revision만 다시 검증할 수 있습니다." }, { status: 409 });
  }

  const { data, error } = await supabase.rpc("start_revision_validation", {
    p_revision_id: body.revisionId,
    p_validator_name: "findone-content-validator",
    p_validator_version: "admin-v1",
  });
  if (error) return NextResponse.json({ error: error.message }, { status: 400 });

  return NextResponse.json({
    validationRunId: data.validation_run_id,
    status: data.status,
    message: "검증 작업을 대기열에 등록했습니다.",
  });
}
