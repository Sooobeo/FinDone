"use client";

import { ArrowRight, ChevronDown, LoaderCircle, LockKeyhole, Mail, ShieldCheck, UserRound } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";
import { getBrowserSupabase } from "@/lib/supabase/browser";
import type { RuntimeMode } from "@/lib/supabase/config";
import type { AdminRole } from "@/lib/types";

interface RoleLoginPanelProps {
  expectedRole: AdminRole;
  mode: RuntimeMode;
  title: string;
  description: string;
}

type LoginStatus = "idle" | "authenticating" | "redirecting";

function RoleLoginPanel({ expectedRole, mode, title, description }: RoleLoginPanelProps) {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [status, setStatus] = useState<LoginStatus>("idle");
  const configError = mode === "misconfigured";
  const busy = status !== "idle";
  const isOwner = expectedRole === "owner";
  const emailId = `${expectedRole}-email`;
  const passwordId = `${expectedRole}-password`;

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    if (mode === "demo") {
      setStatus("redirecting");
      await new Promise<void>((resolve) => requestAnimationFrame(() => resolve()));
      router.replace("/dashboard");
      return;
    }
    const supabase = getBrowserSupabase();
    if (!supabase) {
      setError("Supabase 연결 설정을 확인해 주세요.");
      return;
    }

    setStatus("authenticating");
    const { data: auth, error: signInError } = await supabase.auth.signInWithPassword({ email, password });
    if (signInError || !auth.user) {
      setStatus("idle");
      setError("이메일 또는 비밀번호가 올바르지 않습니다.");
      return;
    }

    const { data: membership, error: membershipError } = await supabase
      .from("admin_users")
      .select("role,is_active")
      .eq("user_id", auth.user.id)
      .maybeSingle();

    if (membershipError || !membership?.is_active || membership.role !== expectedRole) {
      await supabase.auth.signOut();
      setStatus("idle");
      setError(isOwner ? "Owner 계정으로 로그인해 주세요." : "Viewer 계정으로 로그인해 주세요.");
      return;
    }

    setStatus("redirecting");
    await new Promise<void>((resolve) => requestAnimationFrame(() => resolve()));
    router.replace("/dashboard");
    router.refresh();
  }

  return (
    <details className="login-role-toggle">
      <summary>
        <span className="login-role-icon" aria-hidden="true">
          {isOwner ? <ShieldCheck size={19} /> : <UserRound size={19} />}
        </span>
        <span className="login-role-copy">
          <strong>{title}</strong>
          <small>{description}</small>
        </span>
        <ChevronDown className="login-role-chevron" size={18} aria-hidden="true" />
      </summary>

      <form className="login-form login-role-form" onSubmit={submit}>
        <label className="field-label" htmlFor={emailId}>이메일</label>
        <div className="input-with-icon">
          <Mail size={18} aria-hidden="true" />
          <input
            id={emailId}
            type="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            placeholder={isOwner ? "owner@example.com" : "viewer@example.com"}
            autoComplete="email"
            required={mode !== "demo"}
            disabled={configError || busy}
          />
        </div>

        <label className="field-label" htmlFor={passwordId}>비밀번호</label>
        <div className="input-with-icon">
          <LockKeyhole size={18} aria-hidden="true" />
          <input
            id={passwordId}
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            placeholder="비밀번호 입력"
            autoComplete="current-password"
            required={mode !== "demo"}
            disabled={configError || busy}
          />
        </div>

        {error ? <p className="form-error" role="alert">{error}</p> : null}

        <button
          className="button button-primary login-submit"
          type="submit"
          disabled={busy || configError}
          aria-busy={busy}
        >
          {status === "authenticating" ? (
            <><LoaderCircle className="login-button-spinner" size={17} aria-hidden="true" /> 로그인 중…</>
          ) : status === "redirecting" ? (
            <><LoaderCircle className="login-button-spinner" size={17} aria-hidden="true" /> 대시보드로 이동 중…</>
          ) : (
            <>{mode === "demo" ? "읽기 전용 데모 열기" : "로그인"} <ArrowRight size={17} /></>
          )}
        </button>
      </form>
    </details>
  );
}

export function LoginForm({ mode }: { mode: RuntimeMode }) {
  const configError = mode === "misconfigured";

  return (
    <div className="login-card login-choice-card">
      <div className="login-heading">
        <p className="eyebrow">ACCOUNT ACCESS</p>
        <h2>FinDone 로그인</h2>
      </div>

      {configError ? (
        <div className="inline-alert alert-error" role="alert">
          Supabase URL과 publishable key가 모두 설정되어야 합니다.
        </div>
      ) : null}

      {mode === "demo" ? (
        <div className="inline-alert alert-demo" role="status">
          연결 정보가 없어 읽기 전용 데모로 실행 중입니다.
        </div>
      ) : null}

      <div className="login-role-options">
        <RoleLoginPanel
          expectedRole="owner"
          mode={mode}
          title="Admin Login"
          description="Owner 전용 관리 로그인"
        />
        <RoleLoginPanel
          expectedRole="viewer"
          mode={mode}
          title="Viewer Login"
          description="읽기 전용 계정 로그인"
        />
        <Link className="button button-secondary viewer-signup-button" href="/signup">
          Viewer 회원가입 <ArrowRight size={17} />
        </Link>
      </div>

      <p className="login-copyright">
        <span>© 2026 FinDone. All rights reserved.</span>
        <a href="mailto:qyurimoon@yonsei.ac.kr">Contact: qyurimoon@yonsei.ac.kr</a>
      </p>
    </div>
  );
}
