import { NextResponse } from "next/server";
import { getAdminCapabilities } from "@/lib/data";
import { isRequestUuid } from "@/lib/release-actions";
import { getServerSupabase } from "@/lib/supabase/server";

type GenerationAction = "queue_catalog" | "approve" | "reject";

const actions = new Set<GenerationAction>(["queue_catalog", "approve", "reject"]);

export async function POST(request: Request) {
  let rawBody: unknown;
  try {
    rawBody = await request.json();
  } catch {
    return NextResponse.json({ error: "올바른 JSON 요청이 아닙니다." }, { status: 400 });
  }
  if (!rawBody || typeof rawBody !== "object" || Array.isArray(rawBody)) {
    return NextResponse.json({ error: "요청 본문은 JSON 객체여야 합니다." }, { status: 400 });
  }
  const body = rawBody as {
    action?: GenerationAction;
    batchId?: string;
    requestKey?: string;
    comment?: string;
    refresh?: boolean;
  };
  if (!body.action || !actions.has(body.action)) {
    return NextResponse.json({ error: "원본 등록 또는 최종 검토 작업을 선택해 주세요." }, { status: 400 });
  }

  const capabilities = await getAdminCapabilities();
  if (body.action === "queue_catalog" && !capabilities.canEdit) {
    return NextResponse.json({ error: "원본 등록 권한이 없습니다." }, { status: 403 });
  }
  if (body.action === "approve" && (!capabilities.canReview || !capabilities.canRelease)) {
    return NextResponse.json({ error: "최종 승인과 릴리스 권한이 필요합니다." }, { status: 403 });
  }
  if (body.action === "reject" && !capabilities.canReview) {
    return NextResponse.json({ error: "최종 검토 권한이 없습니다." }, { status: 403 });
  }

  const supabase = await getServerSupabase();
  if (!supabase) return NextResponse.json({ error: "Supabase 연결이 없습니다." }, { status: 503 });

  if (body.action === "queue_catalog") {
    const { data, error } = await supabase.rpc("queue_catalog_url_sources", {
      p_source_ids: null,
      p_limit: 50,
      p_refresh: body.refresh === true,
    });
    if (error) return NextResponse.json({ error: error.message }, { status: 400 });
    const result = (Array.isArray(data) ? data[0] : data) as { queuedCount?: number } | null;
    const queuedCount = Number(result?.queuedCount ?? 0);
    return NextResponse.json({
      queuedCount,
      message: queuedCount
        ? `기존 웹 출처 ${queuedCount}건을 실제 수집 대기열에 등록했습니다.`
        : "새로 수집할 기존 웹 출처가 없습니다.",
    });
  }

  const batchId = body.batchId?.trim() ?? "";
  if (!isRequestUuid(batchId)) {
    return NextResponse.json({ error: "로컬 변환 배치 ID가 올바르지 않습니다." }, { status: 400 });
  }
  const { data: batch, error: batchError } = await supabase
    .from("content_generation_overview")
    .select("batch_id,status,release_id")
    .eq("batch_id", batchId)
    .maybeSingle();
  if (batchError || !batch) {
    return NextResponse.json({ error: batchError?.message ?? "로컬 변환 배치를 찾을 수 없습니다." }, { status: 404 });
  }

  if (body.action === "approve") {
    const requestKey = body.requestKey?.trim() ?? "";
    if (!isRequestUuid(requestKey)) {
      return NextResponse.json({ error: "최종 승인 요청 키가 올바르지 않습니다." }, { status: 400 });
    }
    if (batch.status !== "ready_for_review" && !batch.release_id) {
      return NextResponse.json({ error: "최종 검토 준비가 끝난 배치만 승인할 수 있습니다." }, { status: 409 });
    }
    const { data, error } = await supabase.rpc("approve_content_generation_batch", {
      p_batch_id: batchId,
      p_request_key: requestKey,
      p_comment: body.comment?.trim() ?? "",
    });
    if (error) return NextResponse.json({ error: error.message }, { status: 400 });
    const result = (Array.isArray(data) ? data[0] : data) as {
      releaseId?: string;
      contentVersion?: number;
      versionName?: string;
      status?: string;
    } | null;
    return NextResponse.json({
      ...result,
      message: "최종 승인을 기록했습니다. 클린 SQLite 생성·검증·stable 공개를 자동 진행합니다.",
    });
  }

  const comment = body.comment?.trim() ?? "";
  if (!comment) return NextResponse.json({ error: "반려 사유가 필요합니다." }, { status: 400 });
  const { data, error } = await supabase.rpc("reject_content_generation_batch", {
    p_batch_id: batchId,
    p_comment: comment,
  });
  if (error) return NextResponse.json({ error: error.message }, { status: 400 });
  return NextResponse.json({ status: data.status, message: "로컬 변환 배치를 반려했습니다. 운영 콘텐츠는 변경되지 않았습니다." });
}
