"use client";

import {
  AlertTriangle,
  ArrowUpRight,
  CheckCircle2,
  ChevronDown,
  File,
  FileSpreadsheet,
  FileText,
  Globe2,
  Link2,
  LoaderCircle,
  Pause,
  Play,
  Plus,
  RefreshCw,
  Search,
  UploadCloud,
  Trash2,
  X,
} from "lucide-react";
import { ChangeEvent, DragEvent, FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { PageHeader } from "@/components/page-header";
import {
  ALL_SOURCE_DOMAINS,
  filterSources,
  sourceDomainOptions,
  UNASSIGNED_SOURCE_DOMAIN,
} from "@/lib/source-filter";
import {
  classifySourceFiles,
  SOURCE_FILE_ACCEPT,
  SOURCE_FILE_SUPPORT_LABEL,
  sourceFileRejectionSummary,
  sourceMimeType,
} from "@/lib/source-files";
import {
  sha256FileInChunks,
  sourceUploadErrorMessage,
  uploadSourceFileResumable,
} from "@/lib/source-upload";
import {
  hasActiveSourceProcessing,
  mergeSourceStatus,
  sourceStatusPresentation,
  type SourceStatusRow,
} from "@/lib/source-processing";
import { parsePublicSourceUrl } from "@/lib/source-url";
import { getBrowserSupabase } from "@/lib/supabase/browser";
import { supabaseUrl } from "@/lib/supabase/config";
import type { SourceItem } from "@/lib/types";

interface StagedFile {
  id: string;
  file: File;
}

interface FileFeedback {
  tone: "success" | "warning" | "error" | "progress" | "info";
  title: string;
  detail: string;
  progress?: number;
}

export function SourceManager({ initialSources, readOnly, viewerMode = false }: { initialSources: SourceItem[]; readOnly: boolean; viewerMode?: boolean }) {
  const [sources, setSources] = useState(initialSources);
  const [staged, setStaged] = useState<StagedFile[]>([]);
  const [dragActive, setDragActive] = useState(false);
  const [fileFeedback, setFileFeedback] = useState<FileFeedback | null>(null);
  const [url, setUrl] = useState("");
  const [query, setQuery] = useState("");
  const [kind, setKind] = useState("all");
  const [domainId, setDomainId] = useState(ALL_SOURCE_DOMAINS);
  const [message, setMessage] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [submittingTask, setSubmittingTask] = useState<"file" | "url" | null>(null);
  const [statusRefreshing, setStatusRefreshing] = useState(false);
  const [statusRefreshError, setStatusRefreshError] = useState("");
  const [catalogSubmitting, setCatalogSubmitting] = useState(false);
  const [sourceAction, setSourceAction] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const domainOptions = useMemo(() => sourceDomainOptions(sources), [sources]);
  const unassignedSourceCount = useMemo(
    () => sources.filter((source) => source.domains.length === 0).length,
    [sources],
  );
  const filtered = useMemo(() => {
    return filterSources(sources, { query, kind, domainId });
  }, [sources, query, kind, domainId]);
  const activeProcessing = useMemo(() => {
    const activeSources = sources.filter(hasActiveSourceProcessing);
    const hasMeasuredProgress = activeSources.some((source) => (source.progressPercent ?? 0) > 0);
    const progress = hasMeasuredProgress
      ? Math.round(activeSources.reduce((total, source) => total + Math.max(0, Math.min(100, source.progressPercent ?? 0)), 0) / activeSources.length)
      : undefined;
    return { count: activeSources.length, progress };
  }, [sources]);
  const activeSourceCount = activeProcessing.count;

  useEffect(() => {
    if (readOnly) return;
    const supabase = getBrowserSupabase();
    if (!supabase) return;

    let disposed = false;
    let timer: number | undefined;
    const refreshStatuses = async () => {
      setStatusRefreshing(true);
      try {
        const { data, error } = await supabase
          .from("source_catalog_overview")
          .select([
            "source_id",
            "version_count",
            "latest_parse_status",
            "latest_job_id",
            "latest_job_status",
            "latest_job_progress_percent",
            "latest_processing_stage",
            "latest_job_error_message",
            "latest_job_updated_at",
            "linked_element_count",
            "candidate_count",
            "top_candidate_element_id",
            "top_candidate_score",
          ].join(","));
        if (disposed) return;

        if (error) {
          setStatusRefreshError(`자동 가공 상태를 갱신하지 못했습니다: ${error.message}`);
        } else {
          const rowsBySourceId = new Map<string, SourceStatusRow>();
          for (const row of (data ?? []) as SourceStatusRow[]) {
            if (typeof row.source_id === "string") rowsBySourceId.set(row.source_id, row);
          }
          setSources((current) => current.map((source) => {
            const row = rowsBySourceId.get(source.id);
            return row ? mergeSourceStatus(source, row) : source;
          }));
          setStatusRefreshError("");
        }
      } catch (error) {
        if (!disposed) {
          setStatusRefreshError(`자동 가공 상태를 갱신하지 못했습니다: ${error instanceof Error ? error.message : "네트워크 오류"}`);
        }
      } finally {
        if (!disposed) {
          setStatusRefreshing(false);
          timer = window.setTimeout(refreshStatuses, 3_000);
        }
      }
    };

    timer = window.setTimeout(refreshStatuses, 700);
    return () => {
      disposed = true;
      if (timer !== undefined) window.clearTimeout(timer);
    };
  }, [readOnly]);

  function stageFiles(files: FileList | File[]) {
    if (readOnly || submitting) return;
    const candidates = Array.from(files);
    const { accepted, rejected } = classifySourceFiles(candidates);
    const incoming = accepted.map((file) => ({ id: crypto.randomUUID(), file }));
    const totalStaged = staged.length + incoming.length;
    setStaged((current) => [...current, ...incoming]);
    if (incoming.length && rejected.length) {
      setFileFeedback({
        tone: "warning",
        title: `${incoming.length}개 추가 · 현재 대기열 ${totalStaged}개`,
        detail: `${sourceFileRejectionSummary(rejected)} · 아직 서버에는 저장되지 않았습니다.`,
      });
    } else if (incoming.length) {
      setFileFeedback({
        tone: "success",
        title: `${incoming.length}개 추가 · 현재 대기열 ${totalStaged}개`,
        detail: "아직 서버 저장 전입니다. 아래 파일명을 확인한 뒤 업로드 버튼을 눌러 주세요.",
      });
    } else {
      setFileFeedback({
        tone: "error",
        title: "대기열에 추가된 파일이 없습니다.",
        detail: rejected.length ? sourceFileRejectionSummary(rejected) : "파일을 다시 끌어다 놓거나 탐색기에서 선택해 주세요.",
      });
    }
  }

  function removeStagedFile(id: string) {
    const remaining = staged.filter((item) => item.id !== id);
    setStaged(remaining);
    setFileFeedback({
      tone: "info",
      title: remaining.length ? `현재 업로드 대기열 ${remaining.length}개` : "업로드 대기열을 비웠습니다.",
      detail: remaining.length ? "남은 파일은 아직 서버 저장 전입니다." : "서버에 저장된 파일은 없습니다.",
    });
  }

  function onDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setDragActive(false);
    stageFiles(event.dataTransfer.files);
  }

  function onFileInput(event: ChangeEvent<HTMLInputElement>) {
    if (event.target.files) stageFiles(event.target.files);
    event.target.value = "";
  }

  async function addUrl(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    let parsed: URL;
    try {
      parsed = parsePublicSourceUrl(url);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "URL을 확인해 주세요.");
      return;
    }
    const sourceId = `url-${Date.now()}-${crypto.randomUUID().slice(0, 8)}`;
    const draft: SourceItem = {
      id: sourceId,
      label: parsed.hostname,
      kind: "url",
      locator: parsed.toString(),
      status: "processing",
      linkedElements: 0,
      domains: [],
      createdAt: readOnly ? "데모 미저장" : "등록 대기",
    };
    if (readOnly) {
      setSources((current) => [draft, ...current]);
      setUrl("");
      setMessage("URL 가공 흐름을 미리보기로 추가했습니다. 새로고침하면 사라집니다.");
      return;
    }

    const supabase = getBrowserSupabase();
    if (!supabase) return setMessage("Supabase 연결을 확인해 주세요.");
    setSubmittingTask("url");
    setSubmitting(true);
    try {
      const { data: registration, error } = await supabase.rpc("register_url_source", {
        p_source_id: sourceId,
        p_label: parsed.hostname,
        p_url: parsed.toString(),
        p_source_type: "web",
      });
      if (error) {
        setMessage(`URL 수집 요청을 등록하지 못했습니다: ${error.message}`);
        return;
      }
      setSources((current) => [{
        ...draft,
        jobId: registrationJobId(registration),
        jobStatus: "pending_start",
        progressPercent: 0,
        processingStage: "pending_start",
        createdAt: "방금 등록",
      }, ...current]);
      setUrl("");
      setMessage("URL 자동 수집 대기열에 등록했습니다. 아래 목록에서 실제 진행 단계를 확인할 수 있습니다.");
    } catch (error) {
      setMessage(`URL 수집 요청을 등록하지 못했습니다: ${error instanceof Error ? error.message : "네트워크 오류"}`);
    } finally {
      setSubmitting(false);
      setSubmittingTask(null);
    }
  }

  async function queueCatalogSources() {
    if (readOnly || catalogSubmitting) return;
    setCatalogSubmitting(true);
    setMessage("");
    try {
      const response = await fetch("/api/workflow/generation", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: "queue_catalog", refresh: false }),
      });
      const result = await response.json().catch(() => ({})) as { error?: string; message?: string; queuedCount?: number };
      if (!response.ok) {
        setMessage(result.error ?? "기존 웹 출처를 수집 대기열에 넣지 못했습니다.");
        return;
      }
      setMessage(`${result.message ?? "기존 웹 출처 수집을 등록했습니다."} 완료된 원본은 코드의 로컬 변환 Worker가 자동으로 이어서 처리합니다.`);
    } catch {
      setMessage("기존 웹 출처 수집 요청의 네트워크 응답을 확인하지 못했습니다.");
    } finally {
      setCatalogSubmitting(false);
    }
  }

  async function submitStaged() {
    if (!staged.length) return;
    if (readOnly) {
      setFileFeedback({ tone: "info", title: "Viewer 화면에서는 파일을 전송하지 않습니다.", detail: "Owner 계정으로 로그인하면 업로드할 수 있습니다." });
      return;
    }
    const supabase = getBrowserSupabase();
    if (!supabase) {
      setFileFeedback({ tone: "error", title: "서버에 연결하지 못했습니다.", detail: "Supabase 연결 상태를 확인한 뒤 다시 시도해 주세요." });
      return;
    }
    const { data: auth } = await supabase.auth.getUser();
    if (!auth.user) {
      setFileFeedback({ tone: "error", title: "로그인 상태를 확인할 수 없습니다.", detail: "다시 로그인한 뒤 업로드해 주세요." });
      return;
    }

    const queued = [...staged];
    setSubmittingTask("file");
    setSubmitting(true);
    setMessage("");
    const uploaded: SourceItem[] = [];
    let reusedObjectCount = 0;
    for (const [itemIndex, item] of queued.entries()) {
      setFileFeedback({
        tone: "progress",
        title: `${itemIndex + 1}/${queued.length} · ${item.file.name}`,
        detail: "업로드를 준비하고 있습니다.",
        progress: 0,
      });
      const sourceId = `file-${item.id}`;
      const versionId = item.id;
      const safeName = item.file.name.replace(/[^a-zA-Z0-9._-]/g, "_") || "upload";
      let objectPath = `${auth.user.id}/sources/${sourceId}/${versionId}/${safeName}`;
      let reusedExistingObject = false;
      const mimeType = sourceMimeType(item.file);
      let registeredJobId: string | undefined;
      if (!mimeType) {
        setSubmitting(false);
        setSubmittingTask(null);
        setStaged(queued.slice(itemIndex));
        if (uploaded.length) setSources((current) => [...uploaded, ...current]);
        setFileFeedback({ tone: "error", title: `${item.file.name} 업로드 실패`, detail: `지원하지 않는 형식입니다. 앞의 ${uploaded.length}개는 서버 저장을 완료했습니다.` });
        return;
      }
      try {
        const digest = await sha256FileInChunks(item.file, (bytesHashed, bytesTotal) => {
          const progress = percent(bytesHashed, bytesTotal);
          setFileFeedback({
            tone: "progress",
            title: `${itemIndex + 1}/${queued.length} · ${item.file.name}`,
            detail: `1/3 · 무결성 확인 ${Math.round(progress)}% · ${formatBytes(bytesHashed)} / ${formatBytes(bytesTotal)}`,
            progress,
          });
        });

        setFileFeedback({
          tone: "progress",
          title: `${itemIndex + 1}/${queued.length} · ${item.file.name}`,
          detail: "2/3 · 같은 SHA-256 원본이 이미 보관되어 있는지 확인 중입니다.",
        });
        const { data: reusable, error: reuseError } = await supabase.rpc("find_reusable_source_file", {
          p_sha256: digest,
          p_byte_size: item.file.size,
        });
        if (reuseError) throw new Error(`원본 중복 확인 실패: ${reuseError.message}`);
        const reusablePath = reusableObjectPath(reusable);
        if (reusablePath) {
          objectPath = reusablePath;
          reusedExistingObject = true;
          reusedObjectCount += 1;
          setFileFeedback({
            tone: "progress",
            title: `${itemIndex + 1}/${queued.length} · 동일 원본 재사용`,
            detail: "SHA-256이 같은 private 원본을 찾았습니다. 파일을 다시 전송하지 않고 새 source version만 연결합니다.",
            progress: 100,
          });
        } else {
          let bytesUploaded = 0;
          await uploadSourceFileResumable({
            file: item.file,
            bucketName: "source-private",
            objectPath,
            contentType: mimeType,
            projectUrl: supabaseUrl,
            getAccessToken: async () => {
              const { data } = await supabase.auth.getSession();
              return data.session?.access_token ?? null;
            },
            onResume: () => {
              setFileFeedback({
                tone: "progress",
                title: `${itemIndex + 1}/${queued.length} · ${item.file.name}`,
                detail: "중단된 업로드를 찾았습니다. 저장된 지점부터 이어서 준비 중입니다.",
                progress: percent(bytesUploaded, item.file.size),
              });
            },
            onRetry: (attempt) => {
              setFileFeedback({
                tone: "progress",
                title: `${itemIndex + 1}/${queued.length} · 연결 재시도 중`,
                detail: `네트워크 연결을 자동으로 다시 시도하고 있습니다 (${attempt}/5). 완료된 청크부터 이어집니다.`,
                progress: percent(bytesUploaded, item.file.size),
              });
            },
            onProgress: (uploadedBytes, bytesTotal) => {
              bytesUploaded = uploadedBytes;
              const progress = percent(uploadedBytes, bytesTotal);
              setFileFeedback({
                tone: "progress",
                title: `${itemIndex + 1}/${queued.length} · ${item.file.name}`,
                detail: `3/3 · 서버 전송 ${Math.round(progress)}% · ${formatBytes(uploadedBytes)} / ${formatBytes(bytesTotal)}`,
                progress,
              });
            },
          });
        }

        const { data: registration, error: metadataError } = await supabase.rpc("register_file_source", {
          p_source_id: sourceId,
          p_source_version_id: versionId,
          p_label: item.file.name,
          p_object_path: objectPath,
          p_original_filename: item.file.name,
          p_mime_type: mimeType,
          p_byte_size: item.file.size,
          p_sha256: digest,
        });
        if (metadataError) {
          if (!reusedExistingObject) await supabase.storage.from("source-private").remove([objectPath]);
          throw new Error(metadataError.message);
        }
        registeredJobId = registrationJobId(registration);
      } catch (error) {
        setSubmitting(false);
        setSubmittingTask(null);
        setStaged(queued.slice(itemIndex));
        if (uploaded.length) setSources((current) => [...uploaded, ...current]);
        setFileFeedback({
          tone: "error",
          title: `${item.file.name} 업로드 실패`,
          detail: `${sourceUploadErrorMessage(error)}${uploaded.length ? ` · 앞의 ${uploaded.length}개는 서버 저장 완료` : ""}`,
        });
        return;
      }
      uploaded.push({
        id: sourceId,
        label: item.file.name,
        kind: item.file.name.toLowerCase().endsWith(".pdf") ? "pdf" : /\.(xlsx|xls|csv|db|sqlite|sqlite3)$/i.test(item.file.name) ? "spreadsheet" : "document",
        locator: objectPath,
        status: "processing",
        linkedElements: 0,
        domains: [],
        size: formatBytes(item.file.size),
        createdAt: "방금 등록",
        jobId: registeredJobId,
        jobStatus: "pending_start",
        progressPercent: 0,
        processingStage: "pending_start",
      });
    }
    setSources((current) => [...uploaded, ...current]);
    setStaged([]);
    setSubmitting(false);
    setSubmittingTask(null);
    setFileFeedback({
      tone: "success",
      title: `${uploaded.length}개 파일의 서버 저장을 완료했습니다.`,
      detail: `자동 가공 대기열에도 등록했습니다.${reusedObjectCount ? ` 동일 SHA-256 원본 ${reusedObjectCount}개는 재전송하지 않았습니다.` : ""} 아래 목록에서 실제 처리 단계를 확인할 수 있습니다.`,
    });
  }

  async function controlSource(source: SourceItem, action: "start" | "pause" | "resume" | "delete") {
    if (readOnly || sourceAction || !source.jobId && action !== "delete") return;
    const supabase = getBrowserSupabase();
    if (!supabase) return setMessage("Supabase 연결을 확인해 주세요.");
    const label = action === "delete" ? "삭제" : action === "pause" ? "일시정지" : action === "resume" ? "재개" : "시작";
    if (!window.confirm(`${source.label} 가공을 ${label}하시겠습니까?`)) return;
    setSourceAction(`${source.id}:${action}`);
    try {
      if (action === "delete") {
        if (source.linkedElements > 0) throw new Error("앱 콘텐츠와 연결된 원본은 삭제할 수 없습니다.");
        const { error } = await supabase.rpc("archive_unconnected_source", { p_source_id: source.id });
        if (error) throw error;
        if (!source.locator.startsWith("http")) {
          await supabase.storage.from("source-private").remove([source.locator]);
        }
        setSources((current) => current.filter((item) => item.id !== source.id));
        setMessage("연결되지 않은 원본을 보관 처리했습니다. 기록은 복구를 위해 보존됩니다.");
      } else {
        const { data, error } = await supabase.rpc("control_source_ingestion_job", { p_job_id: source.jobId, p_action: action });
        if (error) throw error;
        const result = Array.isArray(data) ? data[0] : data;
        const jobStatus = result && typeof result === "object" && "jobStatus" in result ? String((result as { jobStatus: unknown }).jobStatus) : undefined;
        setSources((current) => current.map((item) => item.id === source.id ? { ...item, jobStatus: jobStatus as SourceItem["jobStatus"], status: jobStatus === "running" ? "processing" : item.status, processingStage: action === "pause" ? "paused" : action === "start" || action === "resume" ? "queued" : item.processingStage } : item));
        setMessage(`${source.label}: 가공 ${label} 요청을 반영했습니다.`);
      }
    } catch (error) {
      setMessage(`${source.label}: ${error instanceof Error ? error.message : "작업에 실패했습니다."}`);
    } finally {
      setSourceAction(null);
    }
  }

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="SOURCE LIBRARY"
        title="원본 자료"
        description={viewerMode
          ? "Owner 화면과 같은 등록·목록 배치에서 원본 자료 DB의 구성 필드만 설명합니다. 실제 파일과 URL은 표시하지 않습니다."
          : readOnly
          ? "등록된 파일·웹 근거 자료와 연결 상태를 조회합니다."
          : "SQLite DB, JSON, CSV, 문서 또는 URL을 등록하면 실제 내용을 추출하고 로컬 변환 모델에 연결합니다."}
        actions={<span className="count-pill">{viewerMode ? "원본 구성 안내" : `현재 원본 ${sources.length}건`}</span>}
      />

      {!readOnly || viewerMode ? <section className="source-ingest-grid">
        <article className="panel upload-panel">
          <div className="panel-heading compact-heading">
            <div><p className="eyebrow">FILES</p><h2>파일 가져오기</h2></div>
            <span className="file-support">{SOURCE_FILE_SUPPORT_LABEL}</span>
          </div>
          <input ref={inputRef} className="visually-hidden" type="file" accept={SOURCE_FILE_ACCEPT} multiple onChange={onFileInput} disabled={readOnly || submitting} />
          <div
            className={`drop-zone ${dragActive ? "drop-zone-active" : ""} ${staged.length ? "drop-zone-has-files" : ""} ${submitting ? "drop-zone-disabled" : ""}`}
            data-testid="source-drop-zone"
            aria-label="원본 파일 드롭 영역"
            onDragEnter={(event) => { event.preventDefault(); if (!readOnly && !submitting) setDragActive(true); }}
            onDragOver={(event) => event.preventDefault()}
            onDragLeave={(event) => { if (event.currentTarget === event.target) setDragActive(false); }}
            onDrop={onDrop}
          >
            <span className="drop-icon">{staged.length && !dragActive ? <CheckCircle2 size={25} /> : <UploadCloud size={25} />}</span>
            <strong>{dragActive ? "지금 여기에 놓으세요" : staged.length ? `${staged.length}개 파일이 업로드 대기 중입니다` : "여기에 원본 파일을 놓으세요"}</strong>
            <p>{dragActive ? "놓는 즉시 아래 대기열에서 파일명을 확인할 수 있습니다." : staged.length ? "아직 서버 저장 전입니다. 아래 목록과 업로드 버튼을 확인하세요." : "파일 크기는 Supabase 설정을 따르며 대용량 파일은 중단 지점부터 이어 올립니다."}</p>
            <button className="button button-secondary" type="button" onClick={() => inputRef.current?.click()} disabled={readOnly || submitting}>
              {staged.length ? "파일 더 추가" : "파일 탐색기 열기"}
            </button>
          </div>

          {fileFeedback ? (
            <div className={`file-feedback file-feedback-${fileFeedback.tone}`} role={fileFeedback.tone === "error" ? "alert" : "status"} aria-live="polite">
              {fileFeedback.tone === "progress" ? <LoaderCircle size={18} /> : fileFeedback.tone === "error" || fileFeedback.tone === "warning" ? <AlertTriangle size={18} /> : <CheckCircle2 size={18} />}
              <div className="file-feedback-body">
                <strong>{fileFeedback.title}</strong><p>{fileFeedback.detail}</p>
                {fileFeedback.tone === "progress" ? (
                  <div
                    className={`source-upload-progress ${fileFeedback.progress === undefined || fileFeedback.progress <= 0 ? "is-indeterminate" : ""}`}
                    role="progressbar"
                    aria-label="파일 업로드 진행률"
                    aria-valuemin={0}
                    aria-valuemax={100}
                    aria-valuenow={fileFeedback.progress === undefined || fileFeedback.progress <= 0 ? undefined : Math.round(fileFeedback.progress)}
                    aria-valuetext={fileFeedback.progress === undefined || fileFeedback.progress <= 0 ? "다음 단계를 준비하는 중" : undefined}
                  >
                    <span style={fileFeedback.progress === undefined || fileFeedback.progress <= 0 ? undefined : { width: `${fileFeedback.progress}%` }} />
                  </div>
                ) : null}
              </div>
            </div>
          ) : null}

          {staged.length ? (
            <div className="staged-files">
              <div className="staged-heading"><strong>서버 저장 전 · {staged.length}개</strong><button type="button" onClick={() => { setStaged([]); setFileFeedback({ tone: "info", title: "업로드 대기열을 비웠습니다.", detail: "서버에 저장된 파일은 없습니다." }); }} disabled={submitting}>전체 지우기</button></div>
              {staged.map((item) => (
                <div className="staged-file" key={item.id}>
                  <File size={17} />
                  <div><strong>{item.file.name}</strong><small>{formatBytes(item.file.size)} · 업로드 대기</small></div>
                  <button type="button" onClick={() => removeStagedFile(item.id)} aria-label={`${item.file.name} 제거`} disabled={submitting}><X size={15} /></button>
                </div>
              ))}
              <button className="button button-primary staged-submit" type="button" onClick={submitStaged} disabled={submitting}>
                {submittingTask === "file" ? <><LoaderCircle className="spin" size={16} />{fileFeedback?.progress !== undefined ? `${Math.round(fileFeedback.progress)}% 저장 중…` : "서버에 저장 중…"}</> : `${staged.length}개 파일 서버에 저장`}
              </button>
            </div>
          ) : null}
        </article>

        <article className="panel url-panel">
          <div className="panel-heading compact-heading">
            <div><p className="eyebrow">WEB SOURCE</p><h2>URL로 가져오기</h2></div>
            <Globe2 size={20} className="subtle-icon" />
          </div>
          <p className="panel-intro">공개 웹페이지나 PDF 주소를 입력하면 본문과 출처 위치를 보존해 가공 대기열에 넣습니다.</p>
          <form className="url-form" onSubmit={addUrl}>
            <label htmlFor="source-url">원본 URL</label>
            <div className="url-input-row">
              <div className="input-with-icon"><Link2 size={17} /><input id="source-url" type="url" value={url} onChange={(event) => setUrl(event.target.value)} placeholder={viewerMode ? "공개 URL 또는 PDF 주소가 들어가는 자리" : "https://…"} required disabled={readOnly} /></div>
              <button className="button button-primary" type="submit" disabled={submitting || readOnly}>{submittingTask === "url" ? <><LoaderCircle className="spin" size={16} /> 등록 중…</> : <><Plus size={16} /> 등록</>}</button>
            </div>
            {submittingTask === "url" ? (
              <div className="url-registration-progress" role="status" aria-live="polite">
                <span>URL 수집 요청을 안전하게 등록하는 중입니다.</span>
                <div className="url-registration-progress-bar is-indeterminate" role="progressbar" aria-label="URL 수집 요청 등록 진행률" aria-valuetext="등록 처리 중">
                  <span />
                </div>
              </div>
            ) : null}
          </form>
          <div className="ingest-notes">
            <div><span>1</span><p><strong>원본 보관</strong>본문과 접근 시점을 snapshot으로 남깁니다.</p></div>
            <div><span>2</span><p><strong>안전한 수집</strong>내부 주소와 위험한 redirect는 차단합니다.</p></div>
            <div><span>3</span><p><strong>로컬 변환</strong>명시된 요소 ID와 앱 필드를 코드 규칙으로 연결합니다.</p></div>
          </div>
          {!viewerMode ? (
            <div className="catalog-source-action">
              <div><strong>기존 앱 DB의 웹 출처도 자동 수집</strong><p>Worker가 순서대로 자동 수집합니다. 기다리지 않고 최대 50건을 지금 등록할 때만 버튼을 사용하세요.</p></div>
              <button className="button button-secondary" type="button" onClick={queueCatalogSources} disabled={readOnly || catalogSubmitting || submitting}>
                {catalogSubmitting ? <LoaderCircle className="spin" size={16} /> : <RefreshCw size={16} />}
                {catalogSubmitting ? "수집 요청 등록 중…" : "지금 최대 50건 수집 시작"}
              </button>
              {catalogSubmitting ? (
                <div className="generation-action-progress catalog-action-progress" role="status">
                  <span>기존 출처를 중복 확인하고 대기열에 넣는 중</span>
                  <div className="is-indeterminate" role="progressbar" aria-label="기존 웹 출처 수집 등록 진행" aria-valuetext="처리 중"><i /></div>
                </div>
              ) : null}
            </div>
          ) : null}
        </article>
      </section> : null}

      <section className="panel source-library-panel">
        <div className="library-toolbar">
          <div>
            <p className="eyebrow">REGISTERED SOURCES</p>
            <h2>등록된 원본</h2>
          </div>
          <div className="library-filters">
            <label className="search-box compact-search"><Search size={16} /><span className="visually-hidden">원본 검색</span><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="출처명 또는 URL 검색" /></label>
            <label className="select-wrap"><span className="visually-hidden">파일 종류</span><select value={kind} onChange={(event) => setKind(event.target.value)}><option value="all">모든 유형</option><option value="pdf">PDF</option><option value="spreadsheet">스프레드시트</option><option value="document">문서</option><option value="url">URL</option></select><ChevronDown size={14} /></label>
          </div>
        </div>
        {activeSourceCount ? (
          <div className="source-processing-summary" role="status" aria-live="polite">
            <LoaderCircle className="spin" size={19} aria-hidden="true" />
            <div>
              <strong>자동 가공 중 · {activeSourceCount}건</strong>
              <p>{statusRefreshing ? "최신 처리 단계를 확인하는 중입니다…" : "Worker가 원본을 검증하고 본문·표·수식·OCR 결과를 저장하고 있습니다."}</p>
              <div
                className={`source-processing-summary-bar ${activeProcessing.progress === undefined ? "is-indeterminate" : ""}`}
                role="progressbar"
                aria-label="전체 자동 가공 진행률"
                aria-valuemin={0}
                aria-valuemax={100}
                aria-valuenow={activeProcessing.progress}
                aria-valuetext={activeProcessing.progress === undefined ? "대기열 처리 시작 중" : undefined}
              >
                <span style={activeProcessing.progress === undefined ? undefined : { width: `${activeProcessing.progress}%` }} />
              </div>
            </div>
          </div>
        ) : null}
        <div className="source-domain-filter" role="group" aria-label="원본 자료 단원 필터">
          <span className="source-domain-filter-label">단원</span>
          <button
            className={`source-domain-toggle ${domainId === ALL_SOURCE_DOMAINS ? "active" : ""}`}
            type="button"
            aria-pressed={domainId === ALL_SOURCE_DOMAINS}
            onClick={() => setDomainId(ALL_SOURCE_DOMAINS)}
          >
            <span>전체보기</span><small>{sources.length}</small>
          </button>
          {domainOptions.map((domain) => (
            <button
              className={`source-domain-toggle ${domainId === domain.id ? "active" : ""}`}
              type="button"
              aria-pressed={domainId === domain.id}
              onClick={() => setDomainId(domain.id)}
              key={domain.id}
            >
              <span>{domain.name}</span><small>{domain.sourceCount}</small>
            </button>
          ))}
          {unassignedSourceCount ? (
            <button
              className={`source-domain-toggle source-domain-unassigned ${domainId === UNASSIGNED_SOURCE_DOMAIN ? "active" : ""}`}
              type="button"
              aria-pressed={domainId === UNASSIGNED_SOURCE_DOMAIN}
              onClick={() => setDomainId(UNASSIGNED_SOURCE_DOMAIN)}
            >
              <span>단원 미연결</span><small>{unassignedSourceCount}</small>
            </button>
          ) : null}
        </div>
        {message ? <div className="table-notice" role="status">{message}</div> : null}
        {statusRefreshError ? <div className="table-notice table-notice-error" role="alert">{statusRefreshError}</div> : null}
        <div className="source-list">
          {filtered.slice(0, 80).map((source) => {
            const presentation = sourceStatusPresentation(source);
            const progressIndeterminate = presentation.progress === undefined || presentation.progress <= 0;
            return (
              <article className="source-row" key={source.id}>
                <span className={`source-kind-icon kind-${source.kind}`}>{source.kind === "url" ? <Globe2 size={19} /> : source.kind === "spreadsheet" ? <FileSpreadsheet size={19} /> : <FileText size={19} />}</span>
                <div className="source-main"><strong>{source.label}</strong><span>{source.locator}</span></div>
                <span className={`source-state source-${source.status}`} title={presentation.detail}>
                  {presentation.loading ? <LoaderCircle className="source-state-spinner" size={14} aria-hidden="true" /> : <i />}
                  <span className="source-state-copy">
                    <strong>{presentation.label}</strong>
                    <small>{presentation.detail}</small>
                    {presentation.loading ? (
                      <span
                        className={`source-processing-progress ${progressIndeterminate ? "is-indeterminate" : ""}`}
                        role="progressbar"
                        aria-label={`${source.label} 자동 가공 진행률`}
                        aria-valuemin={0}
                        aria-valuemax={100}
                        aria-valuenow={progressIndeterminate ? undefined : Math.round(presentation.progress ?? 0)}
                        aria-valuetext={progressIndeterminate ? "작업 시작 또는 대기 중" : undefined}
                      >
                        <span style={progressIndeterminate ? undefined : { width: `${presentation.progress}%` }} />
                      </span>
                    ) : null}
                  </span>
                </span>
                <span className="source-links"><strong>{viewerMode ? "연결" : source.linkedElements}</strong><small>{viewerMode ? "기준 설명" : "연결 요소"}</small></span>
                <span className="source-actions">
                  {!readOnly && source.jobId && source.jobStatus === "pending_start" ? <button className="icon-button" type="button" onClick={() => controlSource(source, "start")} disabled={Boolean(sourceAction)} aria-label={`${source.label} 가공 시작`}>{sourceAction === `${source.id}:start` ? <LoaderCircle className="spin" size={17} /> : <Play size={17} />}</button> : null}
                  {!readOnly && source.jobId && (source.jobStatus === "queued" || source.jobStatus === "running") ? <button className="icon-button" type="button" onClick={() => controlSource(source, "pause")} disabled={Boolean(sourceAction)} aria-label={`${source.label} 가공 일시정지`}>{sourceAction === `${source.id}:pause` ? <LoaderCircle className="spin" size={17} /> : <Pause size={17} />}</button> : null}
                  {!readOnly && source.jobId && source.jobStatus === "paused" ? <button className="icon-button" type="button" onClick={() => controlSource(source, "resume")} disabled={Boolean(sourceAction)} aria-label={`${source.label} 가공 재개`}>{sourceAction === `${source.id}:resume` ? <LoaderCircle className="spin" size={17} /> : <Play size={17} />}</button> : null}
                  {!readOnly && source.linkedElements === 0 && source.jobStatus !== "queued" && source.jobStatus !== "running" && source.jobStatus !== "paused" ? <button className="icon-button source-delete-button" type="button" onClick={() => controlSource(source, "delete")} disabled={Boolean(sourceAction)} aria-label={`${source.label} 원본 삭제`}>{sourceAction === `${source.id}:delete` ? <LoaderCircle className="spin" size={17} /> : <Trash2 size={17} />}</button> : null}
                  {source.locator.startsWith("http") ? <a className="icon-button" href={source.locator} target="_blank" rel="noreferrer" aria-label={`${source.label} 열기`}><ArrowUpRight size={17} /></a> : <span className="icon-button-placeholder" />}
                </span>
              </article>
            );
          })}
          {!filtered.length ? <div className="source-empty">선택한 조건에 해당하는 원본 자료가 없습니다.</div> : null}
        </div>
        {filtered.length > 80 ? <p className="list-limit-note">검색 성능을 위해 첫 80건을 표시 중입니다. 검색어로 범위를 좁혀 주세요.</p> : null}
      </section>
    </div>
  );
}

function formatBytes(bytes: number) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
  return `${(bytes / 1024 / 1024 / 1024).toFixed(2)} GB`;
}

function percent(current: number, total: number): number {
  if (!total) return 0;
  return Math.min(100, Math.max(0, (current / total) * 100));
}

function registrationJobId(value: unknown): string | undefined {
  const candidate = Array.isArray(value) ? value[0] : value;
  if (!candidate || typeof candidate !== "object" || !("jobId" in candidate)) return undefined;
  const jobId = (candidate as { jobId?: unknown }).jobId;
  return typeof jobId === "string" && jobId ? jobId : undefined;
}

function reusableObjectPath(value: unknown): string | undefined {
  const candidate = Array.isArray(value) ? value[0] : value;
  if (!candidate || typeof candidate !== "object" || !("objectPath" in candidate)) return undefined;
  const objectPath = (candidate as { objectPath?: unknown }).objectPath;
  return typeof objectPath === "string" && objectPath ? objectPath : undefined;
}
