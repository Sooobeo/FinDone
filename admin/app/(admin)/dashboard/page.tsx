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
import { getConceptElements, getSources } from "@/lib/data";
import { packagedContentInfo } from "@/lib/packaged-info";

export const metadata: Metadata = { title: "대시보드" };

export default async function DashboardPage() {
  const [elements, sources] = await Promise.all([getConceptElements(), getSources()]);
  const domainCounts = Array.from(
    elements.reduce((map, element) => {
      const item = map.get(element.domainId) ?? { id: element.domainId, name: element.domainName, count: 0 };
      item.count += 1;
      map.set(element.domainId, item);
      return map;
    }, new Map<string, { id: string; name: string; count: number }>()).values(),
  );
  const maxDomainCount = Math.max(...domainCounts.map((domain) => domain.count), 1);
  const issueCount = elements.reduce((sum, element) => sum + element.issueCount, 0);

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="OVERVIEW"
        title="콘텐츠 운영 현황"
        description="현재 앱의 개념 DB를 기준으로 정리·검수·배포 상태를 한눈에 확인합니다."
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
          <div className="metric-value">{elements.length}<small>개</small></div>
          <p>7개 금융 분야의 앱 내장 콘텐츠</p>
          <span className="metric-detail">content-v{packagedContentInfo.version}</span>
        </article>
        <article className="metric-card">
          <div className="metric-icon icon-sand"><FileText size={20} /></div>
          <div className="metric-label">연결된 원본</div>
          <div className="metric-value">{sources.length}<small>건</small></div>
          <p>문서·웹 링크·공식 레퍼런스</p>
          <span className="metric-detail positive">근거 연결 완료</span>
        </article>
        <article className="metric-card">
          <div className="metric-icon icon-blue"><BookCheck size={20} /></div>
          <div className="metric-label">배포된 요소</div>
          <div className="metric-value">{elements.filter((item) => item.status === "published").length}<small>개</small></div>
          <p>현재 APK에서 읽는 콘텐츠</p>
          <span className="metric-detail positive">SQLite 무결성 통과</span>
        </article>
        <article className="metric-card">
          <div className="metric-icon icon-coral"><CircleAlert size={20} /></div>
          <div className="metric-label">확인할 항목</div>
          <div className="metric-value">{issueCount}<small>건</small></div>
          <p>현재 패키지 기준 자동 검증 결과</p>
          <Link className="metric-link" href="/validation">검증 화면 보기 <ArrowRight size={14} /></Link>
        </article>
      </section>

      <section className="dashboard-columns">
        <article className="panel domain-panel">
          <div className="panel-heading">
            <div>
              <p className="eyebrow">CONTENT COVERAGE</p>
              <h2>분야별 콘텐츠</h2>
            </div>
            <span className="panel-kicker">총 {elements.length}개</span>
          </div>
          <div className="domain-bars">
            {domainCounts.map((domain) => (
              <div className="domain-bar-row" key={domain.id}>
                <div className="domain-bar-label">
                  <span>{domain.name}</span>
                  <strong>{domain.count}</strong>
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
              <h2>Admin 도입 순서</h2>
            </div>
            <Sparkles size={19} className="subtle-icon" />
          </div>
          <ol className="workflow-list">
            <li className="workflow-complete">
              <span>1</span>
              <div><strong>현재 DB 가져오기</strong><p>{elements.length}개 요소와 {sources.length}개 출처 준비</p></div>
            </li>
            <li className="workflow-current">
              <span>2</span>
              <div><strong>개념·수식 정돈</strong><p>스프레드시트 화면에서 설명과 근거 검수</p></div>
            </li>
            <li>
              <span>3</span>
              <div><strong>오답 후보 정리</strong><p>요소별 선택지와 틀린 이유 승인</p></div>
            </li>
            <li>
              <span>4</span>
              <div><strong>앱 DB로 반영</strong><p>승인본만 SQLite 릴리스로 생성</p></div>
            </li>
          </ol>
        </article>
      </section>

      <section className="panel readiness-panel">
        <div className="readiness-copy">
          <span className="large-state-icon state-success"><PackageCheck size={25} /></span>
          <div>
            <p className="eyebrow">CURRENT BASELINE</p>
            <h2>앱 내장 DB를 기준점으로 고정했습니다</h2>
            <p>향후 수정은 원본을 덮어쓰지 않고 새 revision으로 남기며, 승인된 변경만 다음 콘텐츠 버전에 포함합니다.</p>
          </div>
        </div>
        <Link className="button button-secondary" href="/releases">릴리스 기준 보기 <ArrowRight size={16} /></Link>
      </section>
    </div>
  );
}
