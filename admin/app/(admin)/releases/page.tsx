import type { Metadata } from "next";
import { ReleaseConsole } from "@/components/release-console";
import { ViewerContentGuide } from "@/components/viewer-content-guide";
import { getAdminContext } from "@/lib/auth";
import { getAdminCapabilities, getReleaseWorkspace } from "@/lib/data";
import { viewerGuides } from "@/lib/viewer-guides";

export const metadata: Metadata = { title: "앱 반영" };

export default async function ReleasesPage() {
  const context = await getAdminContext();
  if (context.role === "viewer") return <ViewerContentGuide guide={viewerGuides.releases} />;
  const [workspace, capabilities] = await Promise.all([getReleaseWorkspace(), getAdminCapabilities()]);
  return (
    <ReleaseConsole
      workspace={workspace}
      capabilities={capabilities}
      demo={context.mode !== "supabase"}
    />
  );
}
