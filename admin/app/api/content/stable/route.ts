import { NextResponse } from "next/server";
import { getServiceSupabase } from "@/lib/supabase/service";

export const dynamic = "force-dynamic";

type ArtifactRow = {
  artifact_kind: "content_database" | "manifest";
  object_path: string;
  sha256: string;
  byte_size: number;
};

function unavailable(message: string, status = 503) {
  return NextResponse.json(
    { error: message },
    { status, headers: { "Cache-Control": "no-store" } },
  );
}

export async function GET() {
  const supabase = getServiceSupabase();
  if (!supabase) return unavailable("Content release service is not configured.");

  const { data: channel, error: channelError } = await supabase
    .from("release_channels")
    .select("release_id,activated_at")
    .eq("channel", "stable")
    .maybeSingle();
  if (channelError) return unavailable("Could not read the stable release.");
  if (!channel) return unavailable("No stable content release is active.", 404);

  const [{ data: release, error: releaseError }, { data: artifacts, error: artifactError }] =
    await Promise.all([
      supabase
        .from("content_releases")
        .select(
          "release_id,content_version,version_name,schema_version,minimum_app_version,status,manifest_sha256,database_sha256,database_byte_size,published_at",
        )
        .eq("release_id", channel.release_id)
        .eq("status", "published")
        .maybeSingle(),
      supabase
        .from("release_artifacts")
        .select("artifact_kind,object_path,sha256,byte_size")
        .eq("release_id", channel.release_id)
        .in("artifact_kind", ["content_database", "manifest"]),
    ]);
  if (releaseError || artifactError) return unavailable("Could not read release artifacts.");
  if (!release) return unavailable("The stable release is not published.", 409);

  const byKind = new Map(
    ((artifacts ?? []) as ArtifactRow[]).map((artifact) => [artifact.artifact_kind, artifact]),
  );
  const database = byKind.get("content_database");
  const manifest = byKind.get("manifest");
  if (
    !database ||
    !manifest ||
    database.sha256 !== release.database_sha256 ||
    database.byte_size !== release.database_byte_size ||
    manifest.sha256 !== release.manifest_sha256
  ) {
    return unavailable("The stable release artifacts are incomplete.", 409);
  }

  const expiresIn = 10 * 60;
  const { data: signed, error: signedError } = await supabase.storage
    .from("release-bundles")
    .createSignedUrls([manifest.object_path, database.object_path], expiresIn);
  const manifestUrl = signed?.find((item) => item.path === manifest.object_path)?.signedUrl;
  const databaseUrl = signed?.find((item) => item.path === database.object_path)?.signedUrl;
  if (signedError || !manifestUrl || !databaseUrl) {
    return unavailable("Could not authorize release downloads.");
  }

  return NextResponse.json(
    {
      protocolVersion: 1,
      channel: "stable",
      releaseId: release.release_id,
      contentDbVersion: release.content_version,
      versionName: release.version_name,
      schemaVersion: release.schema_version,
      minimumAppVersion: release.minimum_app_version,
      manifestSha256: release.manifest_sha256,
      databaseSha256: release.database_sha256,
      databaseByteSize: release.database_byte_size,
      manifestUrl,
      databaseUrl,
      activatedAt: channel.activated_at,
      publishedAt: release.published_at,
      expiresInSeconds: expiresIn,
    },
    { headers: { "Cache-Control": "no-store" } },
  );
}
