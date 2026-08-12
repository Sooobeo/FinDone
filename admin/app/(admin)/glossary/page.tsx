import type { Metadata } from "next";
import { GlossaryManager } from "@/components/glossary-manager";
import { getAdminContext } from "@/lib/auth";
import { getAdminCapabilities, getGlossaryWorkspace } from "@/lib/data";

export const metadata: Metadata = { title: "용어집" };

export default async function GlossaryPage() {
  const context = await getAdminContext();
  if (context.role === "viewer") {
    return <GlossaryManager categories={[]} sources={[]} adminReferenceSources={[]} terms={[]} releases={[]} jobs={[]} readOnly viewerMode />;
  }
  const [workspace, capabilities] = await Promise.all([getGlossaryWorkspace(), getAdminCapabilities()]);
  return <GlossaryManager {...workspace} readOnly={context.mode !== "supabase" || !capabilities.canEdit} />;
}
