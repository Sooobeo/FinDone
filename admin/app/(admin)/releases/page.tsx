import type { Metadata } from "next";
import { ReleaseConsole } from "@/components/release-console";
import { getAdminContext } from "@/lib/auth";
import { getAdminCapabilities, getReleaseWorkspace } from "@/lib/data";
import { viewerCapabilities, viewerReleaseWorkspace } from "@/lib/viewer-placeholders";

export const metadata: Metadata = { title: "릴리스 이력" };

export default async function ReleasesPage() {
  const context = await getAdminContext();
  if (context.role === "viewer") {
    return <ReleaseConsole workspace={viewerReleaseWorkspace} capabilities={viewerCapabilities} demo={false} viewerMode />;
  }
  const [workspace, capabilities] = await Promise.all([getReleaseWorkspace(), getAdminCapabilities()]);
  return (
    <ReleaseConsole
      workspace={workspace}
      capabilities={capabilities}
      demo={context.mode !== "supabase"}
    />
  );
}
