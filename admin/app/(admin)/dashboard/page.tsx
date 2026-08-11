import type { Metadata } from "next";
import {
  ArrowRight,
  BookCheck,
  CircleAlert,
  Database,
  FileText,
  PackageCheck,
  Sparkles,
} from "lucide-react";
import Link from "next/link";
import { PageHeader } from "@/components/page-header";
import { getAdminContext } from "@/lib/auth";
import { getConceptElements, getReviewWorkspace, getSources } from "@/lib/data";
import { packagedContentInfo } from "@/lib/packaged-info";
import { viewerConceptElements, viewerReviewWorkspace, viewerSources } from "@/lib/viewer-placeholders";

export const metadata: Metadata = { title: "대시보드" };

export default async function DashboardPage() {
  const context = await getAdminContext();
  const viewer = context.role === "viewer";
  const [elements, sources, reviewWorkspace] = viewer
    ? [viewerConceptElements, viewerSources, viewerReviewWorkspace]
    : await Promise.all([getConceptElements(), getSources(), getReviewWorkspace()]);
  const domainCounts = viewer
    ? [
        { id: "FIELD-1", name: "분야 ID와 표시 이름", count: 100 },
        { id: "FIELD-2", name: "분야별 학습요소 구성", count: 100 },
        { id: "FIELD-3", name: "개념·계산 유형 구분", count: 100 },
        { id: "FIELD-4", name: "원본 근거 연결 상태", count: 100 },
        { id: "FIELD-5", name: "자동 검증 결과", count: 100 },
        { id: "FIELD-6", name: "승인·배포 상태", count: 100 },
        { id: "FIELD-7", name: "앱 콘텐츠 버전", count: 100 },
      ]
    : Array.from(
        elements.reduce((map, element) => {
          const item = map.get(element.domainId) ?? { id: element.domainId, name: element.domainName, count: 0 };
          item.count += 1;
          map.set(element.domainId, item);
          return map;
        }, new Map<string, { id: string; name: string; count: number }>()).values(),
      );
  const maxDomainCount = Math.max(...domainCounts.map((domain) => domain.count), 1);
  const issueCount = elements.reduce((sum, element) => sum + element.issueCount, 0);
  const finalReviewCount = reviewWorkspace.batches.filter((batch) => batch.status === "ready_for_review").length;

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="OVERVIEW"
        title={viewer ? "콘텐츠 운영 구조" : "콘텐츠 운영 현황"}
        description={viewer ? "Owner 대시보드와 같은 위치에서 각 요약 박스에 어떤 DB 정보가 표시되는지 설명합니다." : "현재 앱의 개념 DB를 기준으로 정리·검수·배포 상태를 한눈에 확인합니다."}
        actions={
          <Link className="button button-primary" href="/concepts">
            개념 DB 열기 <ArrowRight size={16} />
          </Link>
        }
      />

      <section className="metric-grid" aria-label="콘텐츠 요약">
        <article className="metric-card metric-card-featured">
          <div className="metric-icon"><Database size={20} /></div>
          <div className="metric-label">전체 학습 요소</div>
          <div className="metric-value">{viewer ? "요소 수" : elements.length}<small>{viewer ? "" : "개"}</small></div>
          <p>{viewer ? "분야에 포함된 학습 단위의 총개수" : "7개 금융 분야의 앱 내장 콘텐츠"}</p>
          <span className="metric-detail">{viewer ? "콘텐츠 버전이 표시되는 위치" : `content-v${packagedContentInfo.version}`}</span>
        </article>
        <article className="metric-card">
          <div className="metric-icon icon-sand"><FileText size={20} /></div>
          <div className="metric-label">연결된 원본</div>
          <div className="metric-value">{viewer ? "원본 수" : sources.length}<small>{viewer ? "" : "건"}</small></div>
          <p>{viewer ? "문서·웹·공식 레퍼런스의 등록 건수" : "문서·웹 링크·공식 레퍼런스"}</p>
          <span className="metric-detail positive">{viewer ? "근거 연결 상태가 표시되는 위치" : "근거 연결 완료"}</span>
        </article>
        <article className="metric-card">
          <div className="metric-icon icon-blue"><BookCheck size={20} /></div>
          <div className="metric-label">배포된 요소</div>
          <div className="metric-value">{viewer ? "승인 수" : elements.filter((item) => item.status === "published").length}<small>{viewer ? "" : "개"}</small></div>
          <p>{viewer ? "승인되어 앱 반영 대상이 된 요소 수" : "현재 APK에서 읽는 콘텐츠"}</p>
          <span className="metric-detail positive">{viewer ? "DB 무결성 상태가 표시되는 위치" : "SQLite 무결성 통과"}</span>
        </article>
        <article className="metric-card">
          <div className="metric-icon icon-coral"><CircleAlert size={20} /></div>
          <div className="metric-label">최종 검토 대기</div>
          <div className="metric-value">{viewer ? "배치 수" : finalReviewCount}<small>{viewer ? "" : "건"}</small></div>
          <p>{viewer ? "자동 생성·검증을 끝낸 앱 DB 후보 수" : issueCount ? `기존 편집 이슈 ${issueCount}건 · 자동 배치는 별도 검증` : "근거·형식 자동 검증을 통과한 배치"}</p>
          <Link className="metric-link" href="/review">최종 검토 보기 <ArrowRight size={14} /></Link>
        </article>
      </section>

      <section className="dashboard-columns">
        <article className="panel domain-panel">
          <div className="panel-heading">
            <div>
              <p className="eyebrow">CONTENT COVERAGE</p>
              <h2>분야별 콘텐츠</h2>
            </div>
            <span className="panel-kicker">{viewer ? "구성 항목 안내" : `총 ${elements.length}개`}</span>
          </div>
          <div className="domain-bars">
            {domainCounts.map((domain) => (
              <div className="domain-bar-row" key={domain.id}>
                <div className="domain-bar-label">
                  <span>{domain.name}</span>
                  <strong>{viewer ? "설명" : domain.count}</strong>
                </div>
                <div className="progress-track">
                  <span style={{ width: `${Math.max((domain.count / maxDomainCount) * 100, 4)}%` }} />
                </div>
              </div>
            ))}
          </div>
        </article>

        <article className="panel workflow-panel">
          <div className="panel-heading">
            <div>
              <p className="eyebrow">NEXT STEPS</p>
              <h2>자동 앱 DB 반영 순서</h2>
            </div>
            <Sparkles size={19} className="subtle-icon" />
          </div>
          <ol className="workflow-list">
            <li className="workflow-complete">
              <span>1</span>
              <div><strong>기존 앱 DB 기준점</strong><p>{viewer ? "학습요소와 원본 근거를 준비하는 단계" : `${elements.length}개 요소와 ${sources.length}개 출처 준비`}</p></div>
            </li>
            <li className="workflow-current">
              <span>2</span>
              <div><strong>원본 자동 가공·콘텐츠 생성</strong><p>fragment 추출, 근거 연결, 구조화 생성과 자동 수정</p></div>
            </li>
            <li>
              <span>3</span>
              <div><strong>최종 검토 후 자동 릴리스</strong><p>승인 한 번으로 클린 SQLite 검증·stable 공개</p></div>
            </li>
          </ol>
        </article>
      </section>

      <section className="panel readiness-panel">
        <div className="readiness-copy">
          <span className="large-state-icon state-success"><PackageCheck size={25} /></span>
          <div>
            <p className="eyebrow">CURRENT BASELINE</p>
            <h2>{viewer ? "콘텐츠 기준점과 revision 정책" : "앱 내장 DB를 기준점으로 고정했습니다"}</h2>
            <p>{viewer ? "기준 DB, revision 이력과 다음 릴리스 포함 여부를 설명하는 영역입니다." : "향후 수정은 원본을 덮어쓰지 않고 새 revision으로 남기며, 승인된 변경만 다음 콘텐츠 버전에 포함합니다."}</p>
          </div>
        </div>
        <Link className="button button-secondary" href="/releases">릴리스 기준 보기 <ArrowRight size={16} /></Link>
      </section>
    </div>
  );
}
