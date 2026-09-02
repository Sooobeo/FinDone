"use client";

import {
  ArrowLeft,
  ArrowRight,
  Bookmark,
  BookOpenCheck,
  Check,
  CheckCircle2,
  ChevronDown,
  CircleHelp,
  ListChecks,
  RotateCcw,
} from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState, useTransition } from "react";
import { PageHeader } from "@/components/page-header";
import { WorkbookMathText } from "@/components/workbook-math-text";
import { mergeWorkbookMathSeams } from "@/lib/workbook-math-seams";
import {
  createWorkbookProgressState,
  decodeWorkbookProgress,
  gradeSelectedWorkbookAnswers,
  gradeWorkbookAnswer,
  resolveWorkbookReview,
  retryWorkbookAnswer,
  retryWorkbookAnswers,
  selectWorkbookAnswer,
  serializeWorkbookProgress,
  toggleWorkbookBookmark,
  type QuestionProgress,
} from "@/lib/workbook-progress";
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

type StudyMode = "theory" | "quiz";
type QuestionFilter = "all" | "wrong" | "bookmarked";

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

function QuestionCard({
  question,
  number,
  record,
  onSelect,
  onCheck,
  onReset,
  onToggleBookmark,
  onResolveReview,
  onNext,
  nextLabel,
}: {
  question: WorkbookQuestion;
  number: number;
  record?: QuestionProgress;
  onSelect: (choice: number) => void;
  onCheck: () => void;
  onReset: () => void;
  onToggleBookmark: () => void;
  onResolveReview: () => void;
  onNext?: () => void;
  nextLabel: string;
}) {
  const solutionSegments = useMemo(
    () => mergeWorkbookMathSeams(question.solution, (_left, right) => !right.labelled),
    [question.solution],
  );
  const checked = record?.checked === true;
  const correct = checked && record.selected === question.answerIndex;
  const canResolveReview = correct && record.needsReview && record.correctStreak >= 2;
  const className = [
    "workbook-question",
    "panel",
    checked ? correct ? "is-correct" : "is-wrong" : "",
    record?.needsReview ? "needs-review" : "",
  ].filter(Boolean).join(" ");

  return (
    <article className={className} id={question.id} tabIndex={-1} aria-labelledby={`${question.id}-prompt`}>
      <header className="workbook-question-heading">
        <span className="workbook-question-number">{String(number).padStart(2, "0")}</span>
        <div>
          <strong>{question.id}</strong>
          <small>
            난이도 {question.difficulty} · {question.kind}
            {record?.attempts ? ` · 시도 ${record.attempts}회` : ""}
          </small>
          {record?.needsReview ? (
            <span className="workbook-review-badge">오답 복습 · 연속 정답 {Math.min(record.correctStreak, 2)}/2</span>
          ) : null}
        </div>
        <button
          className={`icon-button workbook-question-bookmark ${record?.bookmarked ? "active" : ""}`}
          type="button"
          aria-label={record?.bookmarked ? `${question.id} 북마크 해제` : `${question.id} 북마크 저장`}
          aria-pressed={record?.bookmarked === true}
          onClick={onToggleBookmark}
        >
          <Bookmark size={17} fill={record?.bookmarked ? "currentColor" : "none"} aria-hidden="true" />
        </button>
      </header>

      <h3 id={`${question.id}-prompt`}>
        <WorkbookMathText source={question.stem} className="workbook-question-stem" />
      </h3>

      <fieldset className="workbook-choices" aria-labelledby={`${question.id}-prompt`}>
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
              <WorkbookMathText source={choice} />
              {choiceCorrect ? <Check className="workbook-choice-check" size={18} aria-label="정답" /> : null}
            </label>
          );
        })}
      </fieldset>

      <footer className="workbook-question-actions">
        <p className={`workbook-answer-status ${checked ? correct ? "correct" : "wrong" : ""}`} aria-live="polite">
          {!record || record.selected === null
            ? "보기를 선택하세요."
            : !checked
              ? `${ANSWER_LABELS[record.selected]}번을 선택했습니다.`
              : correct
                ? record.needsReview
                  ? record.correctStreak >= 2
                    ? "2회 연속 정답입니다. 오답 해결 처리를 완료해 주세요."
                    : "정답입니다. 한 번 더 연속으로 맞히면 오답을 해결할 수 있습니다."
                  : "정답입니다."
                : `오답입니다. 정답은 ${ANSWER_LABELS[question.answerIndex]}번입니다.`}
        </p>
        {checked ? (
          <div className="workbook-question-action-buttons">
            <button className="button button-secondary" type="button" onClick={onReset}>
              <RotateCcw size={15} /> 다시 풀기
            </button>
            {canResolveReview ? (
              <button className="button button-primary" type="button" onClick={onResolveReview}>
                <CheckCircle2 size={15} /> 오답 해결 처리
              </button>
            ) : null}
            {onNext ? (
              <button className="button button-secondary" type="button" onClick={onNext}>
                {nextLabel} <ArrowRight size={15} />
              </button>
            ) : null}
          </div>
        ) : (
          <button className="button button-primary" type="button" onClick={onCheck} disabled={record?.selected === null || !record}>
            <Check size={15} /> 정답 확인
          </button>
        )}
      </footer>

      {checked ? (
        <details className="workbook-solution" open>
          <summary>상세 해설</summary>
          <div>
            {solutionSegments.map((segment, segmentIndex) => (
              <p className={segment.labelled ? "labelled" : undefined} key={`${question.id}-solution-${segmentIndex}`}>
                <WorkbookMathText source={segment.text} />
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
  const filterBarRef = useRef<HTMLDivElement>(null);
  const [mode, setMode] = useState<StudyMode>("theory");
  const [questionFilter, setQuestionFilter] = useState<QuestionFilter>("all");
  const [difficultyFilter, setDifficultyFilter] = useState<number | "all">("all");
  const [progress, setProgress] = useState(createWorkbookProgressState);
  const [writableStorageKey, setWritableStorageKey] = useState<string | null>(null);
  const [isNavigating, startNavigation] = useTransition();

  const flatUnits = useMemo(() => index.subjects.flatMap((subject) => subject.units), [index.subjects]);
  const unitPosition = flatUnits.findIndex((item) => item.id === unit.id);
  const previousUnit = unitPosition > 0 ? flatUnits[unitPosition - 1] : null;
  const nextUnit = unitPosition >= 0 && unitPosition < flatUnits.length - 1 ? flatUnits[unitPosition + 1] : null;
  const theoryCards = useMemo(
    () => buildTheoryCards(mergeWorkbookMathSeams(
      unit.theory,
      (left, right) => left.kind === "body" && right.kind === "body",
    )),
    [unit.theory],
  );
  const progressQuestions = useMemo(
    () => unit.questions.map(({ id, answerIndex }) => ({ id, answerIndex })),
    [unit.questions],
  );
  const questionNumbers = useMemo(
    () => new Map(unit.questions.map((question, questionIndex) => [question.id, questionIndex + 1])),
    [unit.questions],
  );
  const legacyStorageKey = `findone-workbook:${index.source.sha256}:${unit.id}`;
  const storageKey = `findone-workbook:v2:${index.source.sha256}:${unit.id}`;

  useEffect(() => {
    setWritableStorageKey(null);
    let currentStored: string | null = null;
    let legacyStored: string | null = null;
    let storageAvailable = true;
    try {
      currentStored = window.localStorage.getItem(storageKey);
      if (currentStored === null) legacyStored = window.localStorage.getItem(legacyStorageKey);
    } catch {
      storageAvailable = false;
      // The workbook still works when storage is disabled by the browser.
    }
    const decoded = decodeWorkbookProgress(currentStored ?? legacyStored, progressQuestions);
    const protectsExistingData = currentStored !== null
      && (decoded.status === "unsupported" || decoded.status === "invalid");
    setProgress(decoded.state);
    setWritableStorageKey(storageAvailable && !protectsExistingData ? storageKey : null);
  }, [legacyStorageKey, progressQuestions, storageKey]);

  useEffect(() => {
    if (writableStorageKey !== storageKey) return;
    try {
      window.localStorage.setItem(storageKey, serializeWorkbookProgress(progress));
    } catch {
      // Keep the in-memory session usable when persistent storage is unavailable.
    }
  }, [progress, storageKey, writableStorageKey]);

  const answers = progress.questions;
  const selectedCount = unit.questions.filter((question) => answers[question.id]?.selected !== null && answers[question.id]?.selected !== undefined).length;
  const checkedCount = unit.questions.filter((question) => answers[question.id]?.checked).length;
  const correctCount = unit.questions.filter((question) => {
    const record = answers[question.id];
    return record?.checked && record.selected === question.answerIndex;
  }).length;
  const wrongCount = unit.questions.filter((question) => answers[question.id]?.needsReview).length;
  const bookmarkedCount = unit.questions.filter((question) => answers[question.id]?.bookmarked).length;
  const hasSavedProgress = Object.values(answers).some((record) => (
    record.selected !== null
    || record.checked
    || record.attempts > 0
    || record.needsReview
    || record.correctStreak > 0
    || record.bookmarked
  ));
  const score = checkedCount ? Math.round((correctCount / checkedCount) * 100) : 0;
  const difficulties = useMemo(
    () => [...new Set(unit.questions.map((question) => question.difficulty))].sort((left, right) => left - right),
    [unit.questions],
  );
  const visibleQuestions = unit.questions.filter((question) => {
    const record = answers[question.id];
    const matchesStatus = questionFilter === "all"
      || questionFilter === "wrong" && record?.needsReview
      || questionFilter === "bookmarked" && record?.bookmarked;
    return matchesStatus && (difficultyFilter === "all" || question.difficulty === difficultyFilter);
  });
  const visibleCheckedCount = visibleQuestions.filter((question) => answers[question.id]?.checked).length;
  const pendingVisibleQuestions = visibleQuestions.filter((question) => {
    const record = answers[question.id];
    return record?.selected !== null && record?.selected !== undefined && !record.checked;
  });
  const visibleProgress = visibleQuestions.length
    ? Math.round((visibleCheckedCount / visibleQuestions.length) * 100)
    : 0;

  function navigateToUnit(unitId: string) {
    if (!unitId || unitId === unit.id) return;
    startNavigation(() => router.push(`/workbook/${unitId}`));
  }

  function showQuiz(filter: QuestionFilter = "all") {
    setMode("quiz");
    setQuestionFilter(filter);
    window.requestAnimationFrame(() => quizTopRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }));
  }

  function focusQuestion(questionId: string) {
    const card = document.getElementById(questionId);
    card?.scrollIntoView({ behavior: "smooth", block: "start" });
    card?.focus({ preventScroll: true });
  }

  function focusFilterBar() {
    filterBarRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    filterBarRef.current?.focus({ preventScroll: true });
  }

  function selectAnswer(questionId: string, choice: number) {
    setProgress((current) => selectWorkbookAnswer(current, questionId, choice));
  }

  function checkAnswer(question: WorkbookQuestion) {
    setProgress((current) => gradeWorkbookAnswer(current, question));
  }

  function resetAnswer(questionId: string) {
    setProgress((current) => retryWorkbookAnswer(current, questionId));
  }

  function checkSelectedAnswers() {
    setProgress((current) => gradeSelectedWorkbookAnswers(current, pendingVisibleQuestions));
  }

  function retryWrongAnswers() {
    const wrongIds = unit.questions
      .filter((question) => answers[question.id]?.needsReview)
      .map((question) => question.id);
    setProgress((current) => retryWorkbookAnswers(current, wrongIds));
    setQuestionFilter("wrong");
    setDifficultyFilter("all");
    window.requestAnimationFrame(() => filterBarRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }));
  }

  function resolveWrongAnswer(questionId: string, nextQuestionId?: string) {
    setProgress((current) => resolveWorkbookReview(current, questionId));
    window.setTimeout(() => {
      if (nextQuestionId) focusQuestion(nextQuestionId);
      else focusFilterBar();
    }, 0);
  }

  function toggleQuestionBookmark(questionId: string, nextQuestionId?: string) {
    const removesVisibleCard = questionFilter === "bookmarked" && answers[questionId]?.bookmarked;
    setProgress((current) => toggleWorkbookBookmark(current, questionId));
    if (!removesVisibleCard) return;

    window.setTimeout(() => {
      if (nextQuestionId) focusQuestion(nextQuestionId);
      else focusFilterBar();
    }, 0);
  }

  function resetUnit() {
    if (!window.confirm(`${unit.title}의 저장된 풀이 기록을 모두 지울까요?`)) return;
    setProgress(createWorkbookProgressState());
  }

  return (
    <div className="page-stack workbook-page">
      <PageHeader
        eyebrow="THEORY TO PRACTICE"
        title="FinDone 이론 문제집"
        description="개념을 먼저 익힌 뒤 단원별 30문항을 풀고, 정답과 상세 해설을 바로 확인합니다."
        actions={
          <button className="button button-primary" type="button" onClick={() => showQuiz()}>
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
        <article className="panel"><span>전체 구성</span><strong>{index.stats.subjectCount}<small>파트</small></strong><p>{index.stats.unitCount}개 단원 · {index.stats.questionCount.toLocaleString("ko-KR")}문항</p></article>
        <article className={`panel ${wrongCount ? "workbook-stat-alert" : ""}`}><span>남은 오답</span><strong>{wrongCount}<small>문항</small></strong><p>{bookmarkedCount}개 북마크</p></article>
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
            className={mode === "quiz" && questionFilter !== "wrong" ? "active" : ""}
            type="button"
            aria-pressed={mode === "quiz" && questionFilter !== "wrong"}
            onClick={() => showQuiz("all")}
          >
            <ListChecks size={17} /> 문제 풀기 <span>{checkedCount}/{unit.questions.length}</span>
          </button>
          <button
            className={mode === "quiz" && questionFilter === "wrong" ? "active" : ""}
            type="button"
            aria-pressed={mode === "quiz" && questionFilter === "wrong"}
            onClick={() => showQuiz("wrong")}
          >
            <RotateCcw size={17} /> 오답 복습 <span>{wrongCount}</span>
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
              <button className="button button-primary" type="button" onClick={() => showQuiz()}>
                문제로 넘어가기 <ArrowRight size={16} />
              </button>
            </header>
            {unit.meta.length ? <div className="workbook-meta-list">{unit.meta.map((item) => <span key={item}>{item}</span>)}</div> : null}
            <div className="workbook-theory-grid">
              {theoryCards.map((card, cardIndex) => card.kind === "divider" ? (
                <h3 className="workbook-theory-divider" key={`theory-${cardIndex}`}><WorkbookMathText source={card.blocks[0].text} /></h3>
              ) : (
                <article className="workbook-theory-card" key={`theory-${cardIndex}`}>
                  {card.blocks.map((block, blockIndex) => {
                    const key = `theory-${cardIndex}-${blockIndex}`;
                    if (block.kind === "concept" || block.kind === "element") return <h4 key={key}><WorkbookMathText source={block.text} /></h4>;
                    if (block.kind === "label") return <strong className="workbook-theory-label" key={key}><WorkbookMathText source={block.text} /></strong>;
                    return <p className={block.kind === "bullet" ? "workbook-theory-bullet" : undefined} key={key}><WorkbookMathText source={block.text} /></p>;
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
                <h2>{questionFilter === "wrong" ? "오답 복습" : questionFilter === "bookmarked" ? "북마크 복습" : "문제 풀기"}</h2>
                <p>오답은 별도로 남고 2회 연속 정답 후 직접 해결 처리할 수 있습니다. 풀이 기록은 이 브라우저에 저장됩니다.</p>
              </div>
              <div className="workbook-quiz-actions">
                <button className="button button-secondary" type="button" onClick={resetUnit} disabled={!hasSavedProgress}>
                  <RotateCcw size={15} /> 진도 초기화
                </button>
                <button className="button button-primary" type="button" onClick={checkSelectedAnswers} disabled={!pendingVisibleQuestions.length}>
                  <Check size={15} /> 선택 답안 채점
                </button>
              </div>
            </header>

            <div className="workbook-question-filterbar" ref={filterBarRef} tabIndex={-1}>
              <div>
                <strong>학습 범위</strong>
                <p className="workbook-filter-result" aria-live="polite">
                  조건에 맞는 문제 {visibleQuestions.length}개 · 남은 오답 {wrongCount}개
                </p>
              </div>
              <div className="workbook-filter-chips" role="group" aria-label="문제 상태 필터">
                <button type="button" className={questionFilter === "all" ? "active" : ""} aria-pressed={questionFilter === "all"} onClick={() => setQuestionFilter("all")}>
                  전체 <span>{unit.questions.length}</span>
                </button>
                <button type="button" className={questionFilter === "wrong" ? "active" : ""} aria-pressed={questionFilter === "wrong"} onClick={() => setQuestionFilter("wrong")}>
                  오답 <span>{wrongCount}</span>
                </button>
                <button type="button" className={questionFilter === "bookmarked" ? "active" : ""} aria-pressed={questionFilter === "bookmarked"} onClick={() => setQuestionFilter("bookmarked")}>
                  북마크 <span>{bookmarkedCount}</span>
                </button>
              </div>
              <label className="workbook-difficulty-filter">
                <span>난이도</span>
                <select
                  value={difficultyFilter}
                  onChange={(event) => setDifficultyFilter(event.target.value === "all" ? "all" : Number(event.target.value))}
                >
                  <option value="all">전체</option>
                  {difficulties.map((difficulty) => <option value={difficulty} key={difficulty}>{difficulty}</option>)}
                </select>
              </label>
              <button className="button button-secondary" type="button" onClick={retryWrongAnswers} disabled={!wrongCount}>
                <RotateCcw size={15} /> 오답 {wrongCount}문항 다시 풀기
              </button>
            </div>

            <div className="workbook-progress-summary" role="status">
              <div
                className="progress-track"
                role={visibleQuestions.length ? "progressbar" : undefined}
                aria-label={visibleQuestions.length ? "현재 표시 문제 채점 진도" : undefined}
                aria-valuemin={visibleQuestions.length ? 0 : undefined}
                aria-valuemax={visibleQuestions.length || undefined}
                aria-valuenow={visibleQuestions.length ? visibleCheckedCount : undefined}
              >
                <span style={{ width: `${visibleProgress}%` }} />
              </div>
              <p><strong>{visibleCheckedCount}/{visibleQuestions.length}</strong> 채점 · 전체 정답률 <strong>{score}%</strong></p>
            </div>

            {visibleQuestions.length ? (
              <div className="workbook-question-list">
                {visibleQuestions.map((question, visibleIndex) => {
                  const nextQuestionId = visibleQuestions[visibleIndex + 1]?.id;
                  return (
                    <QuestionCard
                      key={question.id}
                      question={question}
                      number={questionNumbers.get(question.id) ?? visibleIndex + 1}
                      record={answers[question.id]}
                      onSelect={(choice) => selectAnswer(question.id, choice)}
                      onCheck={() => checkAnswer(question)}
                      onReset={() => resetAnswer(question.id)}
                      onToggleBookmark={() => toggleQuestionBookmark(question.id, nextQuestionId)}
                      onResolveReview={() => resolveWrongAnswer(question.id, nextQuestionId)}
                      onNext={nextQuestionId ? () => focusQuestion(nextQuestionId) : undefined}
                      nextLabel={questionFilter === "wrong" ? "다음 오답" : "다음 문제"}
                    />
                  );
                })}
              </div>
            ) : (
              <section className="workbook-question-empty" role="status">
                <span className="large-state-icon state-success"><CheckCircle2 size={24} /></span>
                <div>
                  <strong>{questionFilter === "wrong" ? "남은 오답이 없습니다." : questionFilter === "bookmarked" ? "북마크한 문제가 없습니다." : "조건에 맞는 문제가 없습니다."}</strong>
                  <p>{questionFilter === "wrong" ? "새 오답이 생기면 이곳에 자동으로 모입니다." : "전체 문제에서 다른 학습 범위를 선택해 보세요."}</p>
                </div>
                <button className="button button-secondary" type="button" onClick={() => { setQuestionFilter("all"); setDifficultyFilter("all"); }}>
                  전체 문제 보기
                </button>
              </section>
            )}

            <footer className="workbook-unit-complete">
              <span className="large-state-icon state-success"><CircleHelp size={24} /></span>
              <div>
                <strong>{checkedCount === unit.questions.length ? "단원 풀이를 마쳤습니다." : "아직 풀지 않은 문제가 있습니다."}</strong>
                <p>{checkedCount === unit.questions.length ? `정답 ${correctCount}개 · 정답률 ${score}% · 남은 오답 ${wrongCount}개` : `${unit.questions.length - checkedCount}문항을 더 채점하면 단원 결과가 완성됩니다.`}</p>
              </div>
              <div className="workbook-unit-complete-actions">
                {wrongCount ? <button className="button button-secondary" type="button" onClick={() => showQuiz("wrong")}><RotateCcw size={15} /> 오답 복습</button> : null}
                {nextUnit ? <Link className="button button-primary" href={`/workbook/${nextUnit.id}`}>다음 단원 <ArrowRight size={16} /></Link> : null}
              </div>
            </footer>
          </div>
        )}
      </section>
    </div>
  );
}
