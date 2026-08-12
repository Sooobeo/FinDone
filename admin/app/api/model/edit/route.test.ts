import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  getAdminContext: vi.fn(),
  getAdminCapabilities: vi.fn(),
  rpc: vi.fn(),
}));

vi.mock("@/lib/auth", () => ({ getAdminContext: mocks.getAdminContext }));
vi.mock("@/lib/data", () => ({ getAdminCapabilities: mocks.getAdminCapabilities }));
vi.mock("@/lib/supabase/server", () => ({
  getServerSupabase: vi.fn(async () => ({ rpc: mocks.rpc })),
}));
vi.mock("@/lib/concept-model-report", () => ({
  conceptModelExperiments: {
    experiments: [{
      automatedReview: {
        reviewInputSha256: "c".repeat(64),
        queue: [{
          questionId: "CF-07-term_to_verbal_relation-01",
          elementId: "CF-07",
          questionFingerprint: "a".repeat(64),
          severity: "block",
        }],
      },
    }],
  },
}));

import { POST } from "@/app/api/model/edit/route";

function request(body: Record<string, unknown>) {
  return new Request("http://localhost/api/model/edit", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

function choices() {
  return ["A", "B", "C", "D", "E"].map((key, index) => ({
    key,
    elementId: index === 0 ? "CF-07" : `CF-${String(index + 10).padStart(2, "0")}`,
    text: `choice-${key}`,
    explanation: `explanation-${key}`,
    isCorrect: index === 0,
  }));
}

describe("concept model edit route", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.getAdminContext.mockResolvedValue({ user: { id: "owner-user-id" } });
    mocks.getAdminCapabilities.mockResolvedValue({ canEdit: true });
    mocks.rpc.mockResolvedValue({
      data: { concept_question_edit_id: "edit-id" },
      error: null,
    });
  });

  it("records a valid edit for the exact current fingerprint", async () => {
    const response = await POST(request({
      questionId: "CF-07-term_to_verbal_relation-01",
      questionFingerprint: "a".repeat(64),
      stem: "edited stem",
      explanation: "edited explanation",
      choices: choices(),
      comment: "fixed answer leak",
    }));

    expect(response.status).toBe(200);
    expect(mocks.rpc).toHaveBeenCalledWith("submit_concept_question_edit", expect.objectContaining({
      p_review_input_sha256: "c".repeat(64),
      p_question_id: "CF-07-term_to_verbal_relation-01",
      p_question_fingerprint: "a".repeat(64),
      p_element_id: "CF-07",
    }));
  });

  it("rejects a stale fingerprint", async () => {
    const response = await POST(request({
      questionId: "CF-07-term_to_verbal_relation-01",
      questionFingerprint: "b".repeat(64),
      stem: "edited stem",
      explanation: "edited explanation",
      choices: choices(),
    }));

    expect(response.status).toBe(409);
    expect(mocks.rpc).not.toHaveBeenCalled();
  });

  it("rejects a changed correct target", async () => {
    const changedChoices = choices();
    changedChoices[0].elementId = "CF-99";
    const response = await POST(request({
      questionId: "CF-07-term_to_verbal_relation-01",
      questionFingerprint: "a".repeat(64),
      stem: "edited stem",
      explanation: "edited explanation",
      choices: changedChoices,
    }));

    expect(response.status).toBe(400);
    expect(mocks.rpc).not.toHaveBeenCalled();
  });

  it("rejects users without edit capability", async () => {
    mocks.getAdminCapabilities.mockResolvedValue({ canEdit: false });
    const response = await POST(request({}));

    expect(response.status).toBe(403);
    expect(mocks.rpc).not.toHaveBeenCalled();
  });
});
