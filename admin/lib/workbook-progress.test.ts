import { describe, expect, it } from "vitest";
import {
  createWorkbookProgressState,
  decodeWorkbookProgress,
  gradeSelectedWorkbookAnswers,
  gradeWorkbookAnswer,
  parseWorkbookProgress,
  resolveWorkbookReview,
  retryWorkbookAnswer,
  retryWorkbookAnswers,
  selectWorkbookAnswer,
  serializeWorkbookProgress,
  toggleWorkbookBookmark,
  type QuestionProgress,
  type WorkbookProgressQuestion,
  type WorkbookProgressState,
} from "@/lib/workbook-progress";

const QUESTIONS: readonly WorkbookProgressQuestion[] = [
  { id: "Q1", answerIndex: 1 },
  { id: "Q2", answerIndex: 2 },
  { id: "Q3", answerIndex: 3 },
  { id: "Q4", answerIndex: 4 },
];

function progress(overrides: Partial<QuestionProgress> = {}): QuestionProgress {
  return {
    selected: null,
    checked: false,
    attempts: 0,
    needsReview: false,
    correctStreak: 0,
    bookmarked: false,
    ...overrides,
  };
}

function state(questions: Record<string, QuestionProgress> = {}): WorkbookProgressState {
  return { version: 2, questions };
}

describe("parseWorkbookProgress", () => {
  it("migrates the legacy flat answer map and identifies previously wrong answers", () => {
    const parsed = parseWorkbookProgress(JSON.stringify({
      Q1: { selected: 1, checked: true },
      Q2: { selected: 0, checked: true },
      Q3: { selected: 3, checked: false },
      unknown: { selected: 1, checked: true },
    }), QUESTIONS);

    expect(parsed).toEqual(state({
      Q1: progress({ selected: 1, checked: true, attempts: 1 }),
      Q2: progress({ selected: 0, checked: true, attempts: 1, needsReview: true }),
      Q3: progress({ selected: 3 }),
    }));
  });

  it("drops unknown questions and records with invalid selections", () => {
    const parsed = parseWorkbookProgress(JSON.stringify({
      version: 2,
      questions: {
        Q1: { selected: 5, checked: false },
        Q2: { selected: -1, checked: false },
        Q3: { selected: 2.5, checked: false },
        Q4: { selected: null, checked: true, bookmarked: true },
        unknown: { selected: 1, checked: false },
      },
    }), QUESTIONS);

    expect(parsed).toEqual(state({
      Q4: progress({ bookmarked: true }),
    }));
  });

  it("bounds history counters and safely defaults malformed metadata", () => {
    const parsed = parseWorkbookProgress(JSON.stringify({
      version: 2,
      questions: {
        Q1: {
          selected: 1,
          checked: true,
          attempts: -7,
          needsReview: "yes",
          correctStreak: 2.9,
          bookmarked: true,
        },
        Q2: {
          selected: null,
          checked: true,
          attempts: 1e30,
          needsReview: true,
          correctStreak: "3",
          bookmarked: false,
        },
      },
    }), QUESTIONS);

    expect(parsed.questions.Q1).toEqual(progress({
      selected: 1,
      checked: true,
      correctStreak: 2,
      bookmarked: true,
    }));
    expect(parsed.questions.Q2).toEqual(progress({
      attempts: Number.MAX_SAFE_INTEGER,
      needsReview: true,
    }));
  });

  it.each([null, "", "not json", "[]", "null", JSON.stringify({ version: 2, questions: [] })])(
    "returns an empty version-two state for malformed input %j",
    (value) => {
      expect(parseWorkbookProgress(value, QUESTIONS)).toEqual(createWorkbookProgressState());
    },
  );

  it("distinguishes legacy, current, invalid, and unsupported storage", () => {
    expect(decodeWorkbookProgress(null, QUESTIONS).status).toBe("empty");
    expect(decodeWorkbookProgress(JSON.stringify({ Q1: { selected: 1 } }), QUESTIONS).status).toBe("migrated-legacy");
    expect(decodeWorkbookProgress(JSON.stringify({ version: 2, questions: {} }), QUESTIONS).status).toBe("valid-v2");
    expect(decodeWorkbookProgress(JSON.stringify({ version: 3, questions: {} }), QUESTIONS).status).toBe("unsupported");
    expect(decodeWorkbookProgress(JSON.stringify({ questions: {} }), QUESTIONS).status).toBe("invalid");
  });
});

describe("serializeWorkbookProgress", () => {
  it("always writes the version-two envelope", () => {
    const value = state({
      Q1: progress({ selected: 1, checked: true, attempts: 3, bookmarked: true }),
    });

    expect(JSON.parse(serializeWorkbookProgress(value))).toEqual(value);
  });
});

