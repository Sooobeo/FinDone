import { NextResponse } from "next/server";
import { getAdminContext } from "@/lib/auth";
import { getAdminCapabilities } from "@/lib/data";
import { GlossaryValidationError, validateGlossaryTerm } from "@/lib/glossary";
import { getServerSupabase } from "@/lib/supabase/server";

async function canEditGlossary() {
  const [context, capabilities] = await Promise.all([getAdminContext(), getAdminCapabilities()]);
  return context.mode === "supabase" && Boolean(context.user) && context.hasAccess && capabilities.canEdit;
}

export async function PUT(
  request: Request,
  { params }: { params: Promise<{ termId: string }> },
) {
  if (!await canEditGlossary()) {
    return NextResponse.json({ error: "용어집 편집 권한이 필요합니다." }, { status: 403 });
  }
  const { termId } = await params;
  let term;
  try {
    term = validateGlossaryTerm(await request.json(), termId);
  } catch (error) {
    const message = error instanceof GlossaryValidationError
      ? error.message
      : "용어 요청을 읽지 못했습니다.";
    return NextResponse.json({ error: message }, { status: 422 });
  }
  const supabase = await getServerSupabase();
  if (!supabase) return NextResponse.json({ error: "Supabase 연결이 없습니다." }, { status: 503 });
  const { data, error } = await supabase.rpc("save_glossary_term_and_queue_compile", {
    p_term_id: termId,
    p_term: term,
    p_change_reason: "Admin 용어집 편집",
  });
  if (error) return NextResponse.json({ error: error.message }, { status: 400 });
  const saved = data?.term && typeof data.term === "object"
    ? data.term as Record<string, unknown>
    : {};
  const contentRevision = Number(saved.content_revision);
  return NextResponse.json({
    term: {
      ...term,
      contentRevision: Number.isSafeInteger(contentRevision) ? contentRevision : term.contentRevision + 1,
      updatedAt: typeof saved.updated_at === "string" ? saved.updated_at : new Date().toISOString(),
    },
    compile: data?.compile ?? data,
  });
}

export async function DELETE(
  _request: Request,
  { params }: { params: Promise<{ termId: string }> },
) {
  if (!await canEditGlossary()) {
    return NextResponse.json({ error: "용어집 삭제 권한이 필요합니다." }, { status: 403 });
  }
  const { termId } = await params;
  if (!/^FIN-(?:0[1-9]|1\d|2[01])-\d{3}$/.test(termId)) {
    return NextResponse.json({ error: "용어 ID가 올바르지 않습니다." }, { status: 400 });
  }
  const supabase = await getServerSupabase();
  if (!supabase) return NextResponse.json({ error: "Supabase 연결이 없습니다." }, { status: 503 });
  const { data, error } = await supabase.rpc("archive_glossary_term_and_queue_compile", {
    p_term_id: termId,
    p_change_reason: "Admin 용어집 삭제",
  });
  if (error) return NextResponse.json({ error: error.message }, { status: 400 });
  return NextResponse.json(data);
}
