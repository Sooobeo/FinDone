import type { Metadata } from "next";
import { getAdminContext } from "@/lib/auth";
import { getAdminCapabilities, getConceptElements } from "@/lib/data";
import { ConceptDatabase } from "@/components/concept-database";

export const metadata: Metadata = { title: "개념 DB" };

export default async function ConceptsPage() {
  const [elements, context, capabilities] = await Promise.all([
    getConceptElements(),
    getAdminContext(),
    getAdminCapabilities(),
  ]);
  return (
    <ConceptDatabase
      initialElements={elements}
      readOnly={context.mode !== "supabase" || !capabilities.canEdit}
    />
  );
}
