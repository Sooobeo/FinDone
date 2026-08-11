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
  Plus,
  Search,
  UploadCloud,
  X,
} from "lucide-react";
import { ChangeEvent, DragEvent, FormEvent, useMemo, useRef, useState } from "react";
import { PageHeader } from "@/components/page-header";
import {
  ALL_SOURCE_DOMAINS,
  filterSources,
  sourceDomainOptions,
  UNASSIGNED_SOURCE_DOMAIN,
} from "@/lib/source-filter";
import { SOURCE_STATUS_LABELS } from "@/lib/status";
import {
  classifySourceFiles,
  SOURCE_FILE_ACCEPT,
  SOURCE_FILE_SUPPORT_LABEL,
  sourceFileRejectionSummary,
  sourceMimeType,
} from "@/lib/source-files";
import { parsePublicSourceUrl } from "@/lib/source-url";
import { getBrowserSupabase } from "@/lib/supabase/browser";
import type { SourceItem } from "@/lib/types";

interface StagedFile {
  id: string;
  file: File;
}

interface FileFeedback {
  tone: "success" | "warning" | "error" | "progress" | "info";
  title: string;
  detail: string;
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
  const inputRef = useRef<HTMLInputElement>(null);

  const domainOptions = useMemo(() => sourceDomainOptions(sources), [sources]);
  const unassignedSourceCount = useMemo(
    () => sources.filter((source) => source.domains.length === 0).length,
    [sources],
  );
  const filtered = useMemo(() => {
    return filterSources(sources, { query, kind, domainId });
  }, [sources, query, kind, domainId]);

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
    setSubmitting(true);
    const { error } = await supabase.rpc("register_url_source", {
      p_source_id: sourceId,
      p_label: parsed.hostname,
      p_url: parsed.toString(),
      p_source_type: "web",
    });
    setSubmitting(false);
    if (error) return setMessage(`URL 수집 요청을 등록하지 못했습니다: ${error.message}`);
    setSources((current) => [draft, ...current]);
    setUrl("");
    setMessage("URL 수집 요청을 등록했습니다.");
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
    setSubmitting(true);
    setMessage("");
    const uploaded: SourceItem[] = [];
    for (const [itemIndex, item] of queued.entries()) {
      setFileFeedback({
        tone: "progress",
        title: `${itemIndex + 1}/${queued.length} · ${item.file.name} 업로드 중`,
        detail: "창을 닫지 말고 잠시 기다려 주세요.",
      });
      const sourceId = `file-${Date.now()}-${crypto.randomUUID().slice(0, 8)}`;
      const versionId = crypto.randomUUID();
      const safeName = item.file.name.replace(/[^a-zA-Z0-9._-]/g, "_") || "upload";
      const objectPath = `${auth.user.id}/sources/${sourceId}/${versionId}/${safeName}`;
      const mimeType = sourceMimeType(item.file);
      if (!mimeType) {
        setSubmitting(false);
        setStaged(queued.slice(itemIndex));
        if (uploaded.length) setSources((current) => [...uploaded, ...current]);
        setFileFeedback({ tone: "error", title: `${item.file.name} 업로드 실패`, detail: `지원하지 않는 형식입니다. 앞의 ${uploaded.length}개는 서버 저장을 완료했습니다.` });
        return;
      }
      try {
        const digest = await sha256(item.file);
        const { error: uploadError } = await supabase.storage
          .from("source-private")
          .upload(objectPath, item.file, { contentType: mimeType, upsert: false });
        if (uploadError) throw new Error(uploadError.message);

        const { error: metadataError } = await supabase.rpc("register_file_source", {
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
          await supabase.storage.from("source-private").remove([objectPath]);
          throw new Error(metadataError.message);
        }
      } catch (error) {
        setSubmitting(false);
        setStaged(queued.slice(itemIndex));
        if (uploaded.length) setSources((current) => [...uploaded, ...current]);
        setFileFeedback({
          tone: "error",
          title: `${item.file.name} 업로드 실패`,
          detail: `${error instanceof Error ? error.message : "알 수 없는 오류"}${uploaded.length ? ` · 앞의 ${uploaded.length}개는 서버 저장 완료` : ""}`,
        });
        return;
      }
      uploaded.push({
        id: sourceId,
        label: item.file.name,
        kind: item.file.name.toLowerCase().endsWith(".pdf") ? "pdf" : /\.(xlsx|xls|csv)$/i.test(item.file.name) ? "spreadsheet" : "document",
        locator: objectPath,
        status: "processing",
        linkedElements: 0,
        domains: [],
        size: formatBytes(item.file.size),
        createdAt: "방금 등록",
      });
    }
    setSources((current) => [...uploaded, ...current]);
    setStaged([]);
    setSubmitting(false);
    setFileFeedback({
      tone: "success",
      title: `${uploaded.length}개 파일의 서버 저장을 완료했습니다.`,
      detail: "아래 등록된 원본 목록 맨 위에서 처리 상태를 확인할 수 있습니다.",
    });
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
          : "파일 탐색기, 드래그앤드롭 또는 URL로 근거 자료를 등록하고 개념 요소와 연결합니다."}
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
            <p>{dragActive ? "놓는 즉시 아래 대기열에서 파일명을 확인할 수 있습니다." : staged.length ? "아직 서버 저장 전입니다. 아래 목록과 업로드 버튼을 확인하세요." : "또는 컴퓨터에서 직접 선택할 수 있습니다."}</p>
            <button className="button button-secondary" type="button" onClick={() => inputRef.current?.click()} disabled={readOnly || submitting}>
              {staged.length ? "파일 더 추가" : "파일 탐색기 열기"}
            </button>
          </div>

