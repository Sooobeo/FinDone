import type { Metadata } from "next";
import { ValidationConsole } from "@/components/validation-console";
import { getAdminContext } from "@/lib/auth";
import { getAdminCapabilities, getValidationWorkspace } from "@/lib/data";

export const metadata: Metadata = { title: "자동 검증" };

export default async function ValidationPage() {
  const [workspace, capabilities, context] = await Promise.all([
    getValidationWorkspace(),
    getAdminCapabilities(),
    getAdminContext(),
  ]);
  return (
    <ValidationConsole
      workspace={workspace}
      capabilities={capabilities}
      demo={context.mode !== "supabase"}
    />
  );
}
