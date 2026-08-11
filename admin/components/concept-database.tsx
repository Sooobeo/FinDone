"use client";

import {
  Check,
  ChevronDown,
  Columns3,
  Download,
  FileSpreadsheet,
  Filter,
  PanelRightClose,
  PanelRightOpen,
  Search,
  Upload,
  X,
} from "lucide-react";
import { ChangeEvent, useMemo, useRef, useState } from "react";
import { PageHeader } from "@/components/page-header";
import { StatusBadge } from "@/components/status-badge";
import { ConceptCsvError, conceptsFromCsv, conceptsToCsv } from "@/lib/csv";
import type { ConceptElement, ContentStatus } from "@/lib/types";
import { filterConcepts, validateConcept } from "@/lib/validation";

type EditorTab = "concept" | "formula" | "source";

interface ConceptDatabaseProps {
  initialElements: ConceptElement[];
  readOnly: boolean;
  viewerMode?: boolean;
}

const fieldLabels: Partial<Record<keyof ConceptElement, string>> = {
  definition: "한 문장 정의",
  intuition: "쉽게 이해하기",
  elementScopeNotes: "원본 요소 범위·생성 메모",
  scopeNotes: "적용 유형",
  coreRelation: "원본 핵심 관계",
  formulaExpression: "핵심 공식",
  formulaAssumptions: "공식 적용 조건",
  formulaNotes: "공식 보조 설명",
  checklist: "실무에서 쓰이는 경우",
  sourceLabel: "출처명",
  sourceLocator: "출처 URL·위치",
  specSectionLocator: "원본 명세 위치",
};

