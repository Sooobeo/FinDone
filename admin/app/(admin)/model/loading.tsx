import { LoaderCircle } from "lucide-react";

export default function ModelDashboardLoading() {
  return (
    <div className="page-stack">
      <section className="panel route-loading-state" role="status" aria-live="polite">
        <LoaderCircle className="spin" size={30} />
        <div><strong>로컬 모델 측정값 불러오는 중…</strong><p>학습 반영량·정확도·빌드 성능을 준비하고 있습니다.</p></div>
        <div className="route-loading-progress"><i /></div>
      </section>
    </div>
  );
}

