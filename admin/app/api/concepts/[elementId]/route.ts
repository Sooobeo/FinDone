import { NextResponse } from "next/server";
import { getAdminContext } from "@/lib/auth";
import { getAdminCapabilities } from "@/lib/data";
import { getServerSupabase } from "@/lib/supabase/server";
import type { ConceptElement } from "@/lib/types";
import { validateConcept } from "@/lib/validation";

export async function PUT(
  request: Request,
  { params }: { params: Promise<{ elementId: string }> },
) {
  const [context, capabilities] = await Promise.all([getAdminContext(), getAdminCapabilities()]);
  if (context.mode !== "supabase" || !context.user || !context.hasAccess || !capabilities.canEdit) {
    return NextResponse.json({ error: "콘텐츠 편집 권한이 필요합니다." }, { status: 403 });
  }

  const { elementId } = await params;
  const body = (await request.json()) as ConceptElement;
  if (!body || body.elementId !== elementId) {
    return NextResponse.json({ error: "요소 ID가 요청 경로와 일치하지 않습니다." }, { status: 400 });
  }

  const issues = validateConcept(body).filter((issue) => issue.severity === "error");
  if (issues.length) {
    return NextResponse.json({ error: issues[0].message, issues }, { status: 422 });
  }

  const supabase = await getServerSupabase();
  if (!supabase) return NextResponse.json({ error: "Supabase 연결이 없습니다." }, { status: 503 });

  const { data, error } = await supabase.rpc("save_content_grid_row", {
    p_element_id: elementId,
    p_element_patch: {
      title: body.title,
      core_relation: body.coreRelation,
      scope_notes: body.elementScopeNotes,
      source_label: body.sourceLabel,
      source_locator: body.sourceLocator,
      spec_section_locator: body.specSectionLocator,
    },
    p_concept_patch: {
      title: body.title,
      definition_markdown: body.definition,
      intuition_markdown: body.intuition,
      learning_notes_markdown: body.scopeNotes,
      checklist_markdown: body.checklist,
    },
    p_formula_patch: {
      expression_markdown: body.formulaExpression,
      assumptions_markdown: body.formulaAssumptions,
      notes_markdown: body.formulaNotes,
    },
    p_change_reason: "Admin 개념 DB 편집",
  });

  if (error) return NextResponse.json({ error: error.message }, { status: 400 });
  return NextResponse.json({ data });
}
