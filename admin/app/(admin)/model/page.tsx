import type { Metadata } from "next";
import {
  Activity,
  CheckCircle2,
  Clock3,
  Cpu,
  Database,
  FileCheck2,
  Gauge,
  GitCompareArrows,
  Globe2,
  Layers3,
  Network,
  ShieldCheck,
} from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { getLocalModelOperationalMetrics } from "@/lib/data";
import { localModelReport } from "@/lib/local-model-report";

export const metadata: Metadata = { title: "로컬 모델 현황" };

function percent(value: number) {
  return `${(value * 100).toFixed(value === 1 ? 0 : 1)}%`;
}

function metric(value: number | boolean) {
  if (typeof value === "boolean") return value ? "통과" : "실패";
  return percent(value);
}

function bytes(value: number) {
  return `${(value / 1024).toLocaleString("ko-KR", { maximumFractionDigits: 0 })} KB`;
}

export default async function ModelDashboardPage() {
  const report = localModelReport;
  const runtime = await getLocalModelOperationalMetrics();
  const training = report.training;
  const evaluation = report.evaluation;
  const performance = report.performance;
  const maxCorpusCount = Math.max(
    training.reviewedElementCount,
    training.cataloguedSourceCount,
    training.sourceReferenceCount,
    1,
  );
  const corpusRows = [
    { label: "검토 완료 앱 요소", value: training.reviewedElementCount, icon: FileCheck2 },
    { label: "카탈로그 출처", value: training.cataloguedSourceCount, icon: Layers3 },
    { label: "요소↔출처 연결", value: training.sourceReferenceCount, icon: Network },
    { label: "웹 출처", value: training.cataloguedWebSourceCount, icon: Globe2 },
  ];
  const learningRows = [
    { label: "코퍼스 커버리지", value: training.corpusCoverage },
    { label: "앱 필수 필드 완성률", value: training.requiredFieldCoverage },
    { label: "출처 추적률", value: training.sourceTraceability },
    { label: "골든셋 필드 정확도", value: evaluation.fieldAccuracy },
    { label: "복수 출처 교차검증", value: training.multipleSourceCoverage },
  ];
  const generatedAt = new Intl.DateTimeFormat("ko-KR", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: "Asia/Seoul",
  }).format(new Date(report.generatedAt));

  return (
    <div className="page-stack local-model-dashboard">
      <PageHeader
        eyebrow="LOCAL CONTENT MODEL"
        title="로컬 모델 현황"
        description="외부 LLM API 없이 코드에 고정된 변환 규칙의 학습 반영량, 정확도, 처리 성능과 품질 게이트를 확인합니다."
        actions={
          <span className={`model-health-badge ${report.status === "passed" ? "passed" : "failed"}`}>
            <ShieldCheck size={15} /> {report.status === "passed" ? "릴리스 게이트 통과" : "릴리스 차단"}
          </span>
        }
      />

      <section className="panel model-readiness-hero">
        <div className="model-score-block">
          <span className="model-score-icon"><Cpu size={25} /></span>
          <div>
            <p className="eyebrow">MODEL READINESS</p>
            <strong>{training.readinessScore.toFixed(1)}<small>/100</small></strong>
            <p>로컬 규칙 모델 준비도</p>
          </div>
        </div>
        <div className="model-readiness-track" role="progressbar" aria-label="로컬 모델 준비도" aria-valuemin={0} aria-valuemax={100} aria-valuenow={training.readinessScore}>
          <span style={{ width: `${training.readinessScore}%` }} />
        </div>
        <div className="model-version-block">
          <small>규칙 버전</small>
          <code>{report.model.version}</code>
          <span>외부 LLM API 호출 {report.model.externalLlmApiCalls}회</span>
        </div>
      </section>

      <section className="model-metric-grid" aria-label="로컬 모델 핵심 지표">
        <article className="panel model-metric-card">
          <span><Database size={19} /></span>
          <small>학습 반영 DB</small>
          <strong>{training.reviewedContentDatabaseCount}<em>개</em></strong>
          <p>검토 완료 요소 {training.reviewedElementCount}개 · {training.domainCount}개 분야</p>
        </article>
        <article className="panel model-metric-card">
          <span><Gauge size={19} /></span>
          <small>학습률</small>
          <strong>{percent(training.corpusCoverage)}</strong>
          <p>현재 목표 135개 중 {training.reviewedElementCount}개 규칙·스키마 반영</p>
        </article>
        <article className="panel model-metric-card">
          <span><GitCompareArrows size={19} /></span>
          <small>골든셋 성능</small>
          <strong>{percent(evaluation.fieldAccuracy)}</strong>
          <p>{evaluation.passedFieldAssertions}/{evaluation.fieldAssertionCount} 필드 · 95% 보수 하한 {percent(evaluation.fieldAccuracyWilson95LowerBound)}</p>
        </article>
        <article className="panel model-metric-card">
          <span><Activity size={19} /></span>
          <small>앱 DB 빌드 성능</small>
          <strong>{performance.medianBuildMs.toFixed(0)}<em>ms</em></strong>
          <p>초당 {performance.elementsPerSecond.toLocaleString("ko-KR")}개 요소 처리</p>
        </article>
      </section>

      <section className="panel model-runtime-strip" aria-label="운영 로컬 모델 누적 지표">
        <div>
          <p className="eyebrow">OPERATIONAL FEEDBACK</p>
          <h2>{runtime.connected ? "운영 누적 측정" : "운영 DB 연결 전"}</h2>
          <p>{runtime.measurementAvailable ? "최종 검토 파이프라인에서 실시간 집계한 값입니다." : "로컬 코퍼스 측정은 위에 표시되며, Supabase 연결 후 운영 누적값이 활성화됩니다."}</p>
        </div>
        <dl>
          <div><dt>추가 구조화 원본</dt><dd>{runtime.structuredSourceFileCount}<small>개</small></dd></div>
          <div><dt>로컬 변환 배치</dt><dd>{runtime.processedBatchCount}<small>건</small></dd></div>
          <div><dt>변환 필드 묶음</dt><dd>{runtime.transformedItemCount}<small>건</small></dd></div>
          <div><dt>사람 승인 피드백</dt><dd>{runtime.approvedFeedbackCount}<small>건</small></dd></div>
          <div><dt>규칙 실행 기록</dt><dd>{runtime.localExecutionCount}<small>회</small></dd></div>
        </dl>
      </section>

      <section className="model-dashboard-columns">
        <article className="panel model-corpus-panel">
          <div className="panel-heading">
            <div><p className="eyebrow">CORPUS SIZE</p><h2>학습 반영 데이터 양</h2></div>
            <span className="panel-kicker">구조화 JSON {training.structuredLearningCopyFileCount}개</span>
          </div>
          <div className="model-corpus-bars">
            {corpusRows.map(({ label, value, icon: Icon }) => (
              <div className="model-corpus-row" key={label}>
                <span><Icon size={15} /> {label}</span>
                <strong>{value.toLocaleString("ko-KR")}</strong>
                <div><i style={{ width: `${Math.max(4, value / maxCorpusCount * 100)}%` }} /></div>
              </div>
            ))}
          </div>
          <p className="model-panel-note">웹 {training.cataloguedWebSourceCount}건은 출처 카탈로그 양입니다. 실제 자동 변환은 요소 ID와 필드가 명시된 구조화 fragment만 반영합니다.</p>
        </article>

        <article className="panel model-learning-panel">
          <div className="panel-heading">
            <div><p className="eyebrow">LEARNING RATE</p><h2>학습률 구성</h2></div>
            <span className="panel-kicker">가중 준비도 {training.readinessScore.toFixed(1)}%</span>
          </div>
          <div className="model-learning-list">
            {learningRows.map((row) => (
              <div key={row.label}>
                <span>{row.label}</span><strong>{percent(row.value)}</strong>
                <div role="progressbar" aria-label={row.label} aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(row.value * 100)}>
                  <i style={{ width: `${row.value * 100}%` }} />
                </div>
              </div>
            ))}
          </div>
          <p className="model-panel-note">{training.metricDefinition}</p>
        </article>
      </section>

      <section className="model-dashboard-columns model-dashboard-lower">
        <article className="panel model-gates-panel">
          <div className="panel-heading">
            <div><p className="eyebrow">QUALITY GATES</p><h2>릴리스 차단 검사</h2></div>
            <ShieldCheck size={19} className="subtle-icon" />
          </div>
          <div className="model-gate-list">
            {evaluation.qualityGates.map((gate) => (
              <div key={gate.id}>
                <span className={gate.passed ? "passed" : "failed"}>{gate.passed ? <CheckCircle2 size={15} /> : <Activity size={15} />}</span>
                <div><strong>{gate.label}</strong><small>측정 {metric(gate.measured)} · 기준 {metric(gate.threshold)}</small></div>
                <b>{gate.passed ? "PASS" : "BLOCK"}</b>
              </div>
            ))}
          </div>
        </article>

        <article className="panel model-performance-panel">
          <div className="panel-heading">
            <div><p className="eyebrow">RUNTIME PERFORMANCE</p><h2>실측 빌드 성능</h2></div>
            <Clock3 size={19} className="subtle-icon" />
          </div>
          <dl className="model-performance-list">
            <div><dt>반복 측정</dt><dd>{performance.benchmarkRounds}회</dd></div>
            <div><dt>중앙 빌드 시간</dt><dd>{performance.medianBuildMs.toFixed(2)} ms</dd></div>
            <div><dt>최소–최대</dt><dd>{performance.minimumBuildMs.toFixed(2)}–{performance.maximumBuildMs.toFixed(2)} ms</dd></div>
            <div><dt>처리량</dt><dd>{performance.elementsPerSecond.toLocaleString("ko-KR")} 요소/s</dd></div>
            <div><dt>앱 DB 크기</dt><dd>{bytes(performance.databaseByteSize)}</dd></div>
            <div><dt>결정론 빌드</dt><dd>{evaluation.deterministicBuild ? "SHA 일치" : "불일치"}</dd></div>
          </dl>
        </article>
      </section>

      <section className="panel model-build-proof">
        <span><CheckCircle2 size={23} /></span>
        <div>
          <p className="eyebrow">LATEST MEASUREMENT</p>
          <h2>content-v{report.content.contentDbVersion} · 필수 필드 {report.content.resolvedRequiredFieldCount.toLocaleString("ko-KR")}/{report.content.requiredFieldCount.toLocaleString("ko-KR")}</h2>
          <p>{generatedAt} 측정 · SQLite SHA-256</p>
          <code>{performance.databaseSha256}</code>
        </div>
        <div className="model-adapter-list">
          {report.model.supportedAdapters.map((adapter) => <span key={adapter}>{adapter}</span>)}
        </div>
      </section>
    </div>
  );
}
