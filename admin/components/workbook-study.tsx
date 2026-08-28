"use client";

import {
  ArrowLeft,
  ArrowRight,
  BookOpenCheck,
  Check,
  ChevronDown,
  CircleHelp,
  ListChecks,
  RotateCcw,
} from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState, useTransition } from "react";
import { PageHeader } from "@/components/page-header";
import type {
  WorkbookIndex,
  WorkbookQuestion,
  WorkbookTheoryBlock,
  WorkbookUnit,
} from "@/lib/workbook-types";

const ANSWER_LABELS = ["①", "②", "③", "④", "⑤"] as const;

interface WorkbookStudyProps {
  index: WorkbookIndex;
  unit: WorkbookUnit;
}

interface AnswerRecord {
  selected: number;
  checked: boolean;
}

type AnswerState = Record<string, AnswerRecord>;
type StudyMode = "theory" | "quiz";

interface TheoryCard {
  kind: "divider" | "card";
  blocks: WorkbookTheoryBlock[];
}

function buildTheoryCards(blocks: WorkbookTheoryBlock[]): TheoryCard[] {
  const cards: TheoryCard[] = [];
  let current: WorkbookTheoryBlock[] = [];

  const flush = () => {
    if (current.length) cards.push({ kind: "card", blocks: current });
    current = [];
  };

  for (const block of blocks) {
    if (block.kind === "section") {
      flush();
      cards.push({ kind: "divider", blocks: [block] });
      continue;
    }
    if (block.kind === "element" && current.length) flush();
    if (block.kind === "concept" && current.length && current[0]?.kind !== "element") flush();
    current.push(block);
  }
  flush();
  return cards;
}

function safeStoredAnswers(value: string | null, questionIds: Set<string>): AnswerState {
  if (!value) return {};
  try {
    const parsed = JSON.parse(value) as unknown;
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) return {};
    const answers: AnswerState = {};
    for (const [questionId, record] of Object.entries(parsed)) {
      if (!questionIds.has(questionId) || !record || typeof record !== "object" || Array.isArray(record)) continue;
      const candidate = record as Partial<AnswerRecord>;
      if (!Number.isInteger(candidate.selected) || candidate.selected! < 0 || candidate.selected! > 4) continue;
      answers[questionId] = { selected: candidate.selected!, checked: candidate.checked === true };
    }
    return answers;
  } catch {
    return {};
  }
}

function QuestionCard({
  question,
  number,
  record,
  onSelect,
  onCheck,
  onReset,
}: {
  question: WorkbookQuestion;
  number: number;
  record?: AnswerRecord;
  onSelect: (choice: number) => void;
  onCheck: () => void;
  onReset: () => void;
}) {
  const checked = record?.checked === true;
  const correct = checked && record.selected === question.answerIndex;

  return (
    <article className={`workbook-question panel ${checked ? correct ? "is-correct" : "is-wrong" : ""}`} id={question.id}>
      <header className="workbook-question-heading">
        <span className="workbook-question-number">{String(number).padStart(2, "0")}</span>
        <div>
          <strong>{question.id}</strong>
          <small>난이도 {question.difficulty} · {question.kind}</small>
        </div>
      </header>

      <h3>
        {question.stem.split("\n").map((line, lineIndex) => (
          <span key={`${question.id}-stem-${lineIndex}`}>{line}</span>
        ))}
      </h3>

      <fieldset className="workbook-choices">
        <legend className="visually-hidden">{question.id} 보기</legend>
        {question.choices.map((choice, choiceIndex) => {
          const selected = record?.selected === choiceIndex;
          const choiceCorrect = checked && choiceIndex === question.answerIndex;
          const choiceWrong = checked && selected && choiceIndex !== question.answerIndex;
          const className = [
            "workbook-choice",
            selected ? "is-selected" : "",
            choiceCorrect ? "is-answer" : "",
            choiceWrong ? "is-wrong-answer" : "",
          ].filter(Boolean).join(" ");
          return (
            <label className={className} key={`${question.id}-${choiceIndex}`}>
              <input
                type="radio"
                name={question.id}
                value={choiceIndex}
                checked={selected}
                disabled={checked}
                onChange={() => onSelect(choiceIndex)}
              />
              <span className="workbook-choice-index" aria-hidden="true">{ANSWER_LABELS[choiceIndex]}</span>
              <span>{choice}</span>
              {choiceCorrect ? <Check className="workbook-choice-check" size={18} aria-label="정답" /> : null}
            </label>
          );
        })}
      </fieldset>

      <footer className="workbook-question-actions">
        <p className={`workbook-answer-status ${checked ? correct ? "correct" : "wrong" : ""}`} aria-live="polite">
          {!record
            ? "보기를 선택하세요."
            : !checked
              ? `${ANSWER_LABELS[record.selected]}번을 선택했습니다.`
              : correct
                ? "정답입니다."
                : `오답입니다. 정답은 ${ANSWER_LABELS[question.answerIndex]}번입니다.`}
        </p>
        {checked ? (
          <button className="button button-secondary" type="button" onClick={onReset}>
            <RotateCcw size={15} /> 다시 풀기
          </button>
        ) : (
          <button className="button button-primary" type="button" onClick={onCheck} disabled={!record}>
            <Check size={15} /> 정답 확인
          </button>
        )}
      </footer>

      {checked ? (
        <details className="workbook-solution" open>
          <summary>상세 해설</summary>
          <div>
            {question.solution.map((segment, segmentIndex) => (
              <p className={segment.labelled ? "labelled" : undefined} key={`${question.id}-solution-${segmentIndex}`}>
                {segment.text}
              </p>
            ))}
            <small>근거 · {question.evidence}</small>
          </div>
        </details>
      ) : null}
    </article>
  );
}

