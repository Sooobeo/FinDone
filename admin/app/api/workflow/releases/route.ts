import { NextResponse } from "next/server";
import { getAdminCapabilities } from "@/lib/data";
import { isReleaseAction, isRequestUuid, type ReleaseAction } from "@/lib/release-actions";
import { getServerSupabase } from "@/lib/supabase/server";

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
    releaseId?: string;
    action?: ReleaseAction;
    channel?: string;
    note?: string;
    versionName?: string;
    releaseNotes?: string;
    minimumAppVersion?: number;
    requestKey?: string;
  };
  if (!isReleaseAction(body.action)) {
    return NextResponse.json({ error: "릴리스와 작업을 선택해 주세요." }, { status: 400 });
  }
  const capabilities = await getAdminCapabilities();
  if (body.action === "validate" && !capabilities.canValidateRelease) {
    return NextResponse.json({ error: "릴리스 검증 권한이 없습니다." }, { status: 403 });
  }
  if (body.action !== "validate" && !capabilities.canRelease) {
    return NextResponse.json({ error: "릴리스 배포 권한이 없습니다." }, { status: 403 });
  }

  const supabase = await getServerSupabase();
  if (!supabase) return NextResponse.json({ error: "Supabase 연결이 없습니다." }, { status: 503 });

  if (body.action === "create") {
    const versionName = body.versionName?.trim() ?? "";
    const releaseNotes = body.releaseNotes?.trim() ?? "";
    const minimumAppVersion = Number(body.minimumAppVersion ?? 1);
    const requestKey = body.requestKey?.trim() ?? "";
    if (!isRequestUuid(requestKey)) {
      return NextResponse.json({ error: "릴리스 요청 키가 올바르지 않습니다." }, { status: 400 });
    }
    if (versionName.length > 80 || releaseNotes.length > 4000) {
      return NextResponse.json({ error: "버전명 또는 개선 내용이 허용 길이를 초과했습니다." }, { status: 400 });
    }
    if (!Number.isInteger(minimumAppVersion) || minimumAppVersion < 1 || minimumAppVersion > 2_147_483_647) {
      return NextResponse.json({ error: "최소 앱 버전은 1 이상의 정수여야 합니다." }, { status: 400 });
    }
    const { data, error } = await supabase.rpc("create_release_from_approved", {
      p_request_key: requestKey,
      p_version_name: versionName || null,
      p_release_notes: releaseNotes,
      p_minimum_app_version: minimumAppVersion,
    });
    if (error) return NextResponse.json({ error: error.message }, { status: 400 });
    const release = (Array.isArray(data) ? data[0] : data) as {
      release_id?: string;
      version_name?: string;
      status?: string;
    } | null;
    const knownStatus = new Set(["building", "validation_failed", "ready", "published", "withdrawn"]);
    if (!release?.release_id || !release.version_name || !release.status || !knownStatus.has(release.status)) {
      return NextResponse.json({ error: "릴리스 생성 응답을 확인할 수 없습니다. 같은 요청으로 다시 시도해 주세요." }, { status: 502 });
    }
    return NextResponse.json({
      releaseId: release?.release_id,
      status: release?.status,
      message: `${release?.version_name ?? "새 릴리스"} 자동 반영을 시작했습니다. 빌드와 검증을 통과하면 stable에 공개됩니다.`,
    });
  }

  if (!body.releaseId) {
    return NextResponse.json({ error: "릴리스를 선택해 주세요." }, { status: 400 });
  }
  const { data: release, error: releaseError } = await supabase
    .from("release_overview")
    .select("release_id,status")
    .eq("release_id", body.releaseId)
    .maybeSingle();
  if (releaseError || !release) {
    return NextResponse.json({ error: releaseError?.message ?? "릴리스를 찾을 수 없습니다." }, { status: 404 });
  }

  if (body.action === "validate") {
    if (release.status !== "building") {
      return NextResponse.json({ error: "빌드 중인 릴리스만 검증 대기열에 넣을 수 있습니다." }, { status: 409 });
    }
    const { data: buildJobs, error: buildJobError } = await supabase
      .from("ingestion_jobs")
      .select("status")
      .eq("release_id", body.releaseId)
      .eq("job_kind", "release_build");
    if (buildJobError) return NextResponse.json({ error: buildJobError.message }, { status: 400 });
    if ((buildJobs ?? []).some((job) => job.status === "queued" || job.status === "running")) {
      return NextResponse.json({ error: "릴리스 DB 빌드가 끝난 뒤 검증을 요청해 주세요." }, { status: 409 });
    }
    if (!(buildJobs ?? []).some((job) => job.status === "succeeded")) {
      return NextResponse.json({ error: "성공한 릴리스 DB 빌드가 필요합니다." }, { status: 409 });
    }
    const { data, error } = await supabase.rpc("start_release_validation", {
      p_release_id: body.releaseId,
      p_validator_name: "findone-release-validator",
      p_validator_version: "admin-v1",
    });
    if (error) return NextResponse.json({ error: error.message }, { status: 400 });
    return NextResponse.json({
      validationRunId: data.validation_run_id,
      status: data.status,
      message: "릴리스 검증 작업을 대기열에 등록했습니다.",
    });
  }

  if (body.action === "activate") {
    if (release.status !== "ready" && release.status !== "published") {
      return NextResponse.json({ error: "준비 완료된 릴리스만 활성화할 수 있습니다." }, { status: 409 });
    }
    const channel = body.channel?.trim() || "stable";
    if (!/^[a-z][a-z0-9_-]{1,31}$/.test(channel)) {
      return NextResponse.json({ error: "채널 이름 형식이 올바르지 않습니다." }, { status: 400 });
    }
    const { data, error } = await supabase.rpc("activate_release", {
      p_release_id: body.releaseId,
      p_channel: channel,
    });
    if (error) return NextResponse.json({ error: error.message }, { status: 400 });
    return NextResponse.json({ channel: data.channel, activatedAt: data.activated_at });
  }

  const note = body.note?.trim() ?? "";
  if (!note) return NextResponse.json({ error: "릴리스 철회 사유가 필요합니다." }, { status: 400 });
  if (release.status === "withdrawn") {
    return NextResponse.json({ error: "이미 철회된 릴리스입니다." }, { status: 409 });
  }
  const { data, error } = await supabase.rpc("set_release_status", {
    p_release_id: body.releaseId,
    p_status: "withdrawn",
    p_note: note,
  });
  if (error) return NextResponse.json({ error: error.message }, { status: 400 });
  return NextResponse.json({ status: data.status });
}
