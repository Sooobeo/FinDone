export const SOURCE_FILE_ACCEPT = ".pdf,.docx,.xlsx,.pptx,.csv,.md,.markdown,.txt,.html,.htm,.png,.jpg,.jpeg,.webp";
export const SOURCE_FILE_SUPPORT_LABEL = "PDF · Office · 표 · 텍스트 · HTML · 이미지";

const SOURCE_MIME_BY_EXTENSION: Record<string, string> = {
  pdf: "application/pdf",
  docx: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  xlsx: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  pptx: "application/vnd.openxmlformats-officedocument.presentationml.presentation",
  csv: "text/csv",
  md: "text/markdown",
  markdown: "text/markdown",
  txt: "text/plain",
  html: "text/html",
  htm: "text/html",
  png: "image/png",
  jpg: "image/jpeg",
  jpeg: "image/jpeg",
  webp: "image/webp",
};

export interface SourceFileDescriptor {
  name: string;
  size: number;
}

export type SourceFileRejectionReason = "unsupported" | "empty";

export interface RejectedSourceFile<T extends SourceFileDescriptor> {
  file: T;
  reason: SourceFileRejectionReason;
}

export function sourceMimeType(file: Pick<SourceFileDescriptor, "name">): string | null {
  const extension = file.name.toLocaleLowerCase("en-US").split(".").pop() ?? "";
  return SOURCE_MIME_BY_EXTENSION[extension] ?? null;
}

export function classifySourceFiles<T extends SourceFileDescriptor>(files: readonly T[]): {
  accepted: T[];
  rejected: RejectedSourceFile<T>[];
} {
  const accepted: T[] = [];
  const rejected: RejectedSourceFile<T>[] = [];

  for (const file of files) {
    const reason = !sourceMimeType(file)
      ? "unsupported"
      : file.size <= 0
        ? "empty"
        : null;
    if (reason) rejected.push({ file, reason });
    else accepted.push(file);
  }

  return { accepted, rejected };
}

export function sourceFileRejectionSummary(rejected: RejectedSourceFile<SourceFileDescriptor>[]): string {
  const count = (reason: SourceFileRejectionReason) => rejected.filter((item) => item.reason === reason).length;
  return [
    ["지원하지 않는 형식", count("unsupported")],
    ["빈 파일", count("empty")],
  ]
    .filter(([, value]) => Number(value) > 0)
    .map(([label, value]) => `${label} ${value}개`)
    .join(" · ");
}
