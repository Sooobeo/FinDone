import type { Metadata } from "next";
import { ArrowRight } from "lucide-react";
import Link from "next/link";
import { redirect } from "next/navigation";
import { LoginForm } from "@/components/login-form";
import { getAdminContext } from "@/lib/auth";

export const metadata: Metadata = { title: "로그인" };

export default async function LoginPage() {
  const context = await getAdminContext();
  if (context.hasAccess && context.mode === "supabase") redirect("/dashboard");

  return (
    <main className="login-page">
      <section className="login-brand-panel" aria-label="FinDone Admin 소개">
        <div className="login-brand-content">
          <div className="login-brand-lockup login-brand-lockup-centered">
            <span className="login-brand-icon" aria-hidden="true">
              <img src="/brand/findone-admin-icon.svg" alt="" />
            </span>
            <span>
              <strong>FinDone</strong>
              <small>CONTENT ADMIN</small>
            </span>
          </div>
          <Link className="login-about-button" href="/about">
            앱 소개 <ArrowRight size={17} />
          </Link>
        </div>
      </section>
      <section className="login-form-panel">
        <LoginForm mode={context.mode} />
      </section>
    </main>
  );
}
