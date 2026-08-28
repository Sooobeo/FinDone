import type { Metadata } from "next";
import { ShieldCheck } from "lucide-react";
import { notFound, redirect } from "next/navigation";
import { PageHeader } from "@/components/page-header";
import { WorkbookStudy } from "@/components/workbook-study";
import { getAdminContext } from "@/lib/auth";
import { getWorkbookIndex, getWorkbookUnit } from "@/lib/workbook";

interface WorkbookUnitPageProps {
  params: Promise<{ unitId: string }>;
}

export const metadata: Metadata = { title: "이론 문제집" };

export default async function WorkbookUnitPage({ params }: WorkbookUnitPageProps) {
  const context = await getAdminContext();
  if (context.role === "viewer") {
    return (
      <div className="page-stack workbook-page">
        <PageHeader
          eyebrow="THEORY TO PRACTICE"
          title="FinDone 이론 문제집"
          description="Owner 화면의 개념 학습과 문제 풀이 구성을 안내합니다."
        />
        <section className="panel workbook-viewer-note">
          <ShieldCheck size={24} aria-hidden="true" />
          <div>
            <strong>Owner 전용 학습 콘텐츠입니다.</strong>
            <p>Viewer 안내 모드에서는 실제 개념, 문제, 정답과 해설을 표시하지 않습니다.</p>
          </div>
        </section>
      </div>
    );
  }
  if (context.mode === "misconfigured") redirect("/login?error=config");
  if (context.mode === "supabase" && !context.user) redirect("/login");
  if (context.mode !== "demo" && context.role !== "owner") redirect("/unauthorized");

  const { unitId } = await params;
  const [index, unit] = await Promise.all([getWorkbookIndex(), getWorkbookUnit(unitId)]);
  if (!unit) notFound();

  return <WorkbookStudy key={`${unit.sourceSha256}:${unit.id}`} index={index} unit={unit} />;
}
