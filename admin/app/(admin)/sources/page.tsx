import type { Metadata } from "next";
import { SourceManager } from "@/components/source-manager";
import { getAdminContext } from "@/lib/auth";
import { getAdminCapabilities, getSources } from "@/lib/data";
import { viewerSources } from "@/lib/viewer-placeholders";

export const metadata: Metadata = { title: "원본 자료" };

export default async function SourcesPage() {
  const context = await getAdminContext();
  if (context.role === "viewer") {
    return <SourceManager initialSources={viewerSources} readOnly viewerMode />;
  }
  const [sources, capabilities] = await Promise.all([getSources(), getAdminCapabilities()]);
  return (
    <SourceManager
      initialSources={sources}
      readOnly={context.mode !== "supabase" || !capabilities.canEdit}
    />
  );
}
