import { describe, expect, it } from "vitest";
import {
  hasActiveSourceProcessing,
  mergeSourceStatus,
  sourceStatusPresentation,
} from "@/lib/source-processing";
import type { SourceItem } from "@/lib/types";

const base: SourceItem = {
  id: "source-1",
  label: "sample.pdf",
  kind: "pdf",
  locator: "private/sample.pdf",
  status: "processing",
  linkedElements: 0,
  domains: [],
  createdAt: "now",
};

describe("source processing state", () => {
  it("shows queued and running work as loading with progress", () => {
    expect(sourceStatusPresentation({ ...base, jobStatus: "queued" })).toMatchObject({
      label: "가공 대기 중",
      loading: true,
      progress: 0,
    });
    expect(sourceStatusPresentation({
      ...base,
      jobStatus: "running",
      processingStage: "ocr",
      progressPercent: 64,
    })).toEqual({ label: "OCR 인식 중", detail: "64% 진행", loading: true, progress: 64 });
    expect(sourceStatusPresentation({
      ...base,
      jobStatus: "running",
      processingStage: "archiving",
      progressPercent: 40,
    }).label).toBe("원본 snapshot 보관 중");
  });

  it("merges database job fields and stops polling on completion", () => {
    const merged = mergeSourceStatus(base, {
      latest_parse_status: "ready",
      latest_job_status: "succeeded",
      latest_job_progress_percent: 100,
      latest_processing_stage: "completed",
      linked_element_count: 1,
      candidate_count: 3,
      top_candidate_element_id: "CF-01",
      top_candidate_score: "0.96",
    });
    expect(merged).toMatchObject({
      status: "ready",
      jobStatus: "succeeded",
      progressPercent: 100,
      linkedElements: 1,
      candidateCount: 3,
      topCandidateElementId: "CF-01",
      topCandidateScore: 0.96,
    });
    expect(hasActiveSourceProcessing(merged)).toBe(false);
    expect(sourceStatusPresentation(merged).detail).toContain("CF-01");
  });

  it("stops the spinner once a queued job has clearly outlived the worker", () => {
    const now = Date.parse("2026-08-17T12:00:00Z");
    const queuedAt = (minutesAgo: number) => ({
      ...base,
      jobStatus: "queued" as const,
      processingUpdatedAt: new Date(now - minutesAgo * 60_000).toISOString(),
    });

    const fresh = queuedAt(2);
    expect(hasActiveSourceProcessing(fresh, now)).toBe(true);
    expect(sourceStatusPresentation(fresh, now)).toMatchObject({ label: "가공 대기 중", loading: true });

    const abandoned = queuedAt(40);
    expect(hasActiveSourceProcessing(abandoned, now)).toBe(false);
    expect(sourceStatusPresentation(abandoned, now)).toMatchObject({
      label: "Worker 대기 초과",
      loading: false,
    });

    const unresponsive = { ...base, jobStatus: "running" as const, processingUpdatedAt: new Date(now - 40 * 60_000).toISOString() };
    expect(hasActiveSourceProcessing(unresponsive, now)).toBe(false);
    expect(sourceStatusPresentation(unresponsive, now)).toMatchObject({ label: "Worker 응답 없음", loading: false });

    // Without a timestamp we cannot tell age, so never accuse a live worker.
    expect(hasActiveSourceProcessing({ ...base, jobStatus: "queued" }, now)).toBe(true);
  });

  it("surfaces the worker failure instead of an endless spinner", () => {
    const failed = mergeSourceStatus(base, {
      latest_parse_status: "failed",
      latest_job_status: "failed",
      latest_job_error_message: "PDF가 손상되었습니다",
    });
    expect(hasActiveSourceProcessing(failed)).toBe(false);
    expect(sourceStatusPresentation(failed)).toMatchObject({
      label: "처리 실패",
      detail: "PDF가 손상되었습니다",
      loading: false,
    });
    const cancelled = { ...base, jobStatus: "cancelled" as const };
    expect(hasActiveSourceProcessing(cancelled)).toBe(false);
    expect(sourceStatusPresentation(cancelled)).toMatchObject({ label: "처리 취소됨", loading: false });
  });
});
