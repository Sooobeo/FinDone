import { describe, expect, it } from "vitest";
import {
  buildSupabaseTusEndpoint,
  sha256FileInChunks,
  sourceUploadErrorMessage,
} from "@/lib/source-upload";

describe("resumable source uploads", () => {
  it("uses Supabase's direct storage hostname for hosted projects", () => {
    expect(buildSupabaseTusEndpoint("https://abcdefgh.supabase.co")).toBe(
      "https://abcdefgh.storage.supabase.co/storage/v1/upload/resumable",
    );
  });

  it("keeps local and custom project hosts", () => {
    expect(buildSupabaseTusEndpoint("http://127.0.0.1:54321")).toBe(
      "http://127.0.0.1:54321/storage/v1/upload/resumable",
    );
    expect(buildSupabaseTusEndpoint("https://db.example.com/base")).toBe(
      "https://db.example.com/storage/v1/upload/resumable",
    );
  });

  it("hashes a blob incrementally without loading the entire file at once", async () => {
    const progress: number[] = [];
    const digest = await sha256FileInChunks(
      new Blob(["abc"]),
      (bytesHashed) => progress.push(bytesHashed),
      2,
    );

    expect(digest).toBe("ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad");
    expect(progress).toEqual([2, 3]);
  });

  it("turns provider size failures into an actionable message", () => {
    expect(sourceUploadErrorMessage(new Error("File size exceeds the maximum allowed size"))).toContain(
      "Global file size limit",
    );
  });
});