function textPreview(value: string, limit = 88) {
  const clean = value.replace(/[#*$`\n]+/g, " ").replace(/\s+/g, " ").trim();
  return clean.length > limit ? `${clean.slice(0, limit)}…` : clean;
}

export function ConceptDatabase({ initialElements, readOnly, viewerMode = false }: ConceptDatabaseProps) {
  const [elements, setElements] = useState(initialElements);
  const [query, setQuery] = useState("");
  const [domain, setDomain] = useState("all");
  const [status, setStatus] = useState("all");
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [selectedId, setSelectedId] = useState(initialElements[0]?.elementId ?? "");
  const [drawerOpen, setDrawerOpen] = useState(true);
  const [editorTab, setEditorTab] = useState<EditorTab>("concept");
  const [draft, setDraft] = useState<ConceptElement | null>(initialElements[0] ?? null);
  const [message, setMessage] = useState("");
  const [importing, setImporting] = useState(false);
  const importRef = useRef<HTMLInputElement>(null);

  const domains = useMemo(
    () => Array.from(new Map(elements.map((item) => [item.domainId, item.domainName])).entries()),
    [elements],
  );
  const filtered = useMemo(
    () => filterConcepts(elements, query, domain, status),
    [elements, query, domain, status],
  );
  const validation = useMemo(() => (draft ? validateConcept(draft) : []), [draft]);
  const dirty = Boolean(
    draft && JSON.stringify(draft) !== JSON.stringify(elements.find((item) => item.elementId === selectedId)),
  );

  function openElement(element: ConceptElement) {
    if (dirty && !window.confirm("저장하지 않은 변경을 버리고 다른 요소를 여시겠습니까?")) return;
    setSelectedId(element.elementId);
    setDraft(element);
    setDrawerOpen(true);
    setEditorTab("concept");
    setMessage("");
  }

  function updateField(field: keyof ConceptElement, value: string) {
    setDraft((current) => (current ? { ...current, [field]: value } : current));
  }

  function toggleSelected(id: string) {
    setSelectedIds((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function toggleAll() {
    setSelectedIds((current) =>
      filtered.every((item) => current.has(item.elementId))
        ? new Set()
        : new Set(filtered.map((item) => item.elementId)),
    );
  }

  function exportCsv() {
    if (readOnly) return;
    const selected = selectedIds.size
      ? elements.filter((element) => selectedIds.has(element.elementId))
      : filtered;
    const blob = new Blob([conceptsToCsv(selected)], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = "findone-concepts.csv";
    anchor.click();
    URL.revokeObjectURL(url);
    setMessage(`${selected.length}개 요소를 CSV로 내보냈습니다.`);
  }

  async function importFile(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    event.target.value = "";
    if (dirty) {
      setMessage("먼저 열려 있는 요소의 변경을 저장하거나 되돌려 주세요.");
      return;
    }
    if (!file.name.toLocaleLowerCase("en-US").endsWith(".csv")) {
      setMessage("Excel에서 UTF-8 CSV로 저장한 파일만 가져올 수 있습니다.");
      return;
    }
    setImporting(true);
    try {
      const imported = conceptsFromCsv(await file.text(), elements);
      if (!imported.changed.length) {
        setMessage(`${imported.rowCount}개 행을 확인했습니다. 달라진 내용이 없습니다.`);
        return;
      }
      const errors = imported.changed.flatMap((element) =>
        validateConcept(element)
          .filter((issue) => issue.severity === "error")
          .map((issue) => `${element.elementId}: ${issue.message}`),
      );
      if (errors.length) {
        setMessage(`가져오기 중단: ${errors[0]}`);
        return;
      }
      if (readOnly) {
        setMessage(`${imported.rowCount}개 행 중 ${imported.changed.length}개 변경을 찾았습니다. 데모에서는 서버에 저장하지 않습니다.`);
        return;
      }
      if (!window.confirm(`${imported.changed.length}개 요소를 하나의 원자적 CSV 작업으로 저장하시겠습니까?`)) {
        setMessage("CSV 가져오기를 취소했습니다.");
        return;
      }
      setMessage(`${imported.changed.length}개 요소 저장 중…`);
      const response = await fetch("/api/concepts/import", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ elements: imported.changed }),
      });
      const result = (await response.json()) as { error?: string };
      if (!response.ok) {
        setMessage(result.error ?? "CSV 변경을 저장하지 못했습니다.");
        return;
      }
      const savedById = new Map(imported.changed.map((element) => [
        element.elementId,
        { ...element, status: "draft" as ContentStatus },
      ]));
      setElements((current) => current.map((element) => savedById.get(element.elementId) ?? element));
      setDraft((current) => current ? savedById.get(current.elementId) ?? current : current);
      setMessage(`${imported.changed.length}개 요소를 revision으로 저장했습니다.`);
    } catch (error) {
      setMessage(error instanceof ConceptCsvError ? error.message : "CSV를 읽는 중 오류가 발생했습니다.");
    } finally {
      setImporting(false);
    }
  }

  async function saveDraft() {
    if (!draft || readOnly || validation.some((issue) => issue.severity === "error")) return;
    setMessage("저장 중…");
    const response = await fetch(`/api/concepts/${encodeURIComponent(draft.elementId)}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(draft),
    });
    const result = (await response.json()) as { error?: string };
    if (!response.ok) {
      setMessage(result.error ?? "저장하지 못했습니다.");
      return;
    }
    const savedDraft = { ...draft, status: "draft" as ContentStatus };
    setDraft(savedDraft);
    setElements((current) => current.map((item) => (item.elementId === draft.elementId ? savedDraft : item)));
    setMessage("새 revision으로 저장했습니다.");
  }

  return (
    <div className="page-stack concept-page">
      <PageHeader
        eyebrow="CONTENT DATABASE"
        title="개념 DB"
        description={viewerMode
          ? "Owner 화면과 같은 표·상세 패널에서 개념 DB를 구성하는 필드만 설명합니다. 실제 DB 값은 표시하지 않습니다."
          : readOnly
          ? "현재 앱의 모든 요소와 설명을 검색하고 조회합니다."
          : "현재 앱의 모든 요소와 설명을 스프레드시트처럼 찾고, 수정하고, 검수합니다."}
        actions={
          <>
            {viewerMode ? (
              <button className="button button-secondary" type="button" disabled>
                <Upload size={16} /> Excel CSV 가져오기
              </button>
            ) : !readOnly ? (
              <>
                <input
                  ref={importRef}
                  className="visually-hidden"
                  type="file"
                  accept=".csv,text/csv"
                  onChange={importFile}
                  tabIndex={-1}
                />
                <button className="button button-secondary" type="button" disabled={importing} onClick={() => importRef.current?.click()} title="Excel에서 UTF-8 CSV로 저장한 파일">
                  <Upload size={16} /> {importing ? "CSV 확인 중…" : "Excel CSV 가져오기"}
                </button>
              </>
            ) : null}
            {viewerMode ? (
              <button className="button button-primary" type="button" disabled>
                <Download size={16} /> 내보내기
              </button>
            ) : !readOnly ? (
              <button className="button button-primary" type="button" onClick={exportCsv}>
                <Download size={16} /> 내보내기
              </button>
            ) : null}
          </>
        }
      />

      <section className="concept-workspace" aria-label={readOnly ? "개념 데이터베이스 뷰어" : "개념 데이터베이스 편집기"}>
        <div className={`concept-grid-panel ${drawerOpen ? "with-editor" : ""}`}>
          <div className="table-toolbar">
            <label className="search-box">
              <Search size={17} aria-hidden="true" />
              <span className="visually-hidden">개념 검색</span>
              <input
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="요소 ID, 개념명, 설명 검색"
              />
              {query ? (
                <button type="button" onClick={() => setQuery("")} aria-label="검색어 지우기"><X size={15} /></button>
              ) : null}
            </label>
            <div className="filter-group">
              <label className="select-wrap">
                <Filter size={15} aria-hidden="true" />
                <span className="visually-hidden">분야 필터</span>
                <select value={domain} onChange={(event) => setDomain(event.target.value)}>
                  <option value="all">모든 분야</option>
                  {domains.map(([id, name]) => <option key={id} value={id}>{name}</option>)}
                </select>
                <ChevronDown size={14} aria-hidden="true" />
              </label>
              <label className="select-wrap">
                <span className="visually-hidden">상태 필터</span>
                <select value={status} onChange={(event) => setStatus(event.target.value)}>
                  <option value="all">모든 상태</option>
                  <option value="draft">초안</option>
                  <option value="reviewed">검토 완료</option>
                  <option value="approved">승인</option>
                  <option value="published">배포됨</option>
                </select>
                <ChevronDown size={14} aria-hidden="true" />
              </label>
              <button className="icon-button" type="button" aria-label="표시 열 설정" disabled><Columns3 size={17} /></button>
              <button
                className="icon-button"
                type="button"
                onClick={() => setDrawerOpen((open) => !open)}
                aria-label={drawerOpen ? "편집 패널 닫기" : "편집 패널 열기"}
              >
                {drawerOpen ? <PanelRightClose size={17} /> : <PanelRightOpen size={17} />}
              </button>
            </div>
          </div>

          <div className="table-summary">
            <span>{viewerMode ? <><strong>{filtered.length}</strong>개 구성 필드 설명</> : <><strong>{filtered.length}</strong> / {elements.length}개 요소</>}</span>
            {selectedIds.size ? <span className="selected-summary">{selectedIds.size}개 선택됨</span> : null}
            {message ? <span className="table-message" role="status">{message}</span> : null}
          </div>

          <div className="data-table-scroll">
            <table className="data-table concept-table">
              <thead>
                <tr>
                  <th className="checkbox-cell">
                    <input
                      type="checkbox"
                      checked={filtered.length > 0 && filtered.every((item) => selectedIds.has(item.elementId))}
                      onChange={toggleAll}
                      aria-label="현재 결과 전체 선택"
                    />
                  </th>
                  <th>요소 ID</th>
                  <th>분야</th>
                  <th>요소명</th>
                  <th>핵심 관계</th>
                  <th>정의</th>
                  <th>상태</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((element) => (
                  <tr key={element.elementId} className={selectedId === element.elementId ? "active-row" : ""}>
                    <td className="checkbox-cell">
                      <input
                        type="checkbox"
                        checked={selectedIds.has(element.elementId)}
                        onChange={() => toggleSelected(element.elementId)}
                        aria-label={`${element.elementId} 선택`}
                      />
                    </td>
                    <td><span className="mono-id">{element.elementId}</span></td>
                    <td><span className={`domain-chip domain-${element.domainId.toLowerCase()}`}>{element.domainName}</span></td>
                    <td>
                      <button className="table-title-button" type="button" onClick={() => openElement(element)}>
                        {element.title}
                      </button>
                    </td>
                    <td><span className="cell-preview">{textPreview(element.coreRelation, 62)}</span></td>
                    <td><span className="cell-preview">{textPreview(element.definition, 66)}</span></td>
                    <td><StatusBadge status={element.status} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
            {filtered.length === 0 ? (
              <div className="table-empty">
                <FileSpreadsheet size={23} />
                <strong>조건에 맞는 요소가 없습니다</strong>
                <p>검색어나 필터를 바꿔 보세요.</p>
              </div>
            ) : null}
          </div>
        </div>

        {drawerOpen && draft ? (
          <aside className="editor-drawer" aria-label={`${draft.elementId} ${readOnly ? "상세 보기" : "편집"}`}>
            <div className="editor-heading">
              <div>
                <div className="editor-id-line">
                  <span className="mono-id">{draft.elementId}</span>
                  <StatusBadge status={draft.status} />
                </div>
                <h2>{draft.title}</h2>
                <p>{draft.domainName}</p>
              </div>
              <button className="icon-button" type="button" onClick={() => setDrawerOpen(false)} aria-label="편집 패널 닫기">
                <X size={18} />
              </button>
            </div>

            <div className="editor-tabs" role="tablist" aria-label="편집 영역">
              {(["concept", "formula", "source"] as EditorTab[]).map((tab) => (
                <button
                  key={tab}
                  type="button"
                  role="tab"
                  aria-selected={editorTab === tab}
                  className={editorTab === tab ? "editor-tab active" : "editor-tab"}
                  onClick={() => setEditorTab(tab)}
                >
                  {tab === "concept" ? "학습 설명" : tab === "formula" ? "공식·실무" : "출처"}
                </button>
              ))}
            </div>

            <div className="editor-body">
              {editorTab === "concept" ? (
                <>
                  <EditorField
                    label="한 문장 정의"
                    hint="공식을 반복하지 말고, 이 개념이 무엇인지 한 문장으로 설명합니다."
                    field="definition"
                    value={draft.definition}
                    onChange={updateField}
                    tall
                    readOnly={readOnly}
                  />
                  <EditorField
                    label="쉽게 이해하기"
                    hint="숫자나 실제 상황을 이용해 처음 보는 사람도 방향을 이해할 수 있게 설명합니다."
                    field="intuition"
                    value={draft.intuition}
                    onChange={updateField}
                    tall
                    readOnly={readOnly}
                  />
                  <EditorField
                    label="적용 유형 · Markdown"
                    hint="### 제목 하나가 앱에서 하나의 토글이 됩니다. 공식은 이 영역에 다시 넣지 않습니다."
                    field="scopeNotes"
                    value={draft.scopeNotes}
                    onChange={updateField}
                    tall
                    readOnly={readOnly}
                  />
                  <EditorField
                    label="원본 핵심 관계"
                    hint="콘텐츠 생성·검증에 쓰는 원본 관계입니다. 앱에는 아래 공식 필드가 표시됩니다."
                    field="coreRelation"
                    value={draft.coreRelation}
                    onChange={updateField}
                    readOnly={readOnly}
                  />
                  <EditorField
                    label="원본 요소 범위·생성 메모"
                    hint="문항 생성과 원본 추적용 메모이며 학습 화면에는 직접 표시되지 않습니다."
                    field="elementScopeNotes"
                    value={draft.elementScopeNotes}
                    onChange={updateField}
                    tall
                    readOnly={readOnly}
                  />
                </>
              ) : null}
              {editorTab === "formula" ? (
                <>
                  <EditorField
                    label="핵심 공식 · Markdown/LaTeX"
                    hint="학습 화면에서 공식이 표시되는 유일한 영역입니다. 긴 식도 임의로 여러 식으로 쪼개지 않습니다."
                    field="formulaExpression"
                    value={draft.formulaExpression}
                    onChange={updateField}
                    tall
                    mono
                    readOnly={readOnly}
                  />
                  <EditorField
                    label="공식 적용 조건"
                    hint="공식 카드 안의 ‘적용 조건’ 토글에서 표시됩니다."
                    field="formulaAssumptions"
                    value={draft.formulaAssumptions}
                    onChange={updateField}
                    tall
                    readOnly={readOnly}
                  />
                  <EditorField
                    label="실무에서 쓰이는 경우"
                    hint="구체적인 업무 장면을 Markdown 목록으로 최소 2개 작성합니다."
                    field="checklist"
                    value={draft.checklist}
                    onChange={updateField}
                    tall
                    readOnly={readOnly}
                  />
                  <div className="render-preview">
                    <span>앱 학습 화면 순서</span>
                    <p>한 문장 정의 → 쉽게 이해하기 → 핵심 공식 → 변수·항목 뜻 → 적용 유형 → 실무에서 쓰이는 경우</p>
                    <p><strong>공식 미리보기:</strong> {textPreview(draft.formulaExpression, 180)}</p>
                  </div>
                </>
              ) : null}
              {editorTab === "source" ? (
                <>
                  <EditorField label="출처명" field="sourceLabel" value={draft.sourceLabel} onChange={updateField} readOnly={readOnly} />
                  <EditorField label="출처 URL·위치" field="sourceLocator" value={draft.sourceLocator} onChange={updateField} tall readOnly={readOnly} />
                  <EditorField label="원본 명세 위치" field="specSectionLocator" value={draft.specSectionLocator} onChange={updateField} readOnly={readOnly} />
                  {draft.sourceLocator.startsWith("http") ? (
                    <a className="source-preview-link" href={draft.sourceLocator} target="_blank" rel="noreferrer">
                      연결된 원본 새 창에서 확인
                    </a>
                  ) : null}
                </>
              ) : null}

              {validation.length ? (
                <div className="editor-validation">
                  <strong>자동 확인 {validation.length}건</strong>
                  {validation.map((issue) => (
                    <p key={`${issue.field}-${issue.message}`} className={`validation-${issue.severity}`}>
                      <span>{issue.severity === "error" ? "!" : "i"}</span>
                      {fieldLabels[issue.field] ?? issue.field}: {issue.message}
                    </p>
                  ))}
                </div>
              ) : (
                <div className="editor-validation validation-clear"><Check size={15} /> 기본 형식 검사를 통과했습니다.</div>
              )}
            </div>

            <div className="editor-footer">
              <div>
                <span className={dirty ? "dirty-indicator is-dirty" : "dirty-indicator"} />
                {readOnly ? "Viewer · 읽기 전용" : dirty ? "저장하지 않은 변경" : "변경 없음"}
              </div>
              {!readOnly ? (
                <button
                  className="button button-primary"
                  type="button"
                  onClick={saveDraft}
                  disabled={!dirty || validation.some((issue) => issue.severity === "error")}
                >
                  revision 저장
                </button>
              ) : null}
            </div>
          </aside>
        ) : null}
      </section>
    </div>
  );
}

interface EditorFieldProps {
  label: string;
  hint?: string;
  field: keyof ConceptElement;
  value: string;
  onChange: (field: keyof ConceptElement, value: string) => void;
  tall?: boolean;
  mono?: boolean;
  readOnly?: boolean;
}

function EditorField({ label, hint, field, value, onChange, tall, mono, readOnly }: EditorFieldProps) {
  return (
    <label className="editor-field">
      <span>{label}</span>
      {hint ? <small>{hint}</small> : null}
      <textarea
        className={`${tall ? "textarea-tall" : ""} ${mono ? "textarea-mono" : ""}`}
        value={value}
        onChange={(event) => onChange(field, event.target.value)}
        rows={tall ? 7 : 3}
        readOnly={readOnly}
      />
    </label>
  );
}
