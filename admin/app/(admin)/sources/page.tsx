import type { Metadata } from "next";
import { SourceManager } from "@/components/source-manager";
import { getAdminContext } from "@/lib/auth";
import { getAdminCapabilities, getSources } from "@/lib/data";

export const metadata: Metadata = { title: "원본 자료" };

export default async function SourcesPage() {
  const [sources, context, capabilities] = await Promise.all([
    getSources(),
    getAdminContext(),
    getAdminCapabilities(),
  ]);
  return (
    <SourceManager
      initialSources={sources}
      readOnly={context.mode !== "supabase" || !capabilities.canEdit}
    />
  );
}
