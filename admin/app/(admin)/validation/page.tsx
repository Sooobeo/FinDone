import type { Metadata } from "next";
import { ValidationConsole } from "@/components/validation-console";
import { getAdminContext } from "@/lib/auth";
import { getAdminCapabilities, getValidationWorkspace } from "@/lib/data";
import { viewerCapabilities, viewerValidationWorkspace } from "@/lib/viewer-placeholders";

export const metadata: Metadata = { title: "자동 검증" };

export default async function ValidationPage() {
  const context = await getAdminContext();
  if (context.role === "viewer") {
    return <ValidationConsole workspace={viewerValidationWorkspace} capabilities={viewerCapabilities} demo={false} viewerMode />;
  }
  const [workspace, capabilities] = await Promise.all([getValidationWorkspace(), getAdminCapabilities()]);
  return (
    <ValidationConsole
      workspace={workspace}
      capabilities={capabilities}
      demo={context.mode !== "supabase"}
    />
  );
}
