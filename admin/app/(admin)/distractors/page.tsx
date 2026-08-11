import type { Metadata } from "next";
import { DistractorManager } from "@/components/distractor-manager";
import { ViewerContentGuide } from "@/components/viewer-content-guide";
import { getAdminContext } from "@/lib/auth";
import { getAdminCapabilities, getConceptElements, getDistractors } from "@/lib/data";
import { viewerGuides } from "@/lib/viewer-guides";

export const metadata: Metadata = { title: "오답 후보" };

export default async function DistractorsPage() {
  const context = await getAdminContext();
  if (context.role === "viewer") return <ViewerContentGuide guide={viewerGuides.distractors} />;
  const [distractors, elements, capabilities] = await Promise.all([getDistractors(), getConceptElements(), getAdminCapabilities()]);
  return (
    <DistractorManager
      initialDistractors={distractors}
      elements={elements.map(({ elementId, title, domainName }) => ({ elementId, title, domainName }))}
      readOnly={context.mode !== "supabase" || !capabilities.canEdit}
    />
  );
}