export function WorkbookStudy({ index, unit }: WorkbookStudyProps) {
  const router = useRouter();
  const quizTopRef = useRef<HTMLElement>(null);
  const [mode, setMode] = useState<StudyMode>("theory");
  const [answers, setAnswers] = useState<AnswerState>({});
  const [storageReady, setStorageReady] = useState(false);
  const [isNavigating, startNavigation] = useTransition();

  const flatUnits = useMemo(() => index.subjects.flatMap((subject) => subject.units), [index.subjects]);
  const unitPosition = flatUnits.findIndex((item) => item.id === unit.id);
  const previousUnit = unitPosition > 0 ? flatUnits[unitPosition - 1] : null;
  const nextUnit = unitPosition >= 0 && unitPosition < flatUnits.length - 1 ? flatUnits[unitPosition + 1] : null;
  const theoryCards = useMemo(() => buildTheoryCards(unit.theory), [unit.theory]);
  const questionIds = useMemo(() => new Set(unit.questions.map((question) => question.id)), [unit.questions]);
  const storageKey = `findone-workbook:${index.source.sha256}:${unit.id}`;

  useEffect(() => {
    setStorageReady(false);
    let stored: string | null = null;
    try {
      stored = window.localStorage.getItem(storageKey);
    } catch {
      // The workbook still works when storage is disabled by the browser.
    }
    setAnswers(safeStoredAnswers(stored, questionIds));
    setStorageReady(true);
  }, [questionIds, storageKey]);

  useEffect(() => {
    if (!storageReady) return;
    try {
      window.localStorage.setItem(storageKey, JSON.stringify(answers));
    } catch {
      // Keep the in-memory session usable when persistent storage is unavailable.
    }
  }, [answers, storageKey, storageReady]);

  const selectedCount = unit.questions.filter((question) => answers[question.id]).length;
  const checkedCount = unit.questions.filter((question) => answers[question.id]?.checked).length;
  const correctCount = unit.questions.filter((question) => {
    const record = answers[question.id];
    return record?.checked && record.selected === question.answerIndex;
  }).length;
  const pendingSelectedCount = selectedCount - checkedCount;
  const score = checkedCount ? Math.round((correctCount / checkedCount) * 100) : 0;

  function navigateToUnit(unitId: string) {
    if (!unitId || unitId === unit.id) return;
    startNavigation(() => router.push(`/workbook/${unitId}`));
  }

  function showQuiz() {
    setMode("quiz");
    window.requestAnimationFrame(() => quizTopRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }));
  }

  function selectAnswer(questionId: string, choice: number) {
    setAnswers((current) => {
      if (current[questionId]?.checked) return current;
      return { ...current, [questionId]: { selected: choice, checked: false } };
    });
  }

  function checkAnswer(questionId: string) {
    setAnswers((current) => {
      const record = current[questionId];
      return record ? { ...current, [questionId]: { ...record, checked: true } } : current;
    });
  }

  function resetAnswer(questionId: string) {
    setAnswers((current) => {
      const next = { ...current };
      delete next[questionId];
      return next;
    });
  }

  function checkSelectedAnswers() {
    setAnswers((current) => Object.fromEntries(
      Object.entries(current).map(([questionId, record]) => [questionId, { ...record, checked: true }]),
    ));
  }

  function resetUnit() {
    if (!window.confirm(`${unit.title}의 저장된 풀이 기록을 모두 지울까요?`)) return;
    setAnswers({});
  }

  return (
    <div className="page-stack workbook-page">
      <PageHeader
        eyebrow="THEORY TO PRACTICE"
        title="FinDone 이론 문제집"
        description="개념을 먼저 익힌 뒤 단원별 30문항을 풀고, 정답과 상세 해설을 바로 확인합니다."
        actions={
          <button className="button button-primary" type="button" onClick={showQuiz}>
            <ListChecks size={16} /> 문제 풀기
          </button>
        }
      />

      <section className="panel workbook-control-panel" aria-label="문제집 단원 선택">
        <div className="workbook-unit-heading">
          <span className="large-state-icon state-success"><BookOpenCheck size={24} /></span>
          <div>
            <small>{unit.subjectTitle}</small>
            <h2>{unit.title}</h2>
            <p>{unit.subtitle || "개념 정리와 30문항 상세 해설"}</p>
          </div>
        </div>

        <div className="workbook-selectors">
          <label>
            <span>과목·파트</span>
            <span className="workbook-select-wrap">
              <select
                value={unit.subjectId}
                onChange={(event) => {
                  const first = index.subjects.find((subject) => subject.id === event.target.value)?.units[0];
                  if (first) navigateToUnit(first.id);
                }}
                disabled={isNavigating}
              >
                {index.subjects.map((subject) => <option key={subject.id} value={subject.id}>{subject.title}</option>)}
              </select>
              <ChevronDown size={15} aria-hidden="true" />
            </span>
          </label>
          <label>
            <span>단원</span>
            <span className="workbook-select-wrap">
              <select value={unit.id} onChange={(event) => navigateToUnit(event.target.value)} disabled={isNavigating}>
                {index.subjects.map((subject) => (
                  <optgroup key={subject.id} label={subject.title}>
                    {subject.units.map((item) => <option key={item.id} value={item.id}>{item.title}</option>)}
                  </optgroup>
                ))}
              </select>
              <ChevronDown size={15} aria-hidden="true" />
            </span>
          </label>
        </div>

        <nav className="workbook-unit-nav" aria-label="이전·다음 단원">
          {previousUnit ? (
            <Link className="icon-button" href={`/workbook/${previousUnit.id}`} aria-label={`이전 단원: ${previousUnit.title}`}>
              <ArrowLeft size={18} />
            </Link>
          ) : <span className="icon-button workbook-disabled-nav" aria-hidden="true"><ArrowLeft size={18} /></span>}
          <span>{unitPosition + 1} / {flatUnits.length}</span>
          {nextUnit ? (
            <Link className="icon-button" href={`/workbook/${nextUnit.id}`} aria-label={`다음 단원: ${nextUnit.title}`}>
              <ArrowRight size={18} />
            </Link>
          ) : <span className="icon-button workbook-disabled-nav" aria-hidden="true"><ArrowRight size={18} /></span>}
        </nav>
      </section>

      <section className="workbook-stat-grid" aria-label="문제집 구성과 풀이 현황">
        <article className="panel"><span>전체 구성</span><strong>{index.stats.subjectCount}<small>파트</small></strong><p>{index.stats.unitCount}개 단원</p></article>
        <article className="panel"><span>수록 문항</span><strong>{index.stats.questionCount.toLocaleString("ko-KR")}<small>문항</small></strong><p>단원별 30문항</p></article>
        <article className="panel"><span>현재 진도</span><strong>{checkedCount}<small>/ {unit.questions.length}</small></strong><p>{selectedCount}개 답안 선택</p></article>
        <article className="panel"><span>현재 정답률</span><strong>{score}<small>%</small></strong><p>{checkedCount ? `${correctCount}개 정답` : "채점 후 표시"}</p></article>
      </section>

      <section className="panel workbook-study-panel" ref={quizTopRef}>
        <div className="workbook-tabs" role="group" aria-label="학습 단계">
          <button
            className={mode === "theory" ? "active" : ""}
            type="button"
            aria-pressed={mode === "theory"}
            onClick={() => setMode("theory")}
          >
            <BookOpenCheck size={17} /> 개념 학습
          </button>
          <button
            className={mode === "quiz" ? "active" : ""}
            type="button"
            aria-pressed={mode === "quiz"}
            onClick={() => setMode("quiz")}
          >
            <ListChecks size={17} /> 문제 풀기 <span>{checkedCount}/{unit.questions.length}</span>
          </button>
        </div>

        {mode === "theory" ? (
          <div className="workbook-theory-view">
            <header>
              <div>
                <p className="eyebrow">CONCEPT REVIEW</p>
                <h2>{unit.title}</h2>
                <p>{unit.subtitle}</p>
              </div>
              <button className="button button-primary" type="button" onClick={showQuiz}>
                문제로 넘어가기 <ArrowRight size={16} />
              </button>
            </header>
            {unit.meta.length ? <div className="workbook-meta-list">{unit.meta.map((item) => <span key={item}>{item}</span>)}</div> : null}
            <div className="workbook-theory-grid">
              {theoryCards.map((card, cardIndex) => card.kind === "divider" ? (
                <h3 className="workbook-theory-divider" key={`theory-${cardIndex}`}>{card.blocks[0].text}</h3>
              ) : (
                <article className="workbook-theory-card" key={`theory-${cardIndex}`}>
                  {card.blocks.map((block, blockIndex) => {
                    const key = `theory-${cardIndex}-${blockIndex}`;
                    if (block.kind === "concept" || block.kind === "element") return <h4 key={key}>{block.text}</h4>;
                    if (block.kind === "label") return <strong className="workbook-theory-label" key={key}>{block.text}</strong>;
                    return <p className={block.kind === "bullet" ? "workbook-theory-bullet" : undefined} key={key}>{block.text}</p>;
                  })}
                </article>
              ))}
            </div>
            {unit.sourceNote ? <p className="workbook-source-note">출처 · {unit.sourceNote}</p> : null}
          </div>
        ) : (
          <div className="workbook-quiz-view">
            <header className="workbook-quiz-toolbar">
              <div>
                <p className="eyebrow">PRACTICE · 30 QUESTIONS</p>
                <h2>문제 풀기</h2>
                <p>보기를 고르고 정답 확인을 누르면 상세 해설이 열립니다. 풀이 기록은 이 브라우저에 저장됩니다.</p>
              </div>
              <div className="workbook-quiz-actions">
                <button className="button button-secondary" type="button" onClick={resetUnit} disabled={!selectedCount}>
                  <RotateCcw size={15} /> 진도 초기화
                </button>
                <button className="button button-primary" type="button" onClick={checkSelectedAnswers} disabled={!pendingSelectedCount}>
                  <Check size={15} /> 선택 답안 채점
                </button>
              </div>
            </header>

            <div className="workbook-progress-summary" role="status">
              <div className="progress-track"><span style={{ width: `${(checkedCount / unit.questions.length) * 100}%` }} /></div>
              <p><strong>{checkedCount}/{unit.questions.length}</strong> 채점 · <strong>{correctCount}</strong> 정답 · <strong>{score}%</strong></p>
            </div>

            <div className="workbook-question-list">
              {unit.questions.map((question, questionIndex) => (
                <QuestionCard
                  key={question.id}
                  question={question}
                  number={questionIndex + 1}
                  record={answers[question.id]}
                  onSelect={(choice) => selectAnswer(question.id, choice)}
                  onCheck={() => checkAnswer(question.id)}
                  onReset={() => resetAnswer(question.id)}
                />
              ))}
            </div>

            <footer className="workbook-unit-complete">
              <span className="large-state-icon state-success"><CircleHelp size={24} /></span>
              <div>
                <strong>{checkedCount === unit.questions.length ? "단원 풀이를 마쳤습니다." : "아직 풀지 않은 문제가 있습니다."}</strong>
                <p>{checkedCount === unit.questions.length ? `정답 ${correctCount}개 · 정답률 ${score}%` : `${unit.questions.length - checkedCount}문항을 더 채점하면 단원 결과가 완성됩니다.`}</p>
              </div>
              {nextUnit ? <Link className="button button-primary" href={`/workbook/${nextUnit.id}`}>다음 단원 <ArrowRight size={16} /></Link> : null}
            </footer>
          </div>
        )}
      </section>
    </div>
  );
}
