"use client";

import { ArrowRight, LoaderCircle, LockKeyhole, Mail, UserRound } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";
import { getBrowserSupabase } from "@/lib/supabase/browser";
import type { RuntimeMode } from "@/lib/supabase/config";

function signupErrorMessage(error: { code?: string; message: string }) {
  switch (error.code) {
    case "email_address_invalid":
      return "실제로 메일을 받을 수 있는 유효한 이메일 주소를 입력해 주세요.";
    case "email_address_not_authorized":
      return "현재 인증 메일 설정에서는 이 주소로 메일을 보낼 수 없습니다. 관리자에게 문의해 주세요.";
    case "email_exists":
    case "user_already_exists":
      return "이미 가입된 이메일입니다. 로그인해 주세요.";
    case "over_email_send_rate_limit":
    case "over_request_rate_limit":
      return "인증 메일 요청이 너무 많습니다. 잠시 후 다시 시도해 주세요.";
    case "weak_password":
      return "비밀번호가 너무 약합니다. 영문과 숫자 등을 조합해 더 안전하게 설정해 주세요.";
    case "signup_disabled":
      return "현재 Viewer 회원가입이 일시적으로 중지되어 있습니다.";
    case "captcha_failed":
      return "보안 확인에 실패했습니다. 페이지를 새로고침한 뒤 다시 시도해 주세요.";
    default:
      return error.message.toLowerCase().includes("already registered")
        ? "이미 가입된 이메일입니다. 로그인해 주세요."
        : "회원가입을 완료하지 못했습니다. 잠시 후 다시 시도해 주세요.";
  }
}

export function SignupForm({ mode }: { mode: RuntimeMode }) {
  const router = useRouter();
  const [displayName, setDisplayName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [passwordConfirm, setPasswordConfirm] = useState("");
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [loading, setLoading] = useState(false);
  const configError = mode !== "supabase";

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setSuccess("");
    if (password.length < 8) {
      setError("비밀번호는 8자 이상 입력해 주세요.");
      return;
    }
    if (password !== passwordConfirm) {
      setError("비밀번호 확인이 일치하지 않습니다.");
      return;
    }

    const supabase = getBrowserSupabase();
    if (!supabase) {
      setError("Supabase 연결 설정을 확인해 주세요.");
      return;
    }

    setLoading(true);
    const { data, error: signupError } = await supabase.auth.signUp({
      email,
      password,
      options: {
        data: { display_name: displayName.trim() },
        emailRedirectTo: `${window.location.origin}/login`,
      },
    });
    setLoading(false);

    if (signupError) {
      setError(signupErrorMessage(signupError));
      return;
    }
    if (data.session) {
      router.replace("/dashboard");
      router.refresh();
      return;
    }
    setSuccess("인증 메일을 보냈습니다. 이메일 인증을 마치면 Viewer로 로그인할 수 있습니다.");
  }

  return (
    <div className="login-card">
      <div className="login-heading">
        <p className="eyebrow">VIEWER SIGN UP</p>
        <h2>Viewer 회원가입</h2>
        <p className="login-heading-description">가입 계정은 자동으로 읽기 전용 Viewer 권한만 받습니다.</p>
      </div>

      {configError ? (
        <div className="inline-alert alert-error" role="alert">
          Supabase 연결이 설정된 환경에서만 회원가입할 수 있습니다.
        </div>
      ) : null}
      {success ? <div className="inline-alert alert-demo" role="status">{success}</div> : null}

      <form className="login-form" onSubmit={submit}>
        <label className="field-label" htmlFor="display-name">이름</label>
        <div className="input-with-icon">
          <UserRound size={18} aria-hidden="true" />
          <input
            id="display-name"
            value={displayName}
            onChange={(event) => setDisplayName(event.target.value)}
            placeholder="표시 이름"
            autoComplete="name"
            maxLength={120}
            required
            disabled={configError || Boolean(success)}
          />
        </div>

        <label className="field-label" htmlFor="signup-email">이메일</label>
        <div className="input-with-icon">
          <Mail size={18} aria-hidden="true" />
          <input
            id="signup-email"
            type="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            placeholder="viewer@example.com"
            autoComplete="email"
            required
            disabled={configError || Boolean(success)}
          />
        </div>

        <label className="field-label" htmlFor="signup-password">비밀번호</label>
        <div className="input-with-icon">
          <LockKeyhole size={18} aria-hidden="true" />
          <input
            id="signup-password"
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            placeholder="8자 이상"
            autoComplete="new-password"
            minLength={8}
            required
            disabled={configError || Boolean(success)}
          />
        </div>

        <label className="field-label" htmlFor="signup-password-confirm">비밀번호 확인</label>
        <div className="input-with-icon">
          <LockKeyhole size={18} aria-hidden="true" />
          <input
            id="signup-password-confirm"
            type="password"
            value={passwordConfirm}
            onChange={(event) => setPasswordConfirm(event.target.value)}
            placeholder="비밀번호 다시 입력"
            autoComplete="new-password"
            minLength={8}
            required
            disabled={configError || Boolean(success)}
          />
        </div>

        {error ? <p className="form-error" role="alert">{error}</p> : null}

        <button
          className="button button-primary login-submit"
          type="submit"
          disabled={loading || configError || Boolean(success)}
          aria-busy={loading}
        >
          {loading ? (
            <><LoaderCircle className="login-button-spinner" size={17} aria-hidden="true" /> 가입 중…</>
          ) : (
            <>Viewer로 가입 <ArrowRight size={17} /></>
          )}
        </button>
      </form>

      <p className="auth-switch">
        이미 계정이 있나요? <Link href="/login">로그인</Link>
      </p>
      <p className="login-copyright">
        <span>© 2026 FinDone. All rights reserved.</span>
        <a href="mailto:qyurimoon@yonsei.ac.kr">Contact: qyurimoon@yonsei.ac.kr</a>
      </p>
    </div>
  );
}
