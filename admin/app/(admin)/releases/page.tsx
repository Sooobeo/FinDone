import type { Metadata } from "next";
import { ReleaseConsole } from "@/components/release-console";
import { getAdminContext } from "@/lib/auth";
import { getAdminCapabilities, getReleaseWorkspace } from "@/lib/data";

export const metadata: Metadata = { title: "앱 반영" };

export default async function ReleasesPage() {
  const [workspace, capabilities, context] = await Promise.all([
    getReleaseWorkspace(),
    getAdminCapabilities(),
    getAdminContext(),
  ]);
  return (
    <ReleaseConsole
      workspace={workspace}
      capabilities={capabilities}
      demo={context.mode !== "supabase"}
    />
  );
}
