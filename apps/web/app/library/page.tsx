"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import { FileText, RefreshCw, Trash2, UploadCloud } from "lucide-react";
import { apiFetch, LibraryFile, LibraryFilePreview, ParsePreset, SubjectConfig, SystemConfig } from "../../lib/api";

const libraryPreviewChars = 200_000;

const sourceTypes = [
  ["textbook", "教材"],
  ["standard", "规范"],
  ["regulation", "法规"],
  ["exam", "真题"],
  ["note", "笔记"],
  ["other", "其他"],
];

const parsePresetOptions: Array<{ value: ParsePreset; label: string }> = [
  { value: "auto", label: "自动" },
  { value: "fast", label: "高速" },
  { value: "balanced", label: "均衡" },
  { value: "accurate", label: "高精度" },
  { value: "formula", label: "公式增强" },
];

export default function LibraryPage() {
  const [files, setFiles] = useState<LibraryFile[]>([]);
  const [uploadFiles, setUploadFiles] = useState<FileList | null>(null);
  const [message, setMessage] = useState("");
  const [previewError, setPreviewError] = useState("");
  const [loading, setLoading] = useState(false);
  const [preview, setPreview] = useState<LibraryFilePreview | null>(null);
  const [subjects, setSubjects] = useState<SubjectConfig[]>([]);
  const [parsePreset, setParsePreset] = useState<ParsePreset>("auto");
  const [forceOcr, setForceOcr] = useState(false);
  const [headerRatio, setHeaderRatio] = useState("0.00");
  const [footerRatio, setFooterRatio] = useState("0.00");
  const [meta, setMeta] = useState({
    subject: "",
    category: "",
    chapter: "",
    source_type: "textbook",
    source_authority: "high",
    source_title: "",
    source_publisher: "",
    source_code: "",
    source_version: "",
    year: "",
    tags: "",
  });
  const [filters, setFilters] = useState({ subject: "", search: "" });

  async function loadFiles() {
    const params = new URLSearchParams();
    if (filters.subject) params.set("subject", filters.subject);
    if (filters.search) params.set("search", filters.search);
    const data = await apiFetch<LibraryFile[]>(`/api/library/files?${params.toString()}`);
    setFiles(data);
  }

  async function loadSubjects() {
    const data = await apiFetch<SystemConfig>("/api/system/config");
    setSubjects(data.subjects);
    setMeta((current) => normalizeMetaSubject(current, data.subjects));
  }

  useEffect(() => {
    loadFiles().catch((error) => setMessage(error.message));
    loadSubjects().catch((error) => setMessage(error.message));
  }, []);

  const totalSize = useMemo(() => files.reduce((sum, file) => sum + file.size, 0), [files]);
  const activeSubject = useMemo(
    () => subjects.find((subject) => subject.name === meta.subject) || null,
    [meta.subject, subjects]
  );

  async function onUpload(event: FormEvent) {
    event.preventDefault();
    if (!uploadFiles?.length) {
      setMessage("请选择要上传的资料。");
      return;
    }
    if (!meta.subject) {
      setMessage("请先在设置页添加学科。");
      return;
    }
    setLoading(true);
    setMessage("");
    try {
      const form = new FormData();
      Array.from(uploadFiles).forEach((file) => form.append("files", file));
      form.append(
        "batch_meta",
        JSON.stringify({
          ...meta,
          source_title: meta.source_title.trim(),
          year: meta.year ? Number(meta.year) : null,
          tags: meta.tags.split(/[，,\s]+/).filter(Boolean),
        })
      );
      await apiFetch<LibraryFile[]>("/api/library/upload", { method: "POST", body: form });
      setMessage("上传完成。");
      await loadFiles();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "上传失败");
    } finally {
      setLoading(false);
    }
  }

  async function deleteFile(id: string) {
    await apiFetch(`/api/library/files/${id}`, { method: "DELETE" });
    await loadFiles();
  }

  async function showPreview(file: LibraryFile) {
    setPreviewError("");
    const params = new URLSearchParams({
      max_chars: String(libraryPreviewChars),
      preset: parsePreset,
    });
    if (forceOcr) params.set("force_ocr", "true");
    if (Number(headerRatio) > 0) params.set("crop_header_ratio", String(Number(headerRatio)));
    if (Number(footerRatio) > 0) params.set("crop_footer_ratio", String(Number(footerRatio)));
    try {
      const data = await apiFetch<LibraryFilePreview>(
        `/api/library/files/${file.id}/preview?${params.toString()}`
      );
      setPreview(data);
      await loadFiles();
    } catch (error) {
      setPreviewError(error instanceof Error ? error.message : "预览失败");
    }
  }

  return (
    <>
      <header className="pageHeader">
        <div>
          <h1>素材库</h1>
          <p>上传教材、规范、法规、真题和笔记，系统会按 SHA256 去重，并在首次使用时解析缓存。</p>
        </div>
        <div className="buttonRow">
          <span className="badge">{files.length} 个文件</span>
          <span className="badge">{(totalSize / 1024 / 1024).toFixed(2)} MB</span>
        </div>
      </header>

      <section className="gridTwo">
        <form className="panel" onSubmit={onUpload}>
          <div className="panelHeader">
            <h2>批量上传</h2>
            <p>先填写批次元数据，必要时后续可单独编辑文件。</p>
          </div>
          <div className="panelBody formGrid">
            <label className="dropzone">
              <UploadCloud size={28} />
              <strong>{uploadFiles?.length ? `${uploadFiles.length} 个文件已选择` : "选择或拖入资料"}</strong>
              <span>PDF / 图片 / DOCX / Markdown / TXT</span>
              <input
                hidden
                multiple
                type="file"
                accept=".pdf,.doc,.docx,.md,.markdown,.txt,.png,.jpg,.jpeg,.webp,.bmp,.tif,.tiff,application/pdf,image/*"
                onChange={(event) => setUploadFiles(event.target.files)}
              />
            </label>
            <div className="row">
              <div className="field">
                <label>学科</label>
                <select value={meta.subject} onChange={(e) => setMeta(selectMetaSubject(meta, subjects, e.target.value))}>
                  {!subjects.length && <option value="">请先添加学科</option>}
                  {subjects.map((subject) => (
                    <option key={subject.id} value={subject.name}>
                      {subject.name}
                    </option>
                  ))}
                </select>
              </div>
              <div className="field">
                <label>类目</label>
                <select value={meta.category} onChange={(e) => setMeta({ ...meta, category: e.target.value })}>
                  <option value="">未分类</option>
                  {activeSubject?.categories.map((category) => (
                    <option key={category} value={category}>
                      {category}
                    </option>
                  ))}
                </select>
              </div>
            </div>
            <div className="field">
              <label>章节</label>
              <input value={meta.chapter} onChange={(e) => setMeta({ ...meta, chapter: e.target.value })} />
            </div>
            <div className="row">
              <div className="field">
                <label>来源类型</label>
                <select value={meta.source_type} onChange={(e) => setMeta({ ...meta, source_type: e.target.value })}>
                  {sourceTypes.map(([value, label]) => (
                    <option key={value} value={value}>
                      {label}
                    </option>
                  ))}
                </select>
              </div>
              <div className="field">
                <label>权威等级</label>
                <select
                  value={meta.source_authority}
                  onChange={(e) => setMeta({ ...meta, source_authority: e.target.value })}
                >
                  <option value="high">high</option>
                  <option value="medium">medium</option>
                  <option value="low">low</option>
                </select>
              </div>
            </div>
            <div className="field">
              <label>来源标题</label>
              <input
                value={meta.source_title}
                onChange={(e) => setMeta({ ...meta, source_title: e.target.value })}
                placeholder="例如 2026 CPA 会计教材"
              />
            </div>
            <div className="row">
              <div className="field">
                <label>版本/规范号</label>
                <input
                  value={meta.source_version}
                  onChange={(e) => setMeta({ ...meta, source_version: e.target.value })}
                />
              </div>
              <div className="field">
                <label>年份</label>
                <input value={meta.year} onChange={(e) => setMeta({ ...meta, year: e.target.value })} />
              </div>
            </div>
            <div className="field">
              <label>标签</label>
              <input
                value={meta.tags}
                onChange={(e) => setMeta({ ...meta, tags: e.target.value })}
                placeholder="高频, 易错, 冲刺"
              />
            </div>
            <div className="buttonRow">
              <button className="button primary" disabled={loading} type="submit">
                <UploadCloud size={17} />
                上传入库
              </button>
              <button className="button" type="button" onClick={loadFiles}>
                <RefreshCw size={17} />
                刷新
              </button>
            </div>
            {message && <p className="muted">{message}</p>}
          </div>
        </form>

        <div className="panel">
          <div className="panelHeader">
            <h2>文件列表</h2>
            <p>按学科和关键词筛选，预览时会触发解析缓存。</p>
          </div>
          <div className="panelBody formGrid">
            <div className="row">
              <div className="field">
                <label>解析预设</label>
                <select value={parsePreset} onChange={(e) => setParsePreset(e.target.value as ParsePreset)}>
                  {parsePresetOptions.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
              </div>
              <div className="field">
                <label>强制 OCR</label>
                <select value={forceOcr ? "true" : "false"} onChange={(e) => setForceOcr(e.target.value === "true")}>
                  <option value="false">否</option>
                  <option value="true">是</option>
                </select>
              </div>
            </div>
            <div className="row">
              <div className="field">
                <label>页眉裁切</label>
                <input value={headerRatio} onChange={(e) => setHeaderRatio(e.target.value)} placeholder="0.04" />
              </div>
              <div className="field">
                <label>页脚裁切</label>
                <input value={footerRatio} onChange={(e) => setFooterRatio(e.target.value)} placeholder="0.05" />
              </div>
            </div>
            <div className="row">
              <div className="field">
                <label>学科筛选</label>
                <select value={filters.subject} onChange={(e) => setFilters({ ...filters, subject: e.target.value })}>
                  <option value="">全部学科</option>
                  {subjects.map((subject) => (
                    <option key={subject.id} value={subject.name}>
                      {subject.name}
                    </option>
                  ))}
                </select>
              </div>
              <div className="field">
                <label>搜索</label>
                <input value={filters.search} onChange={(e) => setFilters({ ...filters, search: e.target.value })} />
              </div>
            </div>
            <button className="button" type="button" onClick={loadFiles}>
              <RefreshCw size={17} />
              应用筛选
            </button>
            {previewError && <p className="errorText">{previewError}</p>}
            <div className="tableWrap">
              <table>
                <thead>
                  <tr>
                    <th>文件</th>
                    <th>学科/类目</th>
                    <th>来源</th>
                    <th>Token</th>
                    <th>操作</th>
                  </tr>
                </thead>
                <tbody>
                  {files.map((file) => (
                    <tr key={file.id}>
                      <td>
                        <strong>{file.filename}</strong>
                        <div className="muted">{(file.size / 1024).toFixed(1)} KB</div>
                      </td>
                      <td>
                        {file.subject}
                        <div className="muted">{[file.category, file.chapter].filter(Boolean).join(" / ")}</div>
                      </td>
                      <td>
                        <span className={`badge ${file.source_authority}`}>{file.source_authority}</span>
                        <div className="muted">{file.source_title}</div>
                      </td>
                      <td>{renderTokenStatus(file)}</td>
                      <td>
                        <div className="buttonRow">
                          <button className="button" type="button" onClick={() => showPreview(file)}>
                            <FileText size={16} />
                          </button>
                          <button className="button danger" type="button" onClick={() => deleteFile(file.id)}>
                            <Trash2 size={16} />
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {!files.length && <div className="empty">素材库还没有文件。</div>}
          </div>
        </div>
      </section>

      {preview && (
        <section className="panel" style={{ marginTop: 18 }}>
          <div className="panelHeader">
            <h2>{preview.filename}</h2>
            <p>
              估算 Token：{preview.token_count.toLocaleString()} · 解析器：{preview.provider} · 表格：{preview.table_count}
            </p>
          </div>
          <div className="panelBody">
            {!!Object.keys(preview.parse_options || {}).length && (
              <p className="muted">解析参数：{JSON.stringify(preview.parse_options)}</p>
            )}
            {!!preview.warnings.length && <p className="muted">{preview.warnings.join(" | ")}</p>}
            <pre className="markdown">{preview.markdown || preview.text}</pre>
          </div>
        </section>
      )}
    </>
  );
}

function renderTokenStatus(file: LibraryFile) {
  if (file.token_count == null) return "未解析";
  if (file.token_count === 0) return "解析为空";
  return file.token_count.toLocaleString();
}

type LibraryMeta = {
  subject: string;
  category: string;
  chapter: string;
  source_type: string;
  source_authority: string;
  source_title: string;
  source_publisher: string;
  source_code: string;
  source_version: string;
  year: string;
  tags: string;
};

function normalizeMetaSubject(meta: LibraryMeta, subjects: SubjectConfig[]): LibraryMeta {
  const subject = findSubject(subjects, meta.subject) || subjects[0];
  if (!subject) return { ...meta, subject: "", category: "" };
  return {
    ...meta,
    subject: subject.name,
    category: subject.categories.includes(meta.category) ? meta.category : subject.categories[0] || "",
  };
}

function selectMetaSubject(meta: LibraryMeta, subjects: SubjectConfig[], name: string): LibraryMeta {
  const subject = findSubject(subjects, name);
  if (!subject) return { ...meta, subject: name, category: "" };
  return {
    ...meta,
    subject: subject.name,
    category: subject.categories.includes(meta.category) ? meta.category : subject.categories[0] || "",
  };
}

function findSubject(subjects: SubjectConfig[], value: string): SubjectConfig | undefined {
  const normalized = value.trim().toLowerCase();
  return subjects.find(
    (subject) =>
      subject.name === value ||
      subject.id.toLowerCase() === normalized ||
      (normalized === "cpa" && subject.id === "cpa")
  );
}
