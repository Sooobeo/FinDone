import { NextResponse } from "next/server";
import { getAdminContext } from "@/lib/auth";
import { conceptModelExperiments } from "@/lib/concept-model-report";
import { getAdminCapabilities } from "@/lib/data";
import { getServerSupabase } from "@/lib/supabase/server";

export const runtime = "nodejs";

const fingerprintPattern = /^[0-9a-f]{64}$/u;
const questionIdPattern = /^[A-Za-z0-9_-]+$/u;
const elementIdPattern = /^[A-Za-z0-9_-]+$/u;
const choiceKeys = ["A", "B", "C", "D", "E"] as const;

type EditableChoice = {
  key: string;
  elementId: string;
  text: string;
  explanation: string;
  isCorrect: boolean;
};

function parseChoices(value: unknown, targetElementId: string): EditableChoice[] | null {
  if (!Array.isArray(value) || value.length !== choiceKeys.length) return null;
  const choices: EditableChoice[] = [];
  for (const [index, raw] of value.entries()) {
    if (!raw || typeof raw !== "object" || Array.isArray(raw)) return null;
    const choice = raw as Record<string, unknown>;
    const key = typeof choice.key === "string" ? choice.key.trim() : "";
    const elementId = typeof choice.elementId === "string" ? choice.elementId.trim() : "";
    const text = typeof choice.text === "string" ? choice.text.trim() : "";
    const explanation = typeof choice.explanation === "string" ? choice.explanation.trim() : "";
    const isCorrect = choice.isCorrect;
    if (
      key !== choiceKeys[index]
      || !elementIdPattern.test(elementId)
      || elementId.length > 80
      || !text
      || text.length > 2000
      || !explanation
      || explanation.length > 2000
      || typeof isCorrect !== "boolean"
    ) return null;
    choices.push({ key, elementId, text, explanation, isCorrect });
  }
  if (choices.filter((choice) => choice.isCorrect).length !== 1) return null;
  if (choices.find((choice) => choice.isCorrect)?.elementId !== targetElementId) return null;
  if (new Set(choices.map((choice) => choice.key)).size !== choiceKeys.length) return null;
  return choices;
}

export async function POST(request: Request) {
  const [context, capabilities] = await Promise.all([getAdminContext(), getAdminCapabilities()]);
  if (!context.user || !capabilities.canEdit) {
    return NextResponse.json({ error: "문항 수정 권한이 없습니다." }, { status: 403 });
  }

  let body: Record<string, unknown>;
  try {
    const value = await request.json() as unknown;
    if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error("invalid body");
    body = value as Record<string, unknown>;
  } catch {
    return NextResponse.json({ error: "올바른 JSON 요청이 아닙니다." }, { status: 400 });
  }

  const questionId = typeof body.questionId === "string" ? body.questionId.trim() : "";
  const questionFingerprint = typeof body.questionFingerprint === "string"
    ? body.questionFingerprint.trim()
    : "";
  const stem = typeof body.stem === "string" ? body.stem.trim() : "";
  const explanation = typeof body.explanation === "string" ? body.explanation.trim() : "";
  const comment = typeof body.comment === "string" ? body.comment.trim() : "";
  if (
    !questionIdPattern.test(questionId)
    || questionId.length > 160
    || !fingerprintPattern.test(questionFingerprint)
    || !stem
    || stem.length > 20000
    || !explanation
    || explanation.length > 20000
    || comment.length > 2000
  ) {
    return NextResponse.json({ error: "문항 수정 정보가 올바르지 않습니다." }, { status: 400 });
  }

  const latest = conceptModelExperiments.experiments[0];
  const item = latest?.automatedReview.queue.find((candidate) => candidate.questionId === questionId);
  if (!item) {
    return NextResponse.json({ error: "현재 검수 대기열에 없는 문항입니다. 화면을 새로고침해 주세요." }, { status: 409 });
  }
  if (item.questionFingerprint !== questionFingerprint) {
    return NextResponse.json({ error: "문항이 변경되었습니다. 새로고침 후 다시 수정해 주세요." }, { status: 409 });
  }
  const choices = parseChoices(body.choices, item.elementId);
  if (!choices) {
    return NextResponse.json({ error: "선택지는 A-E 다섯 개이며 정답은 문항 대상 용어 하나여야 합니다." }, { status: 400 });
  }

  const supabase = await getServerSupabase();
  if (!supabase) return NextResponse.json({ error: "Supabase 연결이 없습니다." }, { status: 503 });
  const { data, error } = await supabase.rpc("submit_concept_question_edit", {
    p_review_input_sha256: latest.automatedReview.reviewInputSha256,
    p_question_id: questionId,
    p_question_fingerprint: questionFingerprint,
    p_element_id: item.elementId,
    p_stem: stem,
    p_explanation: explanation,
    p_choices: choices,
    p_comment: comment,
  });
  if (error) return NextResponse.json({ error: error.message }, { status: 400 });
  const saved = Array.isArray(data) ? data[0] : data;
  return NextResponse.json({
    editId: saved?.concept_question_edit_id,
    questionId,
    rerunRequired: true,
    message: "문항 수정이 저장되었습니다. 모델을 다시 실행하면 수정된 fingerprint로 재검수됩니다.",
  });
}
