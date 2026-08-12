"use client";

import { CloudDownload, DatabaseZap, LoaderCircle, Save, Search, ShieldCheck, Trash2, X } from "lucide-react";
import { useRouter } from "next/navigation";
import type { ReactNode } from "react";
import { useEffect, useMemo, useState } from "react";
import { glossaryConceptTypes, glossaryJurisdictions } from "@/lib/glossary";
import type { GlossaryWorkspace } from "@/lib/data";
import type { GlossaryTermItem } from "@/lib/types";
import { PageHeader } from "@/components/page-header";

interface GlossaryManagerProps extends GlossaryWorkspace {
  readOnly: boolean;
  viewerMode?: boolean;
}

function lines(value: string): string[] {
  return [...new Set(value.split(/\r?\n/).map((item) => item.trim()).filter(Boolean))];
}

function formatBytes(value: number | null): string {
  if (!value) return "-";
  if (value < 1024 * 1024) return `${Math.round(value / 1024)} KB`;
  return `${(value / (1024 * 1024)).toFixed(1)} MB`;
}

export function GlossaryManager({
  categories,
  sources,
  adminReferenceSources,
  terms: initialTerms,
  releases,
  jobs,
  readOnly,
  viewerMode = false,
}: GlossaryManagerProps) {
  const router = useRouter();
  const [terms, setTerms] = useState(initialTerms);
  const [query, setQuery] = useState("");
  const [categoryId, setCategoryId] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [draft, setDraft] = useState<GlossaryTermItem | null>(null);
  const [busy, setBusy] = useState<"save" | "delete" | "compile" | null>(null);
  const [message, setMessage] = useState("");
  const stable = releases.find((release) => release.stable);
  const latestJob = jobs[0];

  useEffect(() => {
    if (!latestJob || (latestJob.status !== "queued" && latestJob.status !== "running")) return;
    const interval = window.setInterval(() => router.refresh(), 3_000);
    return () => window.clearInterval(interval);
  }, [latestJob, router]);

  useEffect(() => setTerms(initialTerms), [initialTerms]);

  const filtered = useMemo(() => {
    const needle = query.trim().toLocaleLowerCase("ko");
    return terms.filter((term) => {
      if (categoryId && term.categoryId !== categoryId) return false;
      if (!needle) return true;
      return [
        term.termId,
        term.canonicalNameEn,
        term.canonicalNameKo,
        term.aliases.join(" "),
        term.oneLineDefinitionKo,
      ].some((value) => value.toLocaleLowerCase("ko").includes(needle));
    });
  }, [categoryId, query, terms]);

  function openEditor(term: GlossaryTermItem) {
    setSelectedId(term.termId);
    setDraft(structuredClone(term));
    setMessage("");
  }

  function update<K extends keyof GlossaryTermItem>(key: K, value: GlossaryTermItem[K]) {
    setDraft((current) => current ? { ...current, [key]: value } : current);
  }

  async function saveTerm() {
    if (!draft || readOnly || busy) return;
    setBusy("save");
    setMessage("");
    try {
      const response = await fetch(`/api/glossary/terms/${encodeURIComponent(draft.termId)}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(draft),
      });
      const payload = await response.json() as { term?: GlossaryTermItem; error?: string };
      if (!response.ok || !payload.term) throw new Error(payload.error || "용어 저장에 실패했습니다.");
      setTerms((current) => current.map((term) => term.termId === payload.term?.termId ? payload.term : term));
      setDraft(payload.term);
      setMessage("저장했습니다. 최신 변경이 포함된 용어집 컴파일도 대기열에 반영했습니다.");
      router.refresh();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "용어 저장에 실패했습니다.");
    } finally {
      setBusy(null);
    }
  }

  async function deleteTerm(termOverride?: GlossaryTermItem) {
    const target = termOverride ?? draft;
    if (!target || readOnly || busy) return;
    if (!window.confirm(`‘${target.canonicalNameEn}’을 용어집에서 삭제할까요?\n다음 stable DB부터 앱 검색에서도 사라집니다.`)) return;
    setBusy("delete");
    setMessage("");
    try {
      const response = await fetch(`/api/glossary/terms/${encodeURIComponent(target.termId)}`, { method: "DELETE" });
      const payload = await response.json() as { error?: string };
      if (!response.ok) throw new Error(payload.error || "용어 삭제에 실패했습니다.");
      setTerms((current) => current.filter((term) => term.termId !== target.termId));
      if (selectedId === target.termId) {
        setSelectedId(null);
        setDraft(null);
      }
      setMessage("용어를 보관 처리했습니다. 삭제본을 반영하는 새 DB 컴파일이 자동으로 큐에 등록됐습니다.");
      router.refresh();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "용어 삭제에 실패했습니다.");
    } finally {
      setBusy(null);
    }
  }

  async function compileGlossary() {
    if (readOnly || busy) return;
    setBusy("compile");
    setMessage("");
    try {
      const response = await fetch("/api/glossary/compile", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ releaseNotes: "Admin 수동 용어집 컴파일", minimumAppVersion: 1 }),
      });
      const payload = await response.json() as { error?: string; glossaryDbVersion?: number; coalesced?: boolean };
      if (!response.ok) throw new Error(payload.error || "컴파일 요청에 실패했습니다.");
      setMessage(
        payload.coalesced
          ? `기존 대기 중인 DB v${payload.glossaryDbVersion ?? "-"} 작업에 변경을 합쳤습니다.`
          : `용어집 DB v${payload.glossaryDbVersion ?? "-"} 컴파일을 대기열에 등록했습니다.`,
      );
      router.refresh();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "컴파일 요청에 실패했습니다.");
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="page-stack glossary-admin">
      <PageHeader
        eyebrow="OFFLINE DATABASE"
        title="용어집"
        description="앱 런타임에서는 LLM을 호출하지 않습니다. 여기서 확정한 용어만 SQLite FTS 팩으로 컴파일해 앱이 내려받습니다. PDF 원문과 내부 레퍼런스는 Admin에만 남습니다."
        actions={
          <button className="button-primary" type="button" onClick={compileGlossary} disabled={readOnly || Boolean(busy)}>
            {busy === "compile" ? <LoaderCircle className="spin" size={16} /> : <DatabaseZap size={16} />}
            용어 DB 컴파일
          </button>
        }
      />

      {viewerMode ? (
        <section className="panel glossary-viewer-note">
          <ShieldCheck size={24} />
          <div><strong>Owner 전용 데이터입니다.</strong><p>Viewer에게는 용어 설명과 원문 근거를 노출하지 않습니다.</p></div>
        </section>
      ) : null}

      <section className="glossary-metrics" aria-label="용어집 현황">
        <article className="panel"><span>활성 용어</span><strong>{terms.length.toLocaleString("ko-KR")}</strong><small>{categories.length}개 카테고리</small></article>
        <article className="panel"><span>Stable DB</span><strong>{stable ? `v${stable.glossaryDbVersion}` : "없음"}</strong><small>{stable ? `${stable.termCount.toLocaleString("ko-KR")}개 · ${formatBytes(stable.databaseByteSize)}` : "첫 컴파일 필요"}</small></article>
        <article className="panel"><span>최근 작업</span><strong>{latestJob?.status ?? "없음"}</strong><small>{latestJob ? `${latestJob.progressPercent}% · 시도 ${latestJob.attemptCount}` : "대기 작업 없음"}</small></article>
        <article className="panel"><span>공개 출처 코드</span><strong>{sources.length}</strong><small>PDF 원문 파일은 컴파일 제외</small></article>
      </section>

      {message ? <div className="glossary-message" role="status">{message}</div> : null}
      {latestJob?.errorMessage ? <div className="glossary-message glossary-message-error">{latestJob.errorMessage}</div> : null}

      <section className={`glossary-workspace ${draft ? "with-editor" : ""}`}>
        <div className="panel glossary-list-panel">
          <div className="glossary-toolbar">
            <label className="search-box">
              <Search size={16} />
              <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="한글·영문·약어·설명 검색" />
              {query ? <button type="button" onClick={() => setQuery("")} aria-label="검색어 지우기"><X size={14} /></button> : null}
            </label>
            <select value={categoryId} onChange={(event) => setCategoryId(event.target.value)} aria-label="카테고리">
              <option value="">전체 카테고리</option>
              {categories.map((category) => <option key={category.categoryId} value={category.categoryId}>{category.categoryId} · {category.name} ({category.termCount})</option>)}
            </select>
          </div>
          <div className="glossary-list-count">검색 결과 {filtered.length.toLocaleString("ko-KR")}개</div>
          <div className="glossary-term-list">
            {filtered.slice(0, 400).map((term) => (
              <div
                key={term.termId}
                className={`glossary-term-row ${term.termId === selectedId ? "active" : ""}`}
                role="button"
                tabIndex={0}
                onClick={() => openEditor(term)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault();
                    openEditor(term);
                  }
                }}
              >
                <span><small>{term.termId}</small><strong>{term.canonicalNameEn}</strong><em>{term.canonicalNameKo}</em></span>
                <p>{term.oneLineDefinitionKo}</p>
                <button
                  className="button-ghost-danger glossary-row-delete"
                  type="button"
                  onClick={(event) => {
                    event.stopPropagation();
                    void deleteTerm(term);
                  }}
                  disabled={readOnly || Boolean(busy)}
                  aria-label={`${term.canonicalNameEn} 삭제`}
                >
                  {busy === "delete" && selectedId === term.termId ? <LoaderCircle className="spin" size={15} /> : <Trash2 size={15} />}
                  삭제
                </button>
              </div>
            ))}
            {!filtered.length ? <div className="source-empty">조건에 맞는 용어가 없습니다.</div> : null}
          </div>
          {filtered.length > 400 ? <p className="list-limit-note">결과가 많아 앞 400개만 표시합니다. 검색어 또는 카테고리를 좁혀 주세요.</p> : null}
        </div>

        {draft ? (
          <aside className="panel glossary-editor">
            <header>
              <div><small>{draft.termId} · revision {draft.contentRevision}</small><h2>{draft.canonicalNameEn}</h2></div>
              <button className="icon-button" type="button" onClick={() => { setDraft(null); setSelectedId(null); }} aria-label="편집기 닫기"><X size={17} /></button>
            </header>
            <div className="glossary-editor-body">
              <div className="glossary-form-grid">
                <Field label="영문 표준명"><input value={draft.canonicalNameEn} onChange={(event) => update("canonicalNameEn", event.target.value)} disabled={readOnly} /></Field>
                <Field label="한글 표준명"><input value={draft.canonicalNameKo} onChange={(event) => update("canonicalNameKo", event.target.value)} disabled={readOnly} /></Field>
                <Field label="개념 유형"><select value={draft.conceptType} onChange={(event) => update("conceptType", event.target.value)} disabled={readOnly}>{glossaryConceptTypes.map((type) => <option key={type}>{type}</option>)}</select></Field>
                <Field label="검토 상태"><select value={draft.reviewStatus} onChange={(event) => update("reviewStatus", event.target.value as GlossaryTermItem["reviewStatus"])} disabled={readOnly}><option value="agent_reviewed">Agent 검토</option><option value="approved">Owner 승인</option></select></Field>
                <Field label="기준일"><input type="date" value={draft.asOfDate} onChange={(event) => update("asOfDate", event.target.value)} disabled={readOnly} /></Field>
              </div>
              <Field label="별칭" hint="한 줄에 하나"><textarea value={draft.aliases.join("\n")} onChange={(event) => update("aliases", lines(event.target.value))} disabled={readOnly} rows={3} /></Field>
              <Field label="한 문장 정의"><textarea value={draft.oneLineDefinitionKo} onChange={(event) => update("oneLineDefinitionKo", event.target.value)} disabled={readOnly} rows={3} /></Field>
              <Field label="핵심 의미"><textarea value={draft.coreDefinitionKo} onChange={(event) => update("coreDefinitionKo", event.target.value)} disabled={readOnly} rows={5} /></Field>
              <Field label="실무 문맥"><textarea value={draft.practicalContextKo} onChange={(event) => update("practicalContextKo", event.target.value)} disabled={readOnly} rows={4} /></Field>
              <Field label="왜 중요한가"><textarea value={draft.whyItMattersKo} onChange={(event) => update("whyItMattersKo", event.target.value)} disabled={readOnly} rows={3} /></Field>
              <Field label="예시"><textarea value={draft.exampleKo} onChange={(event) => update("exampleKo", event.target.value)} disabled={readOnly} rows={4} /></Field>
              <Field label="주의·한계" hint="한 줄에 하나"><textarea value={draft.limitationsKo.join("\n")} onChange={(event) => update("limitationsKo", lines(event.target.value))} disabled={readOnly} rows={4} /></Field>
              <Field label="검토 플래그" hint="한 줄에 하나 · 관할/다의어 등 추가 확인 항목"><textarea value={draft.reviewFlags.join("\n")} onChange={(event) => update("reviewFlags", lines(event.target.value))} disabled={readOnly} rows={3} /></Field>
              <div className="glossary-form-grid">
                <Field label="출처 코드" hint={sources.map((source) => source.sourceCode).join(", ")}><textarea value={draft.sourceCodes.join("\n")} onChange={(event) => update("sourceCodes", lines(event.target.value))} disabled={readOnly} rows={3} /></Field>
                <Field label="적용 관할"><select multiple value={draft.jurisdictions} onChange={(event) => update("jurisdictions", Array.from(event.target.selectedOptions, (option) => option.value))} disabled={readOnly}>{glossaryJurisdictions.map((item) => <option key={item}>{item}</option>)}</select></Field>
              </div>
              <Field label="Admin 전용 원문 레퍼런스" hint="기존 원본 자료에서 선택합니다. 이 연결과 PDF 파일은 앱 DB에 절대 포함되지 않습니다.">
                <select multiple value={draft.adminReferenceSourceIds} onChange={(event) => update("adminReferenceSourceIds", Array.from(event.target.selectedOptions, (option) => option.value))} disabled={readOnly}>
                  {adminReferenceSources.map((source) => <option key={source.sourceId} value={source.sourceId}>{source.label} · {source.kind}{source.sourceType ? ` · ${source.sourceType}` : ""}</option>)}
                </select>
              </Field>
              <Field label="관련 용어 ID" hint="한 줄에 하나"><textarea value={draft.relatedTermIds.join("\n")} onChange={(event) => update("relatedTermIds", lines(event.target.value))} disabled={readOnly} rows={3} /></Field>
              <Field label="공식 LaTeX"><textarea value={draft.formulaLatex} onChange={(event) => update("formulaLatex", event.target.value)} disabled={readOnly} rows={3} /></Field>
              <Field label="공식 설명"><textarea value={draft.formulaNotesKo} onChange={(event) => update("formulaNotesKo", event.target.value)} disabled={readOnly} rows={3} /></Field>
            </div>
            <footer>
              <button className="button-ghost-danger" type="button" onClick={() => void deleteTerm()} disabled={readOnly || Boolean(busy)}>{busy === "delete" ? <LoaderCircle className="spin" size={15} /> : <Trash2 size={15} />} 삭제</button>
              <button className="button-primary" type="button" onClick={saveTerm} disabled={readOnly || Boolean(busy)}>{busy === "save" ? <LoaderCircle className="spin" size={15} /> : <Save size={15} />} 저장</button>
            </footer>
          </aside>
        ) : null}
      </section>

      <section className="panel glossary-release-panel">
        <div className="panel-heading"><div><p className="panel-kicker">DISTRIBUTION</p><h2>독립 용어집 릴리스</h2></div><CloudDownload size={20} /></div>
        <p>Worker가 큐를 처리하면 검증된 <code>glossary.sqlite3</code>와 manifest만 private storage에 올리고 stable 채널을 교체합니다. 앱은 다음 실행 때 받아 원자적으로 설치합니다.</p>
        <div className="glossary-release-list">
          {releases.slice(0, 8).map((release) => <article key={release.releaseId}><strong>{release.versionName}{release.stable ? " · stable" : ""}</strong><span>{release.status} · {release.termCount.toLocaleString("ko-KR")}개 · {formatBytes(release.databaseByteSize)}</span></article>)}
          {!releases.length ? <small>아직 생성된 용어집 릴리스가 없습니다.</small> : null}
        </div>
      </section>
    </div>
  );
}

function Field({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return <label className="glossary-field"><span>{label}</span>{hint ? <small>{hint}</small> : null}{children}</label>;
}
