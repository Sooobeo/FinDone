import type { Metadata } from "next";
import { SourceManager } from "@/components/source-manager";
import { ViewerContentGuide } from "@/components/viewer-content-guide";
import { getAdminContext } from "@/lib/auth";
import { getAdminCapabilities, getSources } from "@/lib/data";
import { viewerGuides } from "@/lib/viewer-guides";

export const metadata: Metadata = { title: "원본 자료" };

export default async function SourcesPage() {
  const context = await getAdminContext();
  if (context.role === "viewer") return <ViewerContentGuide guide={viewerGuides.sources} />;
  const [sources, capabilities] = await Promise.all([getSources(), getAdminCapabilities()]);
  return (
    <SourceManager
      initialSources={sources}
      readOnly={context.mode !== "supabase" || !capabilities.canEdit}
    />
  );
}
