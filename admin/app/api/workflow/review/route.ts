import { NextResponse } from "next/server";
import { getAdminCapabilities } from "@/lib/data";
import { getServerSupabase } from "@/lib/supabase/server";

const decisions = new Set(["approved", "rejected", "changes_requested"]);

export async function POST(request: Request) {
  const capabilities = await getAdminCapabilities();
  if (!capabilities.canReview) {
    return NextResponse.json({ error: "승인 검토 권한이 없습니다." }, { status: 403 });
  }
  const body = (await request.json()) as {
    revisionId?: string;
    decision?: "approved" | "rejected" | "changes_requested";
    comment?: string;
  };
  if (!body.revisionId || !body.decision || !decisions.has(body.decision)) {
    return NextResponse.json({ error: "검토 대상과 결정이 필요합니다." }, { status: 400 });
  }
  const comment = body.comment?.trim() ?? "";
  if (body.decision !== "approved" && !comment) {
    return NextResponse.json({ error: "반려 또는 수정 요청에는 검토 사유가 필요합니다." }, { status: 400 });
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
  if (revision.state !== "reviewed") {
    return NextResponse.json({ error: "자동 검증을 통과해 검토 대기 상태인 revision만 결정할 수 있습니다." }, { status: 409 });
  }

  const { data, error } = await supabase.rpc("submit_review", {
    p_revision_id: body.revisionId,
    p_decision: body.decision,
    p_comment: comment,
  });
  if (error) return NextResponse.json({ error: error.message }, { status: 400 });
  return NextResponse.json({ decisionId: data.review_decision_id, decision: data.decision });
}
