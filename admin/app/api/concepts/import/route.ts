import { NextResponse } from "next/server";
import { getAdminContext } from "@/lib/auth";
import { getAdminCapabilities } from "@/lib/data";
import { getServerSupabase } from "@/lib/supabase/server";
import type { ConceptElement } from "@/lib/types";
import { validateConcept } from "@/lib/validation";

const STRING_FIELDS: Array<keyof ConceptElement> = [
  "elementId", "title", "coreRelation", "definition", "intuition",
  "elementScopeNotes", "scopeNotes", "formulaExpression", "formulaAssumptions",
  "formulaNotes", "checklist", "sourceLabel", "sourceLocator", "specSectionLocator",
];

function isConceptElement(value: unknown): value is ConceptElement {
  if (!value || typeof value !== "object") return false;
  const row = value as Record<string, unknown>;
  return STRING_FIELDS.every((field) => typeof row[field] === "string");
}

export async function POST(request: Request) {
  const [context, capabilities] = await Promise.all([getAdminContext(), getAdminCapabilities()]);
  if (context.mode !== "supabase" || !context.user || !context.hasAccess || !capabilities.canEdit) {
    return NextResponse.json({ error: "콘텐츠 편집 권한이 필요합니다." }, { status: 403 });
  }
  const contentLength = Number(request.headers.get("content-length") ?? 0);
  if (contentLength > 10 * 1024 * 1024) {
    return NextResponse.json({ error: "가져오기 요청은 10MB 이하여야 합니다." }, { status: 413 });
  }

  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "올바른 JSON 요청이 아닙니다." }, { status: 400 });
  }
  const elements = (body as { elements?: unknown })?.elements;
  if (!Array.isArray(elements) || elements.length < 1 || elements.length > 135) {
    return NextResponse.json({ error: "변경 요소는 1개 이상 135개 이하여야 합니다." }, { status: 400 });
  }
  if (!elements.every(isConceptElement)) {
    return NextResponse.json({ error: "요소 데이터 형식이 올바르지 않습니다." }, { status: 400 });
  }
  const ids = elements.map((element) => element.elementId);
  if (new Set(ids).size !== ids.length) {
    return NextResponse.json({ error: "중복된 요소 ID가 있습니다." }, { status: 400 });
  }
  for (const element of elements) {
    const error = validateConcept(element).find((issue) => issue.severity === "error");
    if (error) {
      return NextResponse.json({ error: `${element.elementId}: ${error.message}` }, { status: 422 });
    }
  }

  const rows = elements.map((element) => ({
    elementId: element.elementId,
    elementPatch: {
      title: element.title,
      core_relation: element.coreRelation,
      scope_notes: element.elementScopeNotes,
      source_label: element.sourceLabel,
      source_locator: element.sourceLocator,
      spec_section_locator: element.specSectionLocator,
    },
    conceptPatch: {
      title: element.title,
      definition_markdown: element.definition,
      intuition_markdown: element.intuition,
      learning_notes_markdown: element.scopeNotes,
      checklist_markdown: element.checklist,
    },
    formulaPatch: {
      expression_markdown: element.formulaExpression,
      assumptions_markdown: element.formulaAssumptions,
      // Keep the app projection and the concept checklist field in sync.
      notes_markdown: element.checklist,
    },
  }));

  const supabase = await getServerSupabase();
  if (!supabase) return NextResponse.json({ error: "Supabase 연결이 없습니다." }, { status: 503 });
  const { data, error } = await supabase.rpc("save_content_grid_rows", {
    p_rows: rows,
    p_change_reason: `Admin CSV 가져오기 (${rows.length}개 요소)`,
  });
  if (error) return NextResponse.json({ error: error.message }, { status: 400 });
  return NextResponse.json({ data, saved: rows.length });
}
