import { NextResponse } from "next/server";
import { getAdminContext } from "@/lib/auth";
import { getAdminCapabilities } from "@/lib/data";
import { getServerSupabase } from "@/lib/supabase/server";

export async function POST(request: Request) {
  const [context, capabilities] = await Promise.all([getAdminContext(), getAdminCapabilities()]);
  if (context.mode !== "supabase" || !context.user || !context.hasAccess || !capabilities.canEdit) {
    return NextResponse.json({ error: "용어집 컴파일 권한이 필요합니다." }, { status: 403 });
  }
  const input = await request.json().catch(() => ({})) as { releaseNotes?: unknown; minimumAppVersion?: unknown };
  const releaseNotes = typeof input.releaseNotes === "string"
    ? input.releaseNotes.trim().slice(0, 2_000)
    : "Admin 수동 용어집 컴파일";
  const minimumAppVersion = Number(input.minimumAppVersion ?? 1);
  if (!Number.isInteger(minimumAppVersion) || minimumAppVersion < 1) {
    return NextResponse.json({ error: "최소 앱 버전이 올바르지 않습니다." }, { status: 400 });
  }
  const supabase = await getServerSupabase();
  if (!supabase) return NextResponse.json({ error: "Supabase 연결이 없습니다." }, { status: 503 });
  const { data, error } = await supabase.rpc("queue_glossary_compile", {
    p_release_notes: releaseNotes || "Admin 수동 용어집 컴파일",
    p_minimum_app_version: minimumAppVersion,
  });
  if (error) return NextResponse.json({ error: error.message }, { status: 400 });
  return NextResponse.json(data);
}
