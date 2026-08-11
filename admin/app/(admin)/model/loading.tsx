import { LoaderCircle } from "lucide-react";

export default function ModelDashboardLoading() {
  return (
    <div className="page-stack">
      <section className="panel route-loading-state" role="status" aria-live="polite">
        <LoaderCircle className="spin" size={30} />
        <div><strong>로컬 모델 실험 기록 불러오는 중…</strong><p>임베딩 비교·랭커 성능·사람 검토율·릴리스 게이트를 준비하고 있습니다.</p></div>
        <div className="route-loading-progress"><i /></div>
      </section>
    </div>
  );
}
