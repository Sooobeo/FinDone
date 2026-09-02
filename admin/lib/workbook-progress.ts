export const WORKBOOK_PROGRESS_VERSION = 2 as const;

export interface QuestionProgress {
  selected: number | null;
  checked: boolean;
  attempts: number;
  needsReview: boolean;
  correctStreak: number;
  bookmarked: boolean;
}

export interface WorkbookProgressState {
  version: typeof WORKBOOK_PROGRESS_VERSION;
  questions: Record<string, QuestionProgress>;
}

export interface WorkbookProgressQuestion {
  id: string;
  answerIndex: number;
}

export type WorkbookProgressParseStatus =
  | "empty"
  | "valid-v2"
  | "migrated-legacy"
  | "unsupported"
  | "invalid";

export interface WorkbookProgressParseResult {
  state: WorkbookProgressState;
  status: WorkbookProgressParseStatus;
}

const MAX_CHOICE_INDEX = 4;

function isObject(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function isChoiceIndex(value: unknown): value is number {
  return Number.isInteger(value) && Number(value) >= 0 && Number(value) <= MAX_CHOICE_INDEX;
}

function boundedNonNegativeInteger(value: unknown): number {
  if (typeof value !== "number" || !Number.isFinite(value)) return 0;
  return Math.min(Number.MAX_SAFE_INTEGER, Math.max(0, Math.trunc(value)));
}

function emptyQuestionProgress(): QuestionProgress {
  return {
    selected: null,
    checked: false,
    attempts: 0,
    needsReview: false,
    correctStreak: 0,
    bookmarked: false,
  };
}

function isEmptyQuestionProgress(progress: QuestionProgress): boolean {
  return progress.selected === null
    && !progress.checked
    && progress.attempts === 0
    && !progress.needsReview
    && progress.correctStreak === 0
    && !progress.bookmarked;
}

export function createWorkbookProgressState(): WorkbookProgressState {
  return {
    version: WORKBOOK_PROGRESS_VERSION,
    questions: {},
  };
}

function parseVersionTwoRecord(value: unknown): QuestionProgress | null {
  if (!isObject(value)) return null;
  if (value.selected !== null && !isChoiceIndex(value.selected)) return null;

  const selected = value.selected as number | null;
  return {
    selected,
    checked: selected !== null && value.checked === true,
    attempts: boundedNonNegativeInteger(value.attempts),
    needsReview: value.needsReview === true,
    correctStreak: boundedNonNegativeInteger(value.correctStreak),
    bookmarked: value.bookmarked === true,
  };
}

function parseLegacyRecord(value: unknown, answerIndex: number): QuestionProgress | null {
  if (!isObject(value) || !isChoiceIndex(value.selected)) return null;

  const checked = value.checked === true;
  const isWrong = checked && value.selected !== answerIndex;
  return {
    selected: value.selected,
    checked,
    attempts: checked ? 1 : 0,
    needsReview: isWrong,
    correctStreak: 0,
    bookmarked: false,
  };
}

export function decodeWorkbookProgress(
  value: string | null | undefined,
  questions: readonly WorkbookProgressQuestion[],
): WorkbookProgressParseResult {
  if (!value) return { state: createWorkbookProgressState(), status: "empty" };

  let parsed: unknown;
  try {
    parsed = JSON.parse(value) as unknown;
  } catch {
    return { state: createWorkbookProgressState(), status: "invalid" };
  }

  if (!isObject(parsed)) return { state: createWorkbookProgressState(), status: "invalid" };

  const knownQuestions = new Map(
    questions
      .filter((question) => question.id.length > 0 && isChoiceIndex(question.answerIndex))
      .map((question) => [question.id, question.answerIndex]),
  );
  const hasVersion = Object.prototype.hasOwnProperty.call(parsed, "version");
  if (hasVersion && parsed.version !== WORKBOOK_PROGRESS_VERSION) {
    return { state: createWorkbookProgressState(), status: "unsupported" };
  }

  const versionTwo = hasVersion;
  if (!versionTwo && Object.prototype.hasOwnProperty.call(parsed, "questions")) {
    return { state: createWorkbookProgressState(), status: "invalid" };
  }

  const storedQuestions = versionTwo ? parsed.questions : parsed;
  if (!isObject(storedQuestions)) {
    return { state: createWorkbookProgressState(), status: "invalid" };
  }

  const progress: Record<string, QuestionProgress> = {};
  for (const [questionId, stored] of Object.entries(storedQuestions)) {
    const answerIndex = knownQuestions.get(questionId);
    if (answerIndex === undefined) continue;

    const record = versionTwo
      ? parseVersionTwoRecord(stored)
      : parseLegacyRecord(stored, answerIndex);
    if (record) progress[questionId] = record;
  }

  return {
    state: {
      version: WORKBOOK_PROGRESS_VERSION,
      questions: progress,
    },
    status: versionTwo ? "valid-v2" : "migrated-legacy",
  };
}

export function parseWorkbookProgress(
  value: string | null | undefined,
  questions: readonly WorkbookProgressQuestion[],
): WorkbookProgressState {
  return decodeWorkbookProgress(value, questions).state;
}

export function serializeWorkbookProgress(state: WorkbookProgressState): string {
  return JSON.stringify({
    version: WORKBOOK_PROGRESS_VERSION,
    questions: state.questions,
  } satisfies WorkbookProgressState);
}

export function selectWorkbookAnswer(
  state: WorkbookProgressState,
  questionId: string,
  selected: number,
): WorkbookProgressState {
  if (!questionId || !isChoiceIndex(selected)) return state;

  const current = state.questions[questionId];
  if (current?.checked || current?.selected === selected) return state;

  return {
    ...state,
    questions: {
      ...state.questions,
      [questionId]: {
        ...(current ?? emptyQuestionProgress()),
        selected,
        checked: false,
      },
    },
  };
}

export function gradeWorkbookAnswer(
  state: WorkbookProgressState,
  question: WorkbookProgressQuestion,
): WorkbookProgressState {
  const current = state.questions[question.id];
  if (!current || current.selected === null || current.checked || !isChoiceIndex(question.answerIndex)) return state;

  const correct = current.selected === question.answerIndex;
  const next: QuestionProgress = {
    ...current,
    checked: true,
    attempts: Math.min(Number.MAX_SAFE_INTEGER, current.attempts + 1),
    needsReview: correct ? current.needsReview : true,
    correctStreak: correct && current.needsReview
      ? Math.min(Number.MAX_SAFE_INTEGER, current.correctStreak + 1)
      : 0,
  };

  return {
    ...state,
    questions: {
      ...state.questions,
      [question.id]: next,
    },
  };
}

export function gradeSelectedWorkbookAnswers(
  state: WorkbookProgressState,
  questions: readonly WorkbookProgressQuestion[],
): WorkbookProgressState {
  let next = state;
  for (const question of questions) {
    next = gradeWorkbookAnswer(next, question);
  }
  return next;
}

export function retryWorkbookAnswer(
  state: WorkbookProgressState,
  questionId: string,
): WorkbookProgressState {
  const current = state.questions[questionId];
  if (!current || (current.selected === null && !current.checked)) return state;

  return {
    ...state,
    questions: {
      ...state.questions,
      [questionId]: {
        ...current,
        selected: null,
        checked: false,
      },
    },
  };
}

export function retryWorkbookAnswers(
  state: WorkbookProgressState,
  questionIds: readonly string[],
): WorkbookProgressState {
  let next = state;
  for (const questionId of new Set(questionIds)) {
    next = retryWorkbookAnswer(next, questionId);
  }
  return next;
}

export function resolveWorkbookReview(
  state: WorkbookProgressState,
  questionId: string,
): WorkbookProgressState {
  const current = state.questions[questionId];
  if (!current?.needsReview || current.correctStreak < 2) return state;

  return {
    ...state,
    questions: {
      ...state.questions,
      [questionId]: {
        ...current,
        needsReview: false,
      },
    },
  };
}

export function toggleWorkbookBookmark(
  state: WorkbookProgressState,
  questionId: string,
): WorkbookProgressState {
  if (!questionId) return state;

  const current = state.questions[questionId] ?? emptyQuestionProgress();
  const next = {
    ...current,
    bookmarked: !current.bookmarked,
  };

  if (isEmptyQuestionProgress(next)) {
    const questions = { ...state.questions };
    delete questions[questionId];
    return { ...state, questions };
  }

  return {
    ...state,
    questions: {
      ...state.questions,
      [questionId]: next,
    },
  };
}
