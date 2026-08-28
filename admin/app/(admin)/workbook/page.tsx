import { redirect } from "next/navigation";
import { getAdminContext } from "@/lib/auth";
import { getWorkbookIndex } from "@/lib/workbook";

export default async function WorkbookPage() {
  const context = await getAdminContext();
  if (context.mode === "misconfigured") redirect("/login?error=config");
  if (context.mode === "supabase" && !context.user) redirect("/login");
  if (context.role === "viewer") redirect("/workbook/A01");
  if (context.mode !== "demo" && context.role !== "owner") redirect("/unauthorized");

  const index = await getWorkbookIndex();
  const firstUnit = index.subjects[0]?.units[0];
  if (!firstUnit) throw new Error("Workbook has no units");
  redirect(`/workbook/${firstUnit.id}`);
}
