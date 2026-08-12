"use client";

import { Check, ChevronDown, CircleAlert, LoaderCircle, X } from "lucide-react";
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import type { ConceptExperiment } from "@/lib/concept-model-report";
import type { ConceptQuestionDecision } from "@/lib/concept-model-review-store";

type QueueItem = ConceptExperiment["automatedReview"]["queue"][number];
type DecisionKind = ConceptQuestionDecision["decision"];

export function ConceptExceptionReview({
  items,
  initialDecisions,
  canReview,
}: {
  items: QueueItem[];
  initialDecisions: Record<string, ConceptQuestionDecision>;
  canReview: boolean;
}) {
  const router = useRouter();
  const [savedDecisions, setSavedDecisions] = useState(initialDecisions);
  const [comments, setComments] = useState<Record<string, string>>(
    Object.fromEntries(Object.entries(initialDecisions).map(([questionId, value]) => [questionId, value.comment])),
  );
  const [submitting, setSubmitting] = useState<{ questionId: string; decision: DecisionKind } | null>(null);
  const [messages, setMessages] = useState<Record<string, string>>({});
  const decidedCount = useMemo(
    () => items.filter((item) => savedDecisions[item.questionId]).length,
    [items, savedDecisions],
  );

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
        const busy = submitting?.questionId === item.questionId;
        return (
          <details className="model-rule-details concept-review-item" key={item.questionId} open={saved?.decision === "rejected"}>
            <summary>
              <ChevronDown size={17} />
              <span><strong>{item.severity === "block" ? "차단" : "확인"} · {item.questionId}</strong><small>{item.reasons.map((reason) => reason.label).join(" · ")}</small></span>
              {saved ? <b className={`concept-review-decision ${saved.decision}`}>{saved.decision === "approved" ? "승인 저장됨" : "반려 저장됨"}</b> : <b className="concept-review-decision pending">미결</b>}
            </summary>
            <div className="model-rule-detail-body concept-review-detail">
              <p className="concept-review-stem">{item.stem}</p>
              <div className="table-scroll">
                <table className="data-table">
                  <thead><tr><th>선택지</th><th>개념</th><th>판정</th><th>설명</th></tr></thead>
                  <tbody>{item.choices.map((choice) => <tr key={choice.key}><td>{choice.key}</td><td>{choice.text}</td><td>{choice.isCorrect ? "정답" : "오답"}</td><td>{choice.explanation}</td></tr>)}</tbody>
                </table>
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
