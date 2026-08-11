import type { Metadata } from "next";
import { ValidationConsole } from "@/components/validation-console";
import { ViewerContentGuide } from "@/components/viewer-content-guide";
import { getAdminContext } from "@/lib/auth";
import { getAdminCapabilities, getValidationWorkspace } from "@/lib/data";
import { viewerGuides } from "@/lib/viewer-guides";

export const metadata: Metadata = { title: "자동 검증" };

export default async function ValidationPage() {
  const context = await getAdminContext();
  if (context.role === "viewer") return <ViewerContentGuide guide={viewerGuides.validation} />;
  const [workspace, capabilities] = await Promise.all([getValidationWorkspace(), getAdminCapabilities()]);
  return (
    <ValidationConsole
      workspace={workspace}
      capabilities={capabilities}
      demo={context.mode !== "supabase"}
    />
  );
}
