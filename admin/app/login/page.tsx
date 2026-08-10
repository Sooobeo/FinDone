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
        <div className="login-brand-lockup">
          <span className="brand-mark brand-mark-large" aria-hidden="true">F</span>
          <span>
            <strong>FinDone</strong>
            <small>CONTENT ADMIN</small>
          </span>
        </div>
        <div className="login-brand-copy">
          <p className="eyebrow eyebrow-light">CURATE WITH CONFIDENCE</p>
          <h1>배우는 화면에 닿기 전,<br />한 번 더 정확하게.</h1>
          <p>개념과 수식을 정돈하고, 근거를 확인한 뒤 승인된 콘텐츠만 앱에 전달합니다.</p>
        </div>
        <div className="login-flow" aria-label="콘텐츠 작업 흐름">
          <span>정리</span><i aria-hidden="true" /><span>검증</span><i aria-hidden="true" /><span>승인</span><i aria-hidden="true" /><span>반영</span>
        </div>
      </section>
      <section className="login-form-panel">
        <LoginForm mode={context.mode} />
      </section>
    </main>
  );
}
