import type { Metadata } from "next";
import { AppIntroPage } from "@/components/app-intro-page";

export const metadata: Metadata = {
  title: { absolute: "FinDone 앱 소개" },
  description: "FinDone Android 앱의 오늘, 학습, 퀴즈, 기록 기능을 소개합니다.",
};

export default function AboutPage() {
  return <AppIntroPage slug="overview" />;
}
