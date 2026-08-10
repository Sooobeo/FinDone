import type { ReactNode } from "react";
import { redirect } from "next/navigation";
import { AdminShell } from "@/components/admin-shell";
import { getAdminContext } from "@/lib/auth";

export default async function ProtectedLayout({ children }: { children: ReactNode }) {
  const context = await getAdminContext();

  if (context.mode === "misconfigured") redirect("/login?error=config");
  if (context.mode === "supabase" && !context.user) redirect("/login");
  if (context.mode === "supabase" && !context.isAdmin) redirect("/unauthorized");

  return (
    <AdminShell mode={context.mode} email={context.user?.email}>
      {children}
    </AdminShell>
  );
}
