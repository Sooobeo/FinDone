import type { Metadata } from "next";
import { DistractorManager } from "@/components/distractor-manager";
import { getAdminContext } from "@/lib/auth";
import { getAdminCapabilities, getConceptElements, getDistractors } from "@/lib/data";

export const metadata: Metadata = { title: "오답 후보" };

export default async function DistractorsPage() {
  const [distractors, elements, context, capabilities] = await Promise.all([
    getDistractors(),
    getConceptElements(),
    getAdminContext(),
    getAdminCapabilities(),
  ]);
  return (
    <DistractorManager
      initialDistractors={distractors}
      elements={elements.map(({ elementId, title, domainName }) => ({ elementId, title, domainName }))}
      readOnly={context.mode !== "supabase" || !capabilities.canEdit}
    />
  );
}