          {fileFeedback ? (
            <div className={`file-feedback file-feedback-${fileFeedback.tone}`} role={fileFeedback.tone === "error" ? "alert" : "status"} aria-live="polite">
              {fileFeedback.tone === "progress" ? <LoaderCircle size={18} /> : fileFeedback.tone === "error" || fileFeedback.tone === "warning" ? <AlertTriangle size={18} /> : <CheckCircle2 size={18} />}
              <div><strong>{fileFeedback.title}</strong><p>{fileFeedback.detail}</p></div>
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
              <button className="button button-primary staged-submit" type="button" onClick={submitStaged} disabled={submitting}>{submitting ? "서버에 저장 중…" : `${staged.length}개 파일 서버에 저장`}</button>
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
              <button className="button button-primary" type="submit" disabled={submitting || readOnly}><Plus size={16} /> 등록</button>
            </div>
          </form>
          <div className="ingest-notes">
            <div><span>1</span><p><strong>원본 보관</strong>본문과 접근 시점을 snapshot으로 남깁니다.</p></div>
            <div><span>2</span><p><strong>안전한 수집</strong>내부 주소와 위험한 redirect는 차단합니다.</p></div>
            <div><span>3</span><p><strong>근거 연결</strong>추출한 구절을 요소별 출처로 연결합니다.</p></div>
          </div>
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
        <div className="source-list">
          {filtered.slice(0, 80).map((source) => (
            <article className="source-row" key={source.id}>
              <span className={`source-kind-icon kind-${source.kind}`}>{source.kind === "url" ? <Globe2 size={19} /> : source.kind === "spreadsheet" ? <FileSpreadsheet size={19} /> : <FileText size={19} />}</span>
              <div className="source-main"><strong>{source.label}</strong><span>{source.locator}</span></div>
              <span className={`source-state source-${source.status}`}><i />{SOURCE_STATUS_LABELS[source.status]}</span>
              <span className="source-links"><strong>{viewerMode ? "연결" : source.linkedElements}</strong><small>{viewerMode ? "기준 설명" : "연결 요소"}</small></span>
              {source.locator.startsWith("http") ? <a className="icon-button" href={source.locator} target="_blank" rel="noreferrer" aria-label={`${source.label} 열기`}><ArrowUpRight size={17} /></a> : <span className="icon-button-placeholder" />}
            </article>
          ))}
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
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

async function sha256(file: File): Promise<string> {
  const buffer = await file.arrayBuffer();
  const digest = await crypto.subtle.digest("SHA-256", buffer);
  return Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, "0")).join("");
}
