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
        queue: [{
          questionId: "CF-07-core_relation_to_term-01",
          questionFingerprint: "a".repeat(64),
          severity: "review",
        }],
        reviewInputSha256: "c".repeat(64),
      },
    }],
  },
}));

import { POST } from "@/app/api/model/review/route";

function request(body: Record<string, unknown>) {
  return new Request("http://localhost/api/model/review", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

describe("concept model review route", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.getAdminContext.mockResolvedValue({ user: { id: "owner-user-id" } });
    mocks.getAdminCapabilities.mockResolvedValue({ canReview: true });
    mocks.rpc.mockResolvedValue({
      data: { concept_question_review_decision_id: "decision-id" },
      error: null,
    });
  });

  it("records an owner decision only for the exact current fingerprint", async () => {
    const response = await POST(request({
      questionId: "CF-07-core_relation_to_term-01",
      questionFingerprint: "a".repeat(64),
      decision: "approved",
      comment: "선택지 확인 완료",
    }));

    expect(response.status).toBe(200);
    expect(mocks.rpc).toHaveBeenCalledWith("submit_concept_question_review", {
      p_review_input_sha256: "c".repeat(64),
      p_question_id: "CF-07-core_relation_to_term-01",
      p_question_fingerprint: "a".repeat(64),
      p_decision: "approved",
      p_comment: "선택지 확인 완료",
    });
  });

  it("rejects a stale fingerprint", async () => {
    const response = await POST(request({
      questionId: "CF-07-core_relation_to_term-01",
      questionFingerprint: "b".repeat(64),
      decision: "approved",
    }));

    expect(response.status).toBe(409);
    expect(mocks.rpc).not.toHaveBeenCalled();
  });

  it("requires a reason when rejecting", async () => {
    const response = await POST(request({
      questionId: "CF-07-core_relation_to_term-01",
      questionFingerprint: "a".repeat(64),
      decision: "rejected",
      comment: "",
    }));

    expect(response.status).toBe(400);
    expect(mocks.rpc).not.toHaveBeenCalled();
  });

  it("rejects users without review capability", async () => {
    mocks.getAdminCapabilities.mockResolvedValue({ canReview: false });
    const response = await POST(request({
      questionId: "CF-07-core_relation_to_term-01",
      questionFingerprint: "a".repeat(64),
      decision: "approved",
    }));

    expect(response.status).toBe(403);
    expect(mocks.rpc).not.toHaveBeenCalled();
  });
});
