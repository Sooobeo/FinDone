"use client";

import { ArrowRight, LockKeyhole, Mail } from "lucide-react";
import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";
import { getBrowserSupabase } from "@/lib/supabase/browser";
import type { RuntimeMode } from "@/lib/supabase/config";

export function LoginForm({ mode }: { mode: RuntimeMode }) {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const configError = mode === "misconfigured";

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    if (mode === "demo") {
      router.replace("/dashboard");
      return;
    }
    const supabase = getBrowserSupabase();
    if (!supabase) {
      setError("Supabase 연결 설정을 확인해 주세요.");
      return;
    }

    setLoading(true);
    const { error: signInError } = await supabase.auth.signInWithPassword({ email, password });
    setLoading(false);
    if (signInError) {
      setError("이메일 또는 비밀번호가 올바르지 않습니다.");
      return;
    }
    router.replace("/dashboard");
    router.refresh();
  }

  return (
    <div className="login-card">
      <div className="login-heading">
        <p className="eyebrow">ADMIN ACCESS</p>
        <h2>관리자 로그인</h2>
        <p>사전에 등록된 관리자 계정으로만 접근할 수 있습니다.</p>
      </div>

      {configError ? (
        <div className="inline-alert alert-error" role="alert">
          Supabase URL과 publishable key가 모두 설정되어야 합니다.
        </div>
      ) : null}

      {mode === "demo" ? (
        <div className="inline-alert alert-demo" role="status">
          연결 정보가 없어 읽기 전용 데모로 실행 중입니다. 로그인 없이 현재 콘텐츠를 확인할 수 있습니다.
        </div>
      ) : null}

      <form className="login-form" onSubmit={submit}>
        <label className="field-label" htmlFor="email">이메일</label>
        <div className="input-with-icon">
          <Mail size={18} aria-hidden="true" />
          <input
            id="email"
            type="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            placeholder="admin@example.com"
            autoComplete="email"
            required={mode !== "demo"}
            disabled={configError}
          />
        </div>

        <label className="field-label" htmlFor="password">비밀번호</label>
        <div className="input-with-icon">
          <LockKeyhole size={18} aria-hidden="true" />
          <input
            id="password"
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            placeholder="비밀번호 입력"
            autoComplete="current-password"
            required={mode !== "demo"}
            disabled={configError}
          />
        </div>

        {error ? <p className="form-error" role="alert">{error}</p> : null}

        <button className="button button-primary login-submit" type="submit" disabled={loading || configError}>
          {loading ? "확인 중…" : mode === "demo" ? "읽기 전용 데모 열기" : "로그인"}
          <ArrowRight size={17} />
        </button>
      </form>

      <p className="login-footnote">
        회원가입은 제공하지 않습니다. 계정 접근이 필요한 경우 Supabase 프로젝트 관리자에게 문의하세요.
      </p>
    </div>
  );
}
