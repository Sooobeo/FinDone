import type { Metadata } from "next";
import { ReviewConsole } from "@/components/review-console";
import { getAdminContext } from "@/lib/auth";
import { getAdminCapabilities, getReviewWorkspace } from "@/lib/data";
import { viewerCapabilities, viewerReviewWorkspace } from "@/lib/viewer-placeholders";

export const metadata: Metadata = { title: "앱 DB 최종 검토" };

export default async function ReviewPage() {
  const context = await getAdminContext();
  if (context.role === "viewer") {
    return <ReviewConsole workspace={viewerReviewWorkspace} capabilities={viewerCapabilities} demo={false} viewerMode />;
  }
  const [workspace, capabilities] = await Promise.all([getReviewWorkspace(), getAdminCapabilities()]);
  return (
    <ReviewConsole
      workspace={workspace}
      capabilities={capabilities}
      demo={context.mode !== "supabase"}
    />
  );
}
