"use client";

import { Check, ChevronDown, CircleOff, Lightbulb, Plus, Search, Trash2, X } from "lucide-react";
import { useMemo, useState } from "react";
import { PageHeader } from "@/components/page-header";
import { StatusBadge } from "@/components/status-badge";
import { getBrowserSupabase } from "@/lib/supabase/browser";
import type { Difficulty, DistractorItem } from "@/lib/types";

interface ElementOption {
  elementId: string;
  title: string;
  domainName: string;
}

export function DistractorManager({
  initialDistractors,
  elements,
  readOnly,
}: {
  initialDistractors: DistractorItem[];
  elements: ElementOption[];
  readOnly: boolean;
}) {
  const [items, setItems] = useState(initialDistractors);
  const [selected, setSelected] = useState<DistractorItem | null>(initialDistractors[0] ?? null);
  const [draft, setDraft] = useState<DistractorItem | null>(initialDistractors[0] ?? null);
  const [query, setQuery] = useState("");
  const [activeFilter, setActiveFilter] = useState("all");
  const [message, setMessage] = useState("");
  const [saving, setSaving] = useState(false);

  const filtered = useMemo(() => {
    const normalized = query.toLocaleLowerCase("ko-KR").trim();
    return items.filter((item) => {
      if (activeFilter === "active" && !item.active) return false;
      if (activeFilter === "inactive" && item.active) return false;
      return !normalized || `${item.elementId} ${item.elementTitle} ${item.text} ${item.confusionType}`.toLocaleLowerCase("ko-KR").includes(normalized);
    });
  }, [items, query, activeFilter]);

  function choose(item: DistractorItem) {
    setSelected(item);
    setDraft(item);
    setMessage("");
  }

  function createNew() {
    if (readOnly) return;
    const element = elements[0];
    if (!element) return;
    const item: DistractorItem = {
      id: `new-${crypto.randomUUID()}`,
      elementId: element.elementId,
      elementTitle: element.title,
      text: "",
      rationale: "",
      confusionType: "",
      difficulty: "보통",
      active: true,
      status: "draft",
      updatedAt: "새 항목",
    };
    setSelected(item);
    setDraft(item);
  }

  function update<K extends keyof DistractorItem>(key: K, value: DistractorItem[K]) {
    setDraft((current) => (current ? { ...current, [key]: value } : current));
  }

  function changeElement(elementId: string) {
    const element = elements.find((item) => item.elementId === elementId);
    if (element) setDraft((current) => current ? { ...current, elementId, elementTitle: element.title } : current);
  }

  async function save() {
    if (!draft || !draft.text.trim() || !draft.rationale.trim()) return;
    if (readOnly) {
      setMessage("현재 4개 항목은 화면 흐름 확인용 예시입니다. Supabase 연결 후 실제 오답 후보를 저장할 수 있습니다.");
      return;
    }
    const supabase = getBrowserSupabase();
    if (!supabase) return setMessage("Supabase 연결을 확인해 주세요.");
    setSaving(true);
    const payload = {
      element_id: draft.elementId,
      text: draft.text.trim(),
      explanation: draft.rationale.trim(),
      misconception_type: draft.confusionType.trim(),
      difficulty: draft.difficulty === "기초" ? 2 : draft.difficulty === "심화" ? 4 : 3,
      is_enabled: draft.active,
    };
    if (draft.id.startsWith("new-")) {
      const { data, error } = await supabase
        .from("distractors")
        .insert({ ...payload, distractor_key: `dist-${crypto.randomUUID()}` })
        .select("distractor_id")
        .single();
      setSaving(false);
      if (error) return setMessage(error.message);
      const saved = { ...draft, id: String(data.distractor_id), updatedAt: "방금 저장" };
      setItems((current) => [saved, ...current]);
      setSelected(saved);
      setDraft(saved);
    } else {
      const { error } = await supabase.from("distractors").update(payload).eq("distractor_id", draft.id);
      setSaving(false);
      if (error) return setMessage(error.message);
      setItems((current) => current.map((item) => item.id === draft.id ? draft : item));
      setSelected(draft);
    }
    setMessage("오답 후보를 새 revision으로 저장했습니다.");
  }

  async function remove() {
    if (!draft || draft.id.startsWith("new-") || readOnly) return;
    if (!window.confirm("이 오답 후보를 삭제하시겠습니까? 삭제 revision이 기록됩니다.")) return;
    const supabase = getBrowserSupabase();
    if (!supabase) return setMessage("Supabase 연결을 확인해 주세요.");
    setSaving(true);
    const { error } = await supabase.from("distractors").delete().eq("distractor_id", draft.id);
    setSaving(false);
    if (error) return setMessage(error.message);
    const remaining = items.filter((item) => item.id !== draft.id);
    setItems(remaining);
    setSelected(remaining[0] ?? null);
    setDraft(remaining[0] ?? null);
    setMessage("오답 후보를 삭제하고 이력을 남겼습니다.");
  }

  const dirty = Boolean(draft && JSON.stringify(draft) !== JSON.stringify(selected));
  const exampleMode = readOnly && initialDistractors.some((item) => item.id.startsWith("demo-"));

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="DISTRACTOR LIBRARY"
        title="오답 후보"
        description={readOnly
          ? "랜덤 개념문제에 사용되는 오답 선택지와 설명을 조회합니다."
          : "랜덤 개념문제에 사용할 틀린 선택지와 틀린 이유만 요소별로 관리합니다. 문제 템플릿은 다루지 않습니다."}
        actions={readOnly ? null : <button className="button button-primary" type="button" onClick={createNew}><Plus size={16} /> 오답 후보 추가</button>}
      />

      {exampleMode ? (
        <div className="example-banner"><Lightbulb size={18} /><p><strong>현재 앱에는 별도 오답 후보 DB가 없습니다.</strong> 아래 4건은 관리 방식 확인을 위한 데모 예시이며 실제 앱 데이터가 아닙니다.</p></div>
      ) : null}

      <section className="split-workspace distractor-workspace">
        <div className="panel list-pane">
          <div className="pane-toolbar">
            <label className="search-box compact-search"><Search size={16} /><span className="visually-hidden">오답 검색</span><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="요소 또는 오답 문구 검색" />{query ? <button type="button" onClick={() => setQuery("")} aria-label="검색어 지우기"><X size={14} /></button> : null}</label>
            <label className="select-wrap"><span className="visually-hidden">사용 상태</span><select value={activeFilter} onChange={(event) => setActiveFilter(event.target.value)}><option value="all">전체</option><option value="active">사용 중</option><option value="inactive">사용 안 함</option></select><ChevronDown size={14} /></label>
          </div>
          <div className="pane-count">{filtered.length}개 후보</div>
          <div className="distractor-list">
            {filtered.map((item) => (
              <button key={item.id} type="button" className={`distractor-card ${selected?.id === item.id ? "active" : ""}`} onClick={() => choose(item)}>
                <div className="distractor-card-top"><span className="mono-id">{item.elementId}</span><StatusBadge status={item.status} /></div>
                <strong>{item.text}</strong>
                <p>{item.elementTitle}</p>
                <div className="distractor-card-meta"><span>{item.confusionType || "유형 미지정"}</span><span className={item.active ? "active-use" : "inactive-use"}>{item.active ? "사용 중" : "사용 안 함"}</span></div>
              </button>
            ))}
            {!filtered.length ? <div className="pane-empty"><CircleOff size={22} /><strong>등록된 후보가 없습니다</strong><p>{readOnly ? "조회할 오답 후보가 없습니다." : "상단 버튼으로 첫 오답 후보를 추가하세요."}</p></div> : null}
          </div>
        </div>

        <div className="panel detail-pane">
          {draft ? (
            <>
              <div className="detail-pane-heading"><div><p className="eyebrow">DISTRACTOR DETAIL</p><h2>{draft.id.startsWith("new-") ? "새 오답 후보" : draft.elementTitle}</h2></div><span className={draft.active ? "toggle-label on" : "toggle-label"}><button type="button" role="switch" aria-checked={draft.active} onClick={() => update("active", !draft.active)} disabled={readOnly}><i /></button>{draft.active ? "앱에서 사용" : "사용 안 함"}</span></div>
              <div className="detail-form">
                <label className="editor-field"><span>연결할 학습 요소</span><div className="select-wrap full-select"><select value={draft.elementId} disabled={readOnly || !draft.id.startsWith("new-")} onChange={(event) => changeElement(event.target.value)}>{elements.map((element) => <option key={element.elementId} value={element.elementId}>{element.elementId} · {element.title}</option>)}</select><ChevronDown size={14} /></div></label>
                <label className="editor-field"><span>오답 문구</span><textarea className="textarea-tall" value={draft.text} onChange={(event) => update("text", event.target.value)} rows={5} placeholder="정답처럼 보일 수 있지만 명확히 틀린 문장을 입력하세요." readOnly={readOnly} /></label>
                <label className="editor-field"><span>왜 틀렸는지</span><textarea className="textarea-tall" value={draft.rationale} onChange={(event) => update("rationale", event.target.value)} rows={5} placeholder="학습자가 혼동한 지점을 한 문장으로 설명하세요." readOnly={readOnly} /></label>
                <div className="two-field-row">
                  <label className="editor-field"><span>혼동 유형</span><input value={draft.confusionType} onChange={(event) => update("confusionType", event.target.value)} placeholder="예: 방향성 오류" readOnly={readOnly} /></label>
                  <label className="editor-field"><span>난이도</span><div className="select-wrap full-select"><select value={draft.difficulty} onChange={(event) => update("difficulty", event.target.value as Difficulty)} disabled={readOnly}><option>기초</option><option>보통</option><option>심화</option></select><ChevronDown size={14} /></div></label>
                </div>
                <div className="quality-note"><Check size={16} /><p><strong>좋은 오답 후보</strong>는 정답과 같은 문장 구조를 쓰되, 한 가지 개념 오류만 포함합니다.</p></div>
                {message ? <div className="table-notice" role="status">{message}</div> : null}
              </div>
              <div className="detail-footer"><span><i className={dirty ? "dirty-indicator is-dirty" : "dirty-indicator"} />{readOnly ? "Viewer · 읽기 전용" : dirty ? "저장하지 않은 변경" : "변경 없음"}</span>{!readOnly ? <div className="detail-footer-actions">{!draft.id.startsWith("new-") ? <button className="button button-ghost-danger" type="button" onClick={remove} disabled={saving}><Trash2 size={15} /> 삭제</button> : null}<button className="button button-primary" type="button" onClick={save} disabled={saving || !draft.text.trim() || !draft.rationale.trim()}>{saving ? "저장 중…" : "오답 후보 저장"}</button></div> : null}</div>
            </>
          ) : (
            <div className="pane-empty full-empty"><CircleOff size={24} /><strong>편집할 오답 후보를 선택하세요</strong></div>
          )}
        </div>
      </section>
    </div>
  );
}