describe("workbook answer transitions", () => {
  it("selects an answer without losing history and refuses to change a checked answer", () => {
    const initial = state({
      Q1: progress({ attempts: 4, needsReview: true, correctStreak: 1, bookmarked: true }),
    });
    const selected = selectWorkbookAnswer(initial, "Q1", 1);

    expect(selected.questions.Q1).toEqual(progress({
      selected: 1,
      attempts: 4,
      needsReview: true,
      correctStreak: 1,
      bookmarked: true,
    }));

    const checked = gradeWorkbookAnswer(selected, QUESTIONS[0]);
    expect(selectWorkbookAnswer(checked, "Q1", 3)).toBe(checked);
  });

  it("requires two correct retries and an explicit action to resolve an error", () => {
    let current = selectWorkbookAnswer(createWorkbookProgressState(), "Q1", 0);
    current = gradeWorkbookAnswer(current, QUESTIONS[0]);
    expect(current.questions.Q1).toEqual(progress({
      selected: 0,
      checked: true,
      attempts: 1,
      needsReview: true,
    }));
    expect(resolveWorkbookReview(current, "Q1")).toBe(current);

    current = retryWorkbookAnswer(current, "Q1");
    current = selectWorkbookAnswer(current, "Q1", 1);
    current = gradeWorkbookAnswer(current, QUESTIONS[0]);
    expect(current.questions.Q1).toMatchObject({
      attempts: 2,
      needsReview: true,
      correctStreak: 1,
    });
    expect(resolveWorkbookReview(current, "Q1")).toBe(current);

    current = retryWorkbookAnswer(current, "Q1");
    current = selectWorkbookAnswer(current, "Q1", 1);
    current = gradeWorkbookAnswer(current, QUESTIONS[0]);
    expect(current.questions.Q1).toMatchObject({
      attempts: 3,
      needsReview: true,
      correctStreak: 2,
    });

    current = resolveWorkbookReview(current, "Q1");
    expect(current.questions.Q1).toMatchObject({ needsReview: false, correctStreak: 2 });
  });

  it("resets an unresolved correct streak after another wrong answer", () => {
    let current = state({
      Q2: progress({ attempts: 2, needsReview: true, correctStreak: 1 }),
    });
    current = selectWorkbookAnswer(current, "Q2", 0);
    current = gradeWorkbookAnswer(current, QUESTIONS[1]);

    expect(current.questions.Q2).toMatchObject({
      checked: true,
      attempts: 3,
      needsReview: true,
      correctStreak: 0,
    });
  });

  it("does not create a review streak for a question that was never wrong", () => {
    let current = selectWorkbookAnswer(createWorkbookProgressState(), "Q3", 3);
    current = gradeWorkbookAnswer(current, QUESTIONS[2]);

    expect(current.questions.Q3).toMatchObject({
      attempts: 1,
      needsReview: false,
      correctStreak: 0,
    });
  });

  it("batch grades only selected, unchecked answers", () => {
    const initial = state({
      Q1: progress({ selected: 0 }),
      Q2: progress({ selected: 2, checked: true, attempts: 4 }),
      Q3: progress({ selected: 3 }),
      Q4: progress({ bookmarked: true }),
    });
    const graded = gradeSelectedWorkbookAnswers(initial, QUESTIONS);

    expect(graded.questions.Q1).toMatchObject({ checked: true, attempts: 1, needsReview: true });
    expect(graded.questions.Q2).toEqual(initial.questions.Q2);
    expect(graded.questions.Q3).toMatchObject({ checked: true, attempts: 1, needsReview: false });
    expect(graded.questions.Q4).toEqual(initial.questions.Q4);
  });

  it("does not grade selected questions omitted from a filtered batch", () => {
    const initial = state({
      Q1: progress({ selected: 0 }),
      Q2: progress({ selected: 2 }),
    });
    const graded = gradeSelectedWorkbookAnswers(initial, [QUESTIONS[0]]);

    expect(graded.questions.Q1).toMatchObject({ checked: true, attempts: 1 });
    expect(graded.questions.Q2).toEqual(initial.questions.Q2);
  });

  it("retries one or many answers while preserving review, bookmark, and history", () => {
    const initial = state({
      Q1: progress({ selected: 0, checked: true, attempts: 3, needsReview: true, correctStreak: 1, bookmarked: true }),
      Q2: progress({ selected: 2, checked: true, attempts: 2 }),
      Q3: progress({ selected: 3 }),
    });
    const one = retryWorkbookAnswer(initial, "Q1");

    expect(one.questions.Q1).toEqual(progress({
      attempts: 3,
      needsReview: true,
      correctStreak: 1,
      bookmarked: true,
    }));

    const many = retryWorkbookAnswers(initial, ["Q1", "Q2", "Q1"]);
    expect(many.questions.Q1).toEqual(one.questions.Q1);
    expect(many.questions.Q2).toEqual(progress({ attempts: 2 }));
    expect(many.questions.Q3).toEqual(initial.questions.Q3);
  });

  it("toggles a bookmark even before a question has been answered", () => {
    const bookmarked = toggleWorkbookBookmark(createWorkbookProgressState(), "Q4");
    expect(bookmarked.questions.Q4).toEqual(progress({ bookmarked: true }));

    const cleared = toggleWorkbookBookmark(bookmarked, "Q4");
    expect(cleared.questions.Q4).toBeUndefined();
  });
});
