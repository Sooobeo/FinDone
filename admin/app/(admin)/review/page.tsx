import type { Metadata } from "next";
import { ReviewConsole } from "@/components/review-console";
import { getAdminContext } from "@/lib/auth";
import { getAdminCapabilities, getReviewWorkspace } from "@/lib/data";

export const metadata: Metadata = { title: "승인 검토" };

export default async function ReviewPage() {
  const [workspace, capabilities, context] = await Promise.all([
    getReviewWorkspace(),
    getAdminCapabilities(),
    getAdminContext(),
  ]);
  return (
    <ReviewConsole
      workspace={workspace}
      capabilities={capabilities}
      demo={context.mode !== "supabase"}
    />
  );
}
