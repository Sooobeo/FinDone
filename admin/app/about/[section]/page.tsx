import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { AppIntroPage } from "@/components/app-intro-page";
import { getIntroSection, introSlugs, isIntroSlug } from "@/lib/app-intro";

export function generateStaticParams() {
  return introSlugs.filter((slug) => slug !== "overview").map((section) => ({ section }));
}

export async function generateMetadata({ params }: { params: Promise<{ section: string }> }): Promise<Metadata> {
  const { section } = await params;
  if (!isIntroSlug(section) || section === "overview") return {};
  const content = await getIntroSection(section);
  return {
    title: { absolute: `${content.navLabel} · FinDone 앱 소개` },
    description: content.summary,
  };
}

export default async function AboutSectionPage({ params }: { params: Promise<{ section: string }> }) {
  const { section } = await params;
  if (!isIntroSlug(section) || section === "overview") notFound();
  return <AppIntroPage slug={section} />;
}
