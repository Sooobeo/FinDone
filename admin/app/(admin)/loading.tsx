import { LoaderCircle } from "lucide-react";

export default function AdminRouteLoading() {
  return (
    <div className="page-stack">
      <section className="panel route-loading-state" role="status" aria-live="polite">
        <LoaderCircle className="spin" size={30} />
        <div><strong>관리 데이터를 불러오는 중…</strong><p>현재 상태와 검증 결과를 준비하고 있습니다.</p></div>
        <div className="route-loading-progress"><i /></div>
      </section>
    </div>
  );
}
