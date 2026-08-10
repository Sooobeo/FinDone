"use client";

import {
  ArrowUpRight,
  ChevronDown,
  File,
  FileSpreadsheet,
  FileText,
  Globe2,
  Link2,
  Plus,
  Search,
  UploadCloud,
  X,
} from "lucide-react";
import { ChangeEvent, DragEvent, FormEvent, useMemo, useRef, useState } from "react";
import { PageHeader } from "@/components/page-header";
import { SOURCE_STATUS_LABELS } from "@/lib/status";
import { parsePublicSourceUrl } from "@/lib/source-url";
import { getBrowserSupabase } from "@/lib/supabase/browser";
import type { SourceItem } from "@/lib/types";

interface StagedFile {
  id: string;
  file: File;
}

const MAX_SOURCE_BYTES = 100 * 1024 * 1024;
const SOURCE_MIME_BY_EXTENSION: Record<string, string> = {
  pdf: "application/pdf",
  docx: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  xlsx: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  csv: "text/csv",
  md: "text/markdown",
  txt: "text/plain",
};

function sourceMimeType(file: File): string | null {
  const extension = file.name.toLocaleLowerCase("en-US").split(".").pop() ?? "";
  return SOURCE_MIME_BY_EXTENSION[extension] ?? null;
}

export function SourceManager({ initialSources, readOnly }: { initialSources: SourceItem[]; readOnly: boolean }) {
  const [sources, setSources] = useState(initialSources);
  const [staged, setStaged] = useState<StagedFile[]>([]);
  const [dragActive, setDragActive] = useState(false);
  const [url, setUrl] = useState("");
  const [query, setQuery] = useState("");
  const [kind, setKind] = useState("all");
  const [message, setMessage] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const filtered = useMemo(() => {
    const normalized = query.trim().toLocaleLowerCase("ko-KR");
    return sources.filter((source) => {
      if (kind !== "all" && source.kind !== kind) return false;
      return !normalized || `${source.id} ${source.label} ${source.locator}`.toLocaleLowerCase("ko-KR").includes(normalized);
    });
  }, [sources, query, kind]);

  function stageFiles(files: FileList | File[]) {
    const candidates = Array.from(files);
    const accepted = candidates.filter((file) => sourceMimeType(file) && file.size > 0 && file.size <= MAX_SOURCE_BYTES);
    const rejectedCount = candidates.length - accepted.length;
    const incoming = accepted.map((file) => ({ id: crypto.randomUUID(), file }));
    setStaged((current) => [...current, ...incoming]);
    setMessage(
      rejectedCount
        ? `${incoming.length}개를 추가하고 ${rejectedCount}개를 제외했습니다. 지원 형식과 100MB 한도를 확인하세요.`
        : `${incoming.length}개 파일을 업로드 대기열에 추가했습니다.`,
    );
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
      setMessage("데모에서는 파일을 서버로 전송하지 않습니다. Supabase 연결 후 업로드할 수 있습니다.");
      return;
    }
    const supabase = getBrowserSupabase();
    if (!supabase) return setMessage("Supabase 연결을 확인해 주세요.");
    const { data: auth } = await supabase.auth.getUser();
    if (!auth.user) return setMessage("다시 로그인한 뒤 업로드해 주세요.");

    setSubmitting(true);
    const uploaded: SourceItem[] = [];
    for (const [itemIndex, item] of staged.entries()) {
      setMessage(`${item.file.name} 업로드 중…`);
      const sourceId = `file-${Date.now()}-${crypto.randomUUID().slice(0, 8)}`;
      const versionId = crypto.randomUUID();
      const safeName = item.file.name.replace(/[^a-zA-Z0-9._-]/g, "_") || "upload";
      const objectPath = `${auth.user.id}/sources/${sourceId}/${versionId}/${safeName}`;
      const mimeType = sourceMimeType(item.file);
      if (!mimeType) {
        setSubmitting(false);
        setStaged(staged.slice(itemIndex));
        return setMessage(`${item.file.name}은 지원하지 않는 파일 형식입니다.`);
      }
      const digest = await sha256(item.file);
      const { error: uploadError } = await supabase.storage
        .from("source-private")
        .upload(objectPath, item.file, { contentType: mimeType, upsert: false });
      if (uploadError) {
        setSubmitting(false);
        setStaged(staged.slice(itemIndex));
        return setMessage(`${item.file.name} 업로드 실패: ${uploadError.message}`);
      }

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
        setSubmitting(false);
        setStaged(staged.slice(itemIndex));
        return setMessage(`${item.file.name} 메타데이터 저장 실패: ${metadataError.message}`);
      }
      uploaded.push({
        id: sourceId,
        label: item.file.name,
        kind: item.file.name.toLowerCase().endsWith(".pdf") ? "pdf" : /\.(xlsx|xls|csv)$/i.test(item.file.name) ? "spreadsheet" : "document",
        locator: objectPath,
        status: "processing",
        linkedElements: 0,
        size: formatBytes(item.file.size),
        createdAt: "방금 등록",
      });
    }
    setSources((current) => [...uploaded, ...current]);
    setStaged([]);
    setSubmitting(false);
    setMessage(`${uploaded.length}개 파일을 안전하게 업로드했습니다.`);
  }

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="SOURCE LIBRARY"
        title="원본 자료"
        description="파일 탐색기, 드래그앤드롭 또는 URL로 근거 자료를 등록하고 개념 요소와 연결합니다."
        actions={<span className="count-pill">현재 원본 {sources.length}건</span>}
      />

      <section className="source-ingest-grid">
        <article className="panel upload-panel">
          <div className="panel-heading compact-heading">
            <div><p className="eyebrow">FILES</p><h2>파일 가져오기</h2></div>
            <span className="file-support">PDF · DOCX · XLSX · CSV · MD</span>
          </div>
          <input ref={inputRef} className="visually-hidden" type="file" accept=".pdf,.docx,.xlsx,.csv,.md,.txt" multiple onChange={onFileInput} />
          <div
            className={`drop-zone ${dragActive ? "drop-zone-active" : ""}`}
            onDragEnter={(event) => { event.preventDefault(); setDragActive(true); }}
            onDragOver={(event) => event.preventDefault()}
            onDragLeave={(event) => { if (event.currentTarget === event.target) setDragActive(false); }}
            onDrop={onDrop}
          >
            <span className="drop-icon"><UploadCloud size={25} /></span>
            <strong>여기에 원본 파일을 놓으세요</strong>
            <p>또는 컴퓨터에서 직접 선택할 수 있습니다.</p>
            <button className="button button-secondary" type="button" onClick={() => inputRef.current?.click()}>
              파일 탐색기 열기
            </button>
          </div>

          {staged.length ? (
            <div className="staged-files">
              <div className="staged-heading"><strong>업로드 대기 {staged.length}개</strong><button type="button" onClick={() => setStaged([])}>전체 지우기</button></div>
              {staged.map((item) => (
                <div className="staged-file" key={item.id}>
                  <File size={17} />
                  <div><strong>{item.file.name}</strong><small>{formatBytes(item.file.size)}</small></div>
                  <button type="button" onClick={() => setStaged((current) => current.filter((file) => file.id !== item.id))} aria-label={`${item.file.name} 제거`}><X size={15} /></button>
                </div>
              ))}
              <button className="button button-primary staged-submit" type="button" onClick={submitStaged} disabled={submitting}>{submitting ? "업로드 중…" : "선택 파일 업로드"}</button>
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
              <div className="input-with-icon"><Link2 size={17} /><input id="source-url" type="url" value={url} onChange={(event) => setUrl(event.target.value)} placeholder="https://…" required /></div>
              <button className="button button-primary" type="submit" disabled={submitting}><Plus size={16} /> 등록</button>
            </div>
          </form>
          <div className="ingest-notes">
            <div><span>1</span><p><strong>원본 보관</strong>본문과 접근 시점을 snapshot으로 남깁니다.</p></div>
            <div><span>2</span><p><strong>안전한 수집</strong>내부 주소와 위험한 redirect는 차단합니다.</p></div>
            <div><span>3</span><p><strong>근거 연결</strong>추출한 구절을 요소별 출처로 연결합니다.</p></div>
          </div>
        </article>
      </section>

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
        {message ? <div className="table-notice" role="status">{message}</div> : null}
        <div className="source-list">
          {filtered.slice(0, 80).map((source) => (
            <article className="source-row" key={source.id}>
              <span className={`source-kind-icon kind-${source.kind}`}>{source.kind === "url" ? <Globe2 size={19} /> : source.kind === "spreadsheet" ? <FileSpreadsheet size={19} /> : <FileText size={19} />}</span>
              <div className="source-main"><strong>{source.label}</strong><span>{source.locator}</span></div>
              <span className={`source-state source-${source.status}`}><i />{SOURCE_STATUS_LABELS[source.status]}</span>
              <span className="source-links"><strong>{source.linkedElements}</strong><small>연결 요소</small></span>
              {source.locator.startsWith("http") ? <a className="icon-button" href={source.locator} target="_blank" rel="noreferrer" aria-label={`${source.label} 열기`}><ArrowUpRight size={17} /></a> : <span className="icon-button-placeholder" />}
            </article>
          ))}
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
