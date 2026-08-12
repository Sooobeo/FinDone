import { NextResponse } from "next/server";
import { getAdminContext } from "@/lib/auth";
import { conceptModelExperiments } from "@/lib/concept-model-report";
import { getAdminCapabilities } from "@/lib/data";
import { getServerSupabase } from "@/lib/supabase/server";

export const runtime = "nodejs";

const decisions = new Set(["approved", "rejected"]);
const fingerprintPattern = /^[0-9a-f]{64}$/u;

export async function POST(request: Request) {
  const [context, capabilities] = await Promise.all([getAdminContext(), getAdminCapabilities()]);
  if (!context.user || !capabilities.canReview) {
    return NextResponse.json({ error: "개념형 문항 검수 권한이 없습니다." }, { status: 403 });
  }

  let body: {
    questionId?: unknown;
    questionFingerprint?: unknown;
    decision?: unknown;
    comment?: unknown;
  };
  try {
    const value = await request.json() as unknown;
    if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error("invalid body");
    body = value;
  } catch {
    return NextResponse.json({ error: "올바른 JSON 요청이 아닙니다." }, { status: 400 });
  }

  const questionId = typeof body.questionId === "string" ? body.questionId.trim() : "";
  const questionFingerprint = typeof body.questionFingerprint === "string"
    ? body.questionFingerprint.trim()
    : "";
  const decision = body.decision;
  const comment = typeof body.comment === "string" ? body.comment.trim() : "";
  if (!questionId || questionId.length > 160 || !fingerprintPattern.test(questionFingerprint)) {
    return NextResponse.json({ error: "검수 대상 문항 정보가 올바르지 않습니다." }, { status: 400 });
  }
  if (typeof decision !== "string" || !decisions.has(decision)) {
    return NextResponse.json({ error: "승인 또는 반려 결정을 선택해 주세요." }, { status: 400 });
  }
  if (comment.length > 2000) {
    return NextResponse.json({ error: "검수 메모는 2,000자 이하여야 합니다." }, { status: 400 });
  }
  if (decision === "rejected" && !comment) {
    return NextResponse.json({ error: "반려 사유를 입력해 주세요." }, { status: 400 });
  }

  const latest = conceptModelExperiments.experiments[0];
  const item = latest?.automatedReview.queue.find((candidate) => candidate.questionId === questionId);
  if (!item) {
    return NextResponse.json({ error: "현재 검수 대기열에 없는 문항입니다. 화면을 새로고침해 주세요." }, { status: 409 });
  }
  if (item.questionFingerprint !== questionFingerprint) {
    return NextResponse.json({ error: "문항이 변경되었습니다. 새로고침 후 다시 검수해 주세요." }, { status: 409 });
  }
  if (item.severity === "block" && decision === "approved") {
    return NextResponse.json({ error: "자동 차단 문항은 수정 전 승인할 수 없습니다." }, { status: 409 });
  }

  const supabase = await getServerSupabase();
  if (!supabase) return NextResponse.json({ error: "Supabase 연결이 없습니다." }, { status: 503 });
  const { data, error } = await supabase.rpc("submit_concept_question_review", {
    p_review_input_sha256: latest.automatedReview.reviewInputSha256,
    p_question_id: questionId,
    p_question_fingerprint: questionFingerprint,
    p_decision: decision,
    p_comment: comment,
  });
  if (error) return NextResponse.json({ error: error.message }, { status: 400 });
  const saved = Array.isArray(data) ? data[0] : data;
  return NextResponse.json({
    decisionId: saved?.concept_question_review_decision_id,
    questionId,
    decision,
    comment,
    rerunRequired: true,
    message: decision === "approved"
      ? "승인 결정을 저장했습니다. 다음 모델 실행에서 반영됩니다."
      : "반려 결정을 저장했습니다. 다음 모델 실행에서 문항이 차단됩니다.",
  });
}
