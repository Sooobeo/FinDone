import "server-only";

import { existsSync } from "node:fs";
import { readFile } from "node:fs/promises";
import path from "node:path";
import { getServerSupabase } from "@/lib/supabase/server";

export type ConceptQuestionDecision = {
  decision: "approved" | "rejected";
  reviewerId: string;
  reviewedAt: string;
  comment: string;
};

type QuestionReference = {
  questionId: string;
  questionFingerprint: string;
};

function repositoryRoot() {
  const cwd = process.cwd();
  const directScript = path.join(cwd, "tools", "review_concept_question_model.py");
  if (existsSync(directScript)) return cwd;
  const parent = path.resolve(cwd, "..");
  const parentScript = path.join(parent, "tools", "review_concept_question_model.py");
  if (existsSync(parentScript)) return parent;
  throw new Error("개념형 문항 검수 도구가 있는 저장소 루트를 찾지 못했습니다.");
}

export function parseConceptQuestionDecisions(
  source: string,
  questions: QuestionReference[],
): Record<string, ConceptQuestionDecision> {
  const currentFingerprints = new Map(
    questions.map((question) => [question.questionId, question.questionFingerprint]),
  );
  const result: Record<string, ConceptQuestionDecision> = {};
  for (const [lineIndex, line] of source.split(/\r?\n/u).entries()) {
    if (!line.trim()) continue;
    let row: Record<string, unknown>;
    try {
      const parsed = JSON.parse(line) as unknown;
      if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) throw new Error("not an object");
      row = parsed as Record<string, unknown>;
    } catch {
      throw new Error(`Owner 검수 기록 ${lineIndex + 1}행이 올바른 JSON 객체가 아닙니다.`);
    }
    if ((row.type ?? "question") !== "question") continue;
    const questionId = typeof row.questionId === "string" ? row.questionId : "";
    const fingerprint = typeof row.questionFingerprint === "string" ? row.questionFingerprint : "";
    const decision = row.decision;
    if (
      currentFingerprints.get(questionId) !== fingerprint
      || (decision !== "approved" && decision !== "rejected")
    ) continue;
    result[questionId] = {
      decision,
      reviewerId: typeof row.reviewerId === "string" ? row.reviewerId : "",
      reviewedAt: typeof row.reviewedAt === "string" ? row.reviewedAt : "",
      comment: typeof row.comment === "string" ? row.comment : "",
    };
  }
  return result;
}

export async function getConceptQuestionDecisions(
  reviewInputSha256: string,
  questions: QuestionReference[],
) {
  const supabase = await getServerSupabase();
  if (supabase) {
    const { data, error } = await supabase
      .from("concept_question_review_decisions")
      .select("question_id,question_fingerprint,decision,reviewer_id,decided_at,comment")
      .eq("review_input_sha256", reviewInputSha256)
      .order("decided_at", { ascending: true })
      .limit(1000);
    if (error) return {};
    const source = (data ?? []).map((row) => JSON.stringify({
      type: "question",
      questionId: row.question_id,
      questionFingerprint: row.question_fingerprint,
      decision: row.decision,
      reviewerId: row.reviewer_id,
      reviewedAt: row.decided_at,
      comment: row.comment,
    })).join("\n");
    return parseConceptQuestionDecisions(source, questions);
  }

  const root = repositoryRoot();
  const decisionsPath = path.join(root, "content", "model", "concept-owner-decisions.jsonl");
  try {
    return parseConceptQuestionDecisions(await readFile(decisionsPath, "utf8"), questions);
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === "ENOENT") return {};
    throw error;
  }
}
