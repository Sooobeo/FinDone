import Link from "next/link";
import { ShieldX } from "lucide-react";

export default function UnauthorizedPage() {
  return (
    <main className="centered-page">
      <div className="centered-card">
        <span className="large-state-icon state-danger"><ShieldX size={28} /></span>
        <p className="eyebrow">ACCESS DENIED</p>
        <h1>계정 접근이 비활성화되었습니다</h1>
        <p>회원가입이 완료되지 않았거나 계정이 비활성 상태입니다. 이메일 인증 후 다시 로그인해 주세요.</p>
        <Link className="button button-primary" href="/login">로그인으로 돌아가기</Link>
      </div>
    </main>
  );
}
