import type { Metadata } from "next";
import { redirect } from "next/navigation";
import { SignupForm } from "@/components/signup-form";
import { getAdminContext } from "@/lib/auth";

export const metadata: Metadata = { title: "Viewer 회원가입" };

export default async function SignupPage() {
  const context = await getAdminContext();
  if (context.hasAccess && context.mode === "supabase") redirect("/dashboard");

  return (
    <main className="login-page">
      <section className="login-brand-panel" aria-label="FinDone Viewer 소개">
        <div className="login-brand-lockup login-brand-lockup-centered">
          <span className="login-brand-icon" aria-hidden="true">
            <img src="/brand/findone-app-icon.svg" alt="" />
          </span>
          <span>
            <strong>FinDone</strong>
            <small>CONTENT VIEWER</small>
          </span>
        </div>
      </section>
      <section className="login-form-panel">
        <SignupForm mode={context.mode} />
      </section>
    </main>
  );
}
