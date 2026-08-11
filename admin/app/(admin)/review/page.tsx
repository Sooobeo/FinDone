import type { Metadata } from "next";
import { ReviewConsole } from "@/components/review-console";
import { ViewerContentGuide } from "@/components/viewer-content-guide";
import { getAdminContext } from "@/lib/auth";
import { getAdminCapabilities, getReviewWorkspace } from "@/lib/data";
import { viewerGuides } from "@/lib/viewer-guides";

export const metadata: Metadata = { title: "승인 검토" };

export default async function ReviewPage() {
  const context = await getAdminContext();
  if (context.role === "viewer") return <ViewerContentGuide guide={viewerGuides.review} />;
  const [workspace, capabilities] = await Promise.all([getReviewWorkspace(), getAdminCapabilities()]);
  return (
    <ReviewConsole
      workspace={workspace}
      capabilities={capabilities}
      demo={context.mode !== "supabase"}
    />
  );
}
