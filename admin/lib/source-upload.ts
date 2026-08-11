import { createSHA256 } from "hash-wasm";
import {
  defaultOptions,
  DetailedError,
  isSupported as isTusSupported,
  Upload,
} from "tus-js-client";

export const SUPABASE_TUS_CHUNK_BYTES = 6 * 1024 * 1024;

interface ResumableSourceUploadOptions {
  file: File;
  bucketName: string;
  objectPath: string;
  contentType: string;
  projectUrl: string;
  getAccessToken: () => Promise<string | null>;
  onProgress?: (bytesUploaded: number, bytesTotal: number) => void;
  onRetry?: (attempt: number) => void;
  onResume?: () => void;
}

export interface ResumableSourceUploadResult {
  resumed: boolean;
}

export function buildSupabaseTusEndpoint(projectUrl: string): string {
  const url = new URL(projectUrl);
  const hostedSuffix = ".supabase.co";

  if (url.hostname.endsWith(hostedSuffix)) {
    const projectRef = url.hostname.slice(0, -hostedSuffix.length);
    return `${url.protocol}//${projectRef}.storage.supabase.co/storage/v1/upload/resumable`;
  }

  return new URL("/storage/v1/upload/resumable", url).toString();
}

export async function sha256FileInChunks(
  file: Blob,
  onProgress?: (bytesHashed: number, bytesTotal: number) => void,
  chunkSize = SUPABASE_TUS_CHUNK_BYTES,
): Promise<string> {
  const hasher = await createSHA256();
  hasher.init();

  for (let offset = 0; offset < file.size; offset += chunkSize) {
    const end = Math.min(offset + chunkSize, file.size);
    const chunk = new Uint8Array(await file.slice(offset, end).arrayBuffer());
    hasher.update(chunk);
    onProgress?.(end, file.size);

    if (end < file.size) await yieldToBrowser();
  }

  return hasher.digest("hex");
}

export async function uploadSourceFileResumable(
  options: ResumableSourceUploadOptions,
): Promise<ResumableSourceUploadResult> {
  if (!isTusSupported) {
    throw new Error("이 브라우저는 재개 가능한 파일 업로드를 지원하지 않습니다. 최신 브라우저에서 다시 시도해 주세요.");
  }

  const initialAccessToken = await options.getAccessToken();
  if (!initialAccessToken) throw new Error("로그인 세션이 만료되었습니다. 다시 로그인해 주세요.");

  return new Promise((resolve, reject) => {
    let resumed = false;
    const upload = new Upload(options.file, {
      endpoint: buildSupabaseTusEndpoint(options.projectUrl),
      retryDelays: [0, 3_000, 5_000, 10_000, 20_000],
      headers: {
        authorization: `Bearer ${initialAccessToken}`,
        "x-upsert": "false",
      },
      uploadDataDuringCreation: true,
      removeFingerprintOnSuccess: true,
      chunkSize: SUPABASE_TUS_CHUNK_BYTES,
      fingerprint: () => Promise.resolve([
        "findone-source-v1",
        options.objectPath,
        options.file.name,
        options.file.size,
        options.file.lastModified,
      ].join(":")),
      metadata: {
        bucketName: options.bucketName,
        objectName: options.objectPath,
        contentType: options.contentType,
        cacheControl: "3600",
      },
      onBeforeRequest: async (request) => {
        const accessToken = await options.getAccessToken();
        if (!accessToken) throw new Error("로그인 세션이 만료되었습니다. 다시 로그인해 주세요.");
        request.setHeader("authorization", `Bearer ${accessToken}`);
      },
      onProgress: (bytesUploaded, bytesTotal) => options.onProgress?.(bytesUploaded, bytesTotal),
      onShouldRetry: (error, retryAttempt, uploadOptions) => {
        const shouldRetry = defaultOptions.onShouldRetry?.(error, retryAttempt, uploadOptions) ?? false;
        if (shouldRetry) options.onRetry?.(retryAttempt + 1);
        return shouldRetry;
      },
      onError: reject,
      onSuccess: () => resolve({ resumed }),
    });

    void upload.findPreviousUploads()
      .then((previousUploads) => {
        const previous = previousUploads.find((candidate) => (
          candidate.metadata.bucketName === options.bucketName
          && candidate.metadata.objectName === options.objectPath
        ));
        if (previous) {
          resumed = true;
          options.onResume?.();
          upload.resumeFromPreviousUpload(previous);
        }
        upload.start();
      })
      .catch(reject);
  });
}

export function sourceUploadErrorMessage(error: unknown): string {
  const status = error instanceof DetailedError ? error.originalResponse?.getStatus() : undefined;
  const responseBody = error instanceof DetailedError ? error.originalResponse?.getBody() : "";
  const rawMessage = error instanceof Error ? error.message : "알 수 없는 오류";
  const searchable = `${rawMessage} ${responseBody}`.toLocaleLowerCase("en-US");

  if (status === 413 || /too large|maximum.*size|file.*size.*limit|payload.*large/.test(searchable)) {
    return "Supabase Storage의 파일 크기 한도를 초과했습니다. Storage Settings의 Global file size limit를 확인해 주세요.";
  }
  if (status === 401 || /unauthorized|jwt.*expired|invalid.*jwt/.test(searchable)) {
    return "로그인 세션이 만료되었습니다. 다시 로그인한 뒤 같은 파일을 선택하면 중단 지점부터 이어서 시도합니다.";
  }
  if (status === 403 || /row-level security|permission|forbidden/.test(searchable)) {
    return "원본 저장 권한이 없습니다. Owner 계정으로 로그인했는지 확인해 주세요.";
  }
  if (status === 409 || /conflict|already exists/.test(searchable)) {
    return "같은 파일 경로에 다른 업로드가 진행 중입니다. 잠시 후 다시 시도해 주세요.";
  }

  return rawMessage;
}

async function yieldToBrowser(): Promise<void> {
  await new Promise<void>((resolve) => {
    if (typeof requestAnimationFrame === "function") requestAnimationFrame(() => resolve());
    else setTimeout(resolve, 0);
  });
}
