import type { Metadata } from "next";
import { redirect } from "next/navigation";
import { LoginForm } from "@/components/login-form";
import { getAdminContext } from "@/lib/auth";

export const metadata: Metadata = { title: "로그인" };

export default async function LoginPage() {
  const context = await getAdminContext();
  if (context.isAdmin && context.mode === "supabase") redirect("/dashboard");

  return (
    <main className="login-page">
      <section className="login-brand-panel" aria-label="FinDone Admin 소개">
        <div className="login-brand-lockup login-brand-lockup-centered">
          <span className="login-brand-icon" aria-hidden="true">
            <svg viewBox="0 0 64 64" fill="none" xmlns="http://www.w3.org/2000/svg">
              <rect x="18" y="13" width="7" height="38" rx="3.5" fill="currentColor" />
              <path d="M25 15.5C32.5 11.5 42.5 11.8 50 16.2C49.2 24.8 40.5 29.2 25 27.6V15.5Z" fill="currentColor" />
              <path d="M25 33.6C31.5 30.5 39.5 30.8 45 34.1C43.8 41.2 36.5 44.8 25 42.3V33.6Z" fill="currentColor" />
            </svg>
          </span>
          <span>
            <strong>FinDone</strong>
            <small>CONTENT ADMIN</small>
          </span>
        </div>
      </section>
      <section className="login-form-panel">
        <LoginForm mode={context.mode} />
      </section>
    </main>
  );
}
