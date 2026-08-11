import type { Metadata } from "next";
import { getAdminContext } from "@/lib/auth";
import { getAdminCapabilities, getConceptElements } from "@/lib/data";
import { ConceptDatabase } from "@/components/concept-database";
import { viewerConceptElements } from "@/lib/viewer-placeholders";

export const metadata: Metadata = { title: "개념 DB" };

export default async function ConceptsPage() {
  const context = await getAdminContext();
  if (context.role === "viewer") {
    return <ConceptDatabase initialElements={viewerConceptElements} readOnly viewerMode />;
  }
  const [elements, capabilities] = await Promise.all([getConceptElements(), getAdminCapabilities()]);
  return (
    <ConceptDatabase
      initialElements={elements}
      readOnly={context.mode !== "supabase" || !capabilities.canEdit}
    />
  );
}
