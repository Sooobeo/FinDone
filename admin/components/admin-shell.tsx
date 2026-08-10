"use client";

import {
  BookOpenText,
  CheckCircle2,
  ChevronLeft,
  Database,
  FileArchive,
  FileCheck2,
  FileSearch,
  LayoutDashboard,
  LogOut,
  Menu,
  MessageSquareWarning,
  Settings,
  X,
} from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import type { ReactNode } from "react";
import { useState } from "react";
import { getBrowserSupabase } from "@/lib/supabase/browser";
import type { RuntimeMode } from "@/lib/supabase/config";

const navItems = [
  { href: "/dashboard", label: "대시보드", icon: LayoutDashboard },
  { href: "/concepts", label: "개념 DB", icon: Database },
  { href: "/sources", label: "원본 자료", icon: FileSearch },
  { href: "/distractors", label: "오답 후보", icon: MessageSquareWarning },
  { href: "/validation", label: "자동 검증", icon: CheckCircle2 },
  { href: "/review", label: "승인 검토", icon: FileCheck2 },
  { href: "/releases", label: "앱 반영", icon: FileArchive },
] as const;

interface AdminShellProps {
  children: ReactNode;
  mode: RuntimeMode;
  email?: string;
}

export function AdminShell({ children, mode, email }: AdminShellProps) {
  const pathname = usePathname();
  const router = useRouter();
  const [mobileOpen, setMobileOpen] = useState(false);
  const activeItem = navItems.find((item) => pathname.startsWith(item.href));

  async function signOut() {
    await getBrowserSupabase()?.auth.signOut();
    router.replace("/login");
    router.refresh();
  }

  return (
    <div className="admin-frame">
      <aside className={`sidebar ${mobileOpen ? "sidebar-open" : ""}`} aria-label="관리 메뉴">
        <div className="sidebar-brand">
          <Link href="/dashboard" className="brand-link" onClick={() => setMobileOpen(false)}>
            <span className="brand-mark" aria-hidden="true">F</span>
            <span>
              <strong>FinDone</strong>
              <small>CONTENT ADMIN</small>
            </span>
          </Link>
          <button
            className="icon-button sidebar-close"
            type="button"
            onClick={() => setMobileOpen(false)}
            aria-label="메뉴 닫기"
          >
            <X size={19} />
          </button>
        </div>

        <div className="sidebar-context">
          <span className="context-icon"><BookOpenText size={16} /></span>
          <span>
            <small>작업 공간</small>
            <strong>학습 콘텐츠</strong>
          </span>
          <ChevronLeft className="context-chevron" size={16} aria-hidden="true" />
        </div>

        <nav className="sidebar-nav">
          <p className="nav-label">관리</p>
          {navItems.map(({ href, label, icon: Icon }) => {
            const active = pathname.startsWith(href);
            return (
              <Link
                key={href}
                href={href}
                className={active ? "nav-link nav-link-active" : "nav-link"}
                aria-current={active ? "page" : undefined}
                onClick={() => setMobileOpen(false)}
              >
                <Icon size={18} strokeWidth={active ? 2.3 : 1.8} />
                <span>{label}</span>
              </Link>
            );
          })}
        </nav>

        <div className="sidebar-footer">
          <div className="admin-avatar" aria-hidden="true">
            {(email?.[0] ?? "관").toUpperCase()}
          </div>
          <div className="admin-identity">
            <strong>{mode === "demo" ? "데모 관리자" : "관리자"}</strong>
            <small>{email ?? "읽기 전용 미리보기"}</small>
          </div>
          <button className="icon-button dark-icon-button" type="button" onClick={signOut} aria-label="로그아웃">
            <LogOut size={17} />
          </button>
        </div>
      </aside>

      {mobileOpen ? (
        <button
          className="sidebar-scrim"
          onClick={() => setMobileOpen(false)}
          aria-hidden="true"
          tabIndex={-1}
        />
      ) : null}

      <div className="workspace">
        <header className="topbar">
          <div className="topbar-title">
            <button
              className="icon-button mobile-menu-button"
              type="button"
              onClick={() => setMobileOpen(true)}
              aria-label="메뉴 열기"
            >
              <Menu size={20} />
            </button>
            <span>{activeItem?.label ?? "관리"}</span>
          </div>
          <div className="topbar-meta">
            <span className={mode === "supabase" ? "connection-live" : "connection-demo"}>
              <span aria-hidden="true" />
              {mode === "supabase" ? "Supabase 연결됨" : "데모 · 읽기 전용"}
            </span>
            <button className="icon-button" type="button" aria-label="설정" disabled>
              <Settings size={18} />
            </button>
          </div>
        </header>

        {mode === "demo" ? (
          <div className="demo-banner" role="status">
            <span className="demo-banner-icon" aria-hidden="true">D</span>
            <p>
              <strong>현재 앱의 실제 콘텐츠를 읽기 전용으로 표시하고 있습니다.</strong>
              Supabase 환경변수를 연결하면 편집·업로드·승인이 활성화됩니다.
            </p>
          </div>
        ) : null}

        <main className="main-content">{children}</main>
      </div>
    </div>
  );
}
