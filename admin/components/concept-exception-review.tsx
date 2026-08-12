"use client";

import { Check, ChevronDown, CircleAlert, LoaderCircle, Pencil, Save, X } from "lucide-react";
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import type { ConceptExperiment } from "@/lib/concept-model-report";
import type { ConceptQuestionDecision } from "@/lib/concept-model-review-store";

type QueueItem = ConceptExperiment["automatedReview"]["queue"][number];
type DecisionKind = ConceptQuestionDecision["decision"];
type DraftChoice = QueueItem["choices"][number];
type QuestionDraft = {
  stem: string;
  explanation: string;
  choices: DraftChoice[];
};
type ConceptOption = {
  elementId: string;
  title: string;
  definition: string;
  intuition: string;
};

function maskTerm(text: string, title: string) {
  const aliases = new Set([title, title.replace(/\([^)]*\)/gu, "").trim()]);
  for (const match of title.matchAll(/\(([^)]*)\)/gu)) {
    if (match[1]?.trim()) aliases.add(match[1].trim());
  }
  return [...aliases]
    .filter(Boolean)
    .sort((left, right) => right.length - left.length)
    .reduce((copy, alias) => copy.replaceAll(alias, "이 개념"), text)
    .replace(/(?:이 개념\s*){2,}/gu, "이 개념 ")
    .trim();
}

function suggestedChoiceText(option: ConceptOption, questionType: string) {
  if (questionType === "term_to_definition") return maskTerm(option.definition, option.title);
  if (questionType === "term_to_intuition") return maskTerm(option.intuition, option.title);
  const sentences = option.intuition.split(/(?<=[.!?])\s+/u).filter(Boolean);
  return maskTerm(sentences.at(-1) ?? option.intuition, option.title);
}

