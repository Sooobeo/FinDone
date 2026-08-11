import type { Metadata } from "next";
import type { ReactNode } from "react";
import "./globals.css";

export const metadata: Metadata = {
  metadataBase: new URL("https://ffinddone.vercel.app"),
  title: {
    default: "FinDone Admin",
    template: "%s · FinDone Admin",
  },
  description: "FinDone 학습 콘텐츠 제작·검수·배포 관리자",
  icons: {
    icon: [{ url: "/brand/findone-app-icon.svg", type: "image/svg+xml" }],
    shortcut: "/brand/findone-app-icon.svg",
  },
  openGraph: {
    type: "website",
    locale: "ko_KR",
    url: "/",
    siteName: "FinDone",
    title: "FinDone Content Admin",
    description: "FinDone 학습 콘텐츠 제작·검수·배포 관리자",
    images: [
      {
        url: "/opengraph-image",
        width: 1200,
        height: 630,
        alt: "FinDone Content Admin",
      },
    ],
  },
  twitter: {
    card: "summary_large_image",
    title: "FinDone Content Admin",
    description: "FinDone 학습 콘텐츠 제작·검수·배포 관리자",
    images: ["/opengraph-image"],
  },
  robots: { index: false, follow: false, noarchive: true },
};

export default function RootLayout({ children }: Readonly<{ children: ReactNode }>) {
  return (
    <html lang="ko">
      <body>{children}</body>
    </html>
  );
}
