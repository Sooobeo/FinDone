import Link from "next/link";
import { ShieldX } from "lucide-react";

export default function UnauthorizedPage() {
  return (
    <main className="centered-page">
      <div className="centered-card">
        <span className="large-state-icon state-danger"><ShieldX size={28} /></span>
        <p className="eyebrow">ACCESS DENIED</p>
        <h1>관리자 권한이 없습니다</h1>
        <p>로그인한 계정이 FinDone 관리자 허용 목록에 등록되어 있지 않습니다.</p>
        <Link className="button button-primary" href="/login">로그인으로 돌아가기</Link>
      </div>
    </main>
  );
}
