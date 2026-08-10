import { describe, expect, it } from "vitest";
import { parsePublicSourceUrl } from "@/lib/source-url";

describe("parsePublicSourceUrl", () => {
  it("accepts ordinary public HTTP and HTTPS URLs", () => {
    expect(parsePublicSourceUrl("https://example.com/report.pdf").hostname).toBe("example.com");
    expect(parsePublicSourceUrl("http://research.example.org/page").protocol).toBe("http:");
  });

  it("rejects credentials, local names, and IP literals", () => {
    for (const value of [
      "https://user:pass@example.com/",
      "http://localhost/admin",
      "http://metadata.internal/",
      "http://127.0.0.1/",
      "http://169.254.169.254/latest/meta-data/",
      "http://[::1]/",
      "https://foo.127.0.0.1.nip.io/",
      "https://example..com/",
    ]) {
      expect(() => parsePublicSourceUrl(value)).toThrow();
    }
  });
});