export function ConceptExceptionReview({
  items,
  initialDecisions,
  conceptOptions,
  canReview,
}: {
  items: QueueItem[];
  initialDecisions: Record<string, ConceptQuestionDecision>;
  conceptOptions: ConceptOption[];
  canReview: boolean;
}) {
  const router = useRouter();
  const [savedDecisions, setSavedDecisions] = useState(initialDecisions);
  const [comments, setComments] = useState<Record<string, string>>(
    Object.fromEntries(Object.entries(initialDecisions).map(([questionId, value]) => [questionId, value.comment])),
  );
  const [submitting, setSubmitting] = useState<{ questionId: string; decision: DecisionKind } | null>(null);
  const [editingQuestionId, setEditingQuestionId] = useState<string | null>(null);
  const [savingQuestionId, setSavingQuestionId] = useState<string | null>(null);
  const [drafts, setDrafts] = useState<Record<string, QuestionDraft>>({});
  const [messages, setMessages] = useState<Record<string, string>>({});
  const decidedCount = useMemo(
    () => items.filter((item) => savedDecisions[item.questionId]).length,
    [items, savedDecisions],
  );

  function beginEdit(item: QueueItem) {
    setDrafts((current) => ({
      ...current,
      [item.questionId]: {
        stem: item.stem,
        explanation: item.explanation,
        choices: item.choices.map((choice) => ({ ...choice })),
      },
    }));
    setEditingQuestionId(item.questionId);
    setMessages((current) => ({ ...current, [item.questionId]: "" }));
  }

  function updateDraft(questionId: string, update: Partial<QuestionDraft>) {
    setDrafts((current) => ({
      ...current,
      [questionId]: { ...current[questionId], ...update } as QuestionDraft,
    }));
  }

  function updateDraftChoice(questionId: string, index: number, update: Partial<DraftChoice>) {
    const draft = drafts[questionId];
    if (!draft) return;
    updateDraft(questionId, {
      choices: draft.choices.map((choice, choiceIndex) => (
        choiceIndex === index ? { ...choice, ...update } : choice
      )),
    });
  }

  function changeDraftChoice(item: QueueItem, index: number, elementId: string) {
    const option = conceptOptions.find((candidate) => candidate.elementId === elementId);
    if (!option) return;
    const text = suggestedChoiceText(option, item.questionType);
    updateDraftChoice(item.questionId, index, {
      elementId: option.elementId,
      text,
      explanation: `${option.title}: ${text}`,
    });
  }

  async function saveEdit(item: QueueItem) {
    const draft = drafts[item.questionId];
    if (!draft) return;
    if (!draft.stem.trim() || !draft.explanation.trim()) {
      setMessages((current) => ({ ...current, [item.questionId]: "문항과 해설을 입력해 주세요." }));
      return;
    }
    setSavingQuestionId(item.questionId);
    setMessages((current) => ({ ...current, [item.questionId]: "" }));
    try {
      const response = await fetch("/api/model/edit", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          questionId: item.questionId,
          questionFingerprint: item.questionFingerprint,
          stem: draft.stem,
          explanation: draft.explanation,
          choices: draft.choices,
          comment: comments[item.questionId] ?? "",
        }),
      });
      const result = await response.json().catch(() => ({})) as { error?: string; message?: string };
      if (!response.ok) {
        setMessages((current) => ({ ...current, [item.questionId]: result.error ?? "문항 수정 저장에 실패했습니다." }));
        return;
      }
      setEditingQuestionId(null);
      setMessages((current) => ({ ...current, [item.questionId]: result.message ?? "문항 수정이 저장되었습니다." }));
      router.refresh();
    } catch {
      setMessages((current) => ({ ...current, [item.questionId]: "서버에 연결하지 못했습니다." }));
    } finally {
      setSavingQuestionId(null);
    }
  }

  async function submitDecision(item: QueueItem, decision: DecisionKind) {
    const comment = comments[item.questionId]?.trim() ?? "";
    if (decision === "rejected" && !comment) {
      setMessages((current) => ({ ...current, [item.questionId]: "반려 사유를 입력해 주세요." }));
      return;
    }
    setSubmitting({ questionId: item.questionId, decision });
    setMessages((current) => ({ ...current, [item.questionId]: "" }));
    try {
      const response = await fetch("/api/model/review", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          questionId: item.questionId,
          questionFingerprint: item.questionFingerprint,
          decision,
          comment,
        }),
      });
      const result = await response.json().catch(() => ({})) as { error?: string; message?: string };
      if (!response.ok) {
        setMessages((current) => ({ ...current, [item.questionId]: result.error ?? "결정을 저장하지 못했습니다." }));
        return;
      }
      setSavedDecisions((current) => ({
        ...current,
        [item.questionId]: {
          decision,
          reviewerId: "current-owner",
          reviewedAt: new Date().toISOString(),
          comment,
        },
      }));
      setMessages((current) => ({ ...current, [item.questionId]: result.message ?? "결정을 저장했습니다." }));
      router.refresh();
    } catch {
      setMessages((current) => ({ ...current, [item.questionId]: "서버에 연결하지 못했습니다." }));
    } finally {
      setSubmitting(null);
    }
  }

  return (
    <div className="concept-review-queue">
      <div className="concept-review-queue-heading">
        <div><h3>확인 대기 문항 {items.length}개</h3><p>결정 저장 {decidedCount} · 미결 {items.length - decidedCount}</p></div>
        {!canReview ? <span><CircleAlert size={15} /> Owner 계정에서만 결정할 수 있습니다.</span> : null}
      </div>
      {items.map((item) => {
        const saved = savedDecisions[item.questionId];
        const busy = submitting?.questionId === item.questionId || savingQuestionId === item.questionId;
        const editing = editingQuestionId === item.questionId;
        const draft = drafts[item.questionId];
        return (
          <details className="model-rule-details concept-review-item" key={item.questionId} open={saved?.decision === "rejected"}>
            <summary>
              <ChevronDown size={17} />
              <span><strong>{item.severity === "block" ? "차단" : "확인"} · {item.questionId}</strong><small>{item.reasons.map((reason) => reason.label).join(" · ")}</small></span>
              {saved ? <b className={`concept-review-decision ${saved.decision}`}>{saved.decision === "approved" ? "승인 저장됨" : "반려 저장됨"}</b> : <b className="concept-review-decision pending">미결</b>}
            </summary>
            <div className="model-rule-detail-body concept-review-detail">
              {editing && draft ? (
                <div className="concept-review-editor">
                  <label className="concept-review-comment">
                    <span>문항</span>
                    <textarea
                      rows={3}
                      value={draft.stem}
                      onChange={(event) => updateDraft(item.questionId, { stem: event.target.value })}
                      maxLength={20000}
                      disabled={!canReview || busy}
                    />
                  </label>
                  <label className="concept-review-comment">
                    <span>해설</span>
                    <textarea
                      rows={4}
                      value={draft.explanation}
                      onChange={(event) => updateDraft(item.questionId, { explanation: event.target.value })}
                      maxLength={20000}
                      disabled={!canReview || busy}
                    />
                  </label>
                </div>
              ) : <p className="concept-review-stem">{item.stem}</p>}
              <div className="table-scroll">
                <table className="data-table">
                  <thead><tr><th>선택지</th><th>화면에 보이는 설명</th><th>판정</th><th>출처 용어·검토 메모</th></tr></thead>
                  <tbody>{item.choices.map((choice, choiceIndex) => {
                    const draftChoice = draft?.choices[choiceIndex] ?? choice;
                    const sourceOption = conceptOptions.find((option) => option.elementId === draftChoice.elementId);
                    return (
                      <tr key={choice.key}>
                        <td><strong>{choice.key}</strong></td>
                        <td>{editing ? <textarea
                          className="concept-review-input"
                          rows={4}
                          value={draftChoice.text}
                          onChange={(event) => updateDraftChoice(item.questionId, choiceIndex, { text: event.target.value })}
                          maxLength={2000}
                          disabled={!canReview || busy}
                          aria-label={`${choice.key} 화면 설명`}
                        /> : <span className="concept-review-choice-copy"><strong>{choice.text}</strong></span>}</td>
                        <td>{choice.isCorrect ? "정답" : "오답"}</td>
                        <td>{editing ? <div className="concept-review-choice-fields">
                          <select
                            className="concept-review-input concept-review-select"
                            value={draftChoice.elementId}
                            onChange={(event) => changeDraftChoice(item, choiceIndex, event.target.value)}
                            disabled={!canReview || busy || choice.isCorrect}
                            aria-label={`${choice.key} 출처 용어`}
                          >
                            {!sourceOption ? <option value={draftChoice.elementId}>{draftChoice.elementId}</option> : null}
                            {conceptOptions.map((option) => (
                              <option key={option.elementId} value={option.elementId}>{option.title}</option>
                            ))}
                          </select>
                          <textarea
                            className="concept-review-input"
                            rows={2}
                            value={draftChoice.explanation}
                            onChange={(event) => updateDraftChoice(item.questionId, choiceIndex, { explanation: event.target.value })}
                            maxLength={2000}
                            disabled={!canReview || busy}
                            aria-label={`${choice.key} 보기 해설`}
                          />
                        </div> : <span className="concept-review-choice-copy"><strong>{sourceOption?.title ?? choice.elementId}</strong><small>{choice.elementId}</small>{choice.explanation}</span>}</td>
                      </tr>
                    );
                  })}</tbody>
                </table>
              </div>
              <div className="concept-review-edit-toolbar">
                <span>{editing ? "정답 대상 용어는 고정되며 오답 보기와 문구를 수정할 수 있습니다." : "문항·선택지·해설을 수정한 뒤 모델을 다시 실행할 수 있습니다."}</span>
                {editing ? <>
                  <button className="button button-ghost" type="button" onClick={() => setEditingQuestionId(null)} disabled={busy}>
                    <X size={15} /> 취소
                  </button>
                  <button className="button button-primary" type="button" onClick={() => saveEdit(item)} disabled={!canReview || busy}>
                    {savingQuestionId === item.questionId ? <LoaderCircle className="spin" size={15} /> : <Save size={15} />}
                    {savingQuestionId === item.questionId ? "저장 중" : "수정 저장"}
                  </button>
                </> : <button className="button button-ghost" type="button" onClick={() => beginEdit(item)} disabled={!canReview || busy}>
                  <Pencil size={15} /> 문항 수정
                </button>}
              </div>
              <label className="concept-review-comment">
                <span>검수 메모 {comments[item.questionId]?.length ? `· ${comments[item.questionId].length}자` : ""}</span>
                <textarea
                  rows={2}
                  value={comments[item.questionId] ?? ""}
                  onChange={(event) => setComments((current) => ({ ...current, [item.questionId]: event.target.value }))}
                  placeholder="승인 메모는 선택, 반려 사유는 필수입니다."
                  maxLength={2000}
                  disabled={!canReview || busy}
                />
              </label>
              <div className="concept-review-actions">
                <code title={item.questionFingerprint}>{item.questionFingerprint}</code>
                <button className="button button-ghost-danger" type="button" onClick={() => submitDecision(item, "rejected")} disabled={!canReview || busy}>
                  {busy && submitting?.decision === "rejected" ? <LoaderCircle className="spin" size={15} /> : <X size={15} />}
                  {busy && submitting?.decision === "rejected" ? "반려 저장 중…" : "반려"}
                </button>
                <button className="button button-primary" type="button" onClick={() => submitDecision(item, "approved")} disabled={!canReview || busy || item.severity === "block"}>
                  {busy && submitting?.decision === "approved" ? <LoaderCircle className="spin" size={15} /> : <Check size={15} />}
                  {busy && submitting?.decision === "approved" ? "승인 저장 중…" : "승인"}
                </button>
              </div>
              {messages[item.questionId] ? <p className="concept-review-message" role="status">{messages[item.questionId]}</p> : null}
            </div>
          </details>
        );
      })}
    </div>
  );
}
