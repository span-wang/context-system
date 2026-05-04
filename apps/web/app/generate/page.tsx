"use client";

import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AlertTriangle, CheckCircle2, RefreshCw, ShieldCheck, UploadCloud, Wand2 } from "lucide-react";
import {
  API_BASE,
  apiFetch,
  contentTypeLabels,
  ContentType,
  GenerationJob,
  LibraryFile,
  ReviewMode,
  reviewModeLabels,
  SubjectConfig,
  SystemConfig,
} from "../../lib/api";

const contentTypes = Object.keys(contentTypeLabels) as ContentType[];
const generationDraftKey = "context-for-xhs:generation-draft";
const generationJobKey = "context-for-xhs:last-generation-job";
const generationJobIdKey = "context-for-xhs:last-generation-job-id";
const reviewModeKey = "context-for-xhs:review-mode";
const reviewModes = Object.keys(reviewModeLabels) as ReviewMode[];
const activeGenerationStatuses = new Set<GenerationJob["status"]>([
  "pending",
  "retrieving",
  "generating",
  "reviewing",
]);

type GenerationMode = "direct" | "ragflow";
type GenerationForm = {
  subject: string;
  category: string;
  chapter: string;
  content_type: ContentType;
  pages: string;
  user_notes: string;
  ragflow_dataset_ids: string;
};
type GenerationDraft = {
  mode: GenerationMode;
  selected: string[];
  saveUploads: boolean;
  form: GenerationForm;
};

const defaultForm: GenerationForm = {
  subject: "",
  category: "",
  chapter: "",
  content_type: "tri_color",
  pages: "10",
  user_notes: "",
  ragflow_dataset_ids: "",
};

function isActiveGeneration(job: GenerationJob) {
  return activeGenerationStatuses.has(job.status);
}

function readMemory<T>(key: string): T | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : null;
  } catch {
    forgetMemory(key);
    return null;
  }
}

function writeMemory<T>(key: string, value: T) {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(key, JSON.stringify(value));
  } catch {
    forgetMemory(key);
  }
}

function forgetMemory(key: string) {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.removeItem(key);
  } catch {
    // localStorage can be unavailable in strict privacy modes.
  }
}

function rememberJobId(jobId: string) {
  writeMemory(generationJobIdKey, jobId);
}

function rememberJob(job: GenerationJob) {
  rememberJobId(job.id);
  writeMemory(generationJobKey, job);
}

function forgetRememberedJob() {
  forgetMemory(generationJobKey);
  forgetMemory(generationJobIdKey);
}

export default function GeneratePage() {
  const streamRef = useRef<EventSource | null>(null);
  const [memoryReady, setMemoryReady] = useState(false);
  const [mode, setMode] = useState<GenerationMode>("direct");
  const [files, setFiles] = useState<LibraryFile[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [uploadFiles, setUploadFiles] = useState<FileList | null>(null);
  const [saveUploads, setSaveUploads] = useState(true);
  const [job, setJob] = useState<GenerationJob | null>(null);
  const [message, setMessage] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [reviewing, setReviewing] = useState(false);
  const [reviewMode, setReviewMode] = useState<ReviewMode>("hybrid");
  const [form, setForm] = useState<GenerationForm>(defaultForm);
  const [subjects, setSubjects] = useState<SubjectConfig[]>([]);

  async function loadFiles() {
    const data = await apiFetch<LibraryFile[]>("/api/library/files");
    setFiles(data);
  }

  async function loadSubjects() {
    const data = await apiFetch<SystemConfig>("/api/system/config");
    setSubjects(data.subjects);
    setForm((current) => normalizeFormSubject(current, data.subjects));
  }

  const closeStream = useCallback(() => {
    streamRef.current?.close();
    streamRef.current = null;
  }, []);

  const applyJob = useCallback((nextJob: GenerationJob) => {
    setJob(nextJob);
    rememberJob(nextJob);
  }, []);

  const watchJob = useCallback(
    (jobId: string) => {
      rememberJobId(jobId);
      closeStream();

      const events = new EventSource(`${API_BASE}/api/generate/${jobId}/stream`);
      streamRef.current = events;

      events.addEventListener("status", (event) => {
        const payload = JSON.parse((event as MessageEvent).data) as {
          id: string;
          status: GenerationJob["status"];
          error?: string | null;
        };
        setJob((current) => {
          const nextJob = current?.id === jobId ? { ...current, status: payload.status, error: payload.error } : current;
          if (nextJob) rememberJob(nextJob);
          return nextJob;
        });
        setMessage(`当前状态：${payload.status}`);
      });

      events.addEventListener("done", (event) => {
        const payload = JSON.parse((event as MessageEvent).data) as GenerationJob;
        applyJob(payload);
        setMessage(payload.status === "done" ? "生成完成。" : payload.error || "任务失败");
        closeStream();
      });

      events.onerror = () => {
        closeStream();
        apiFetch<GenerationJob>(`/api/generate/${jobId}`)
          .then((fallback) => {
            applyJob(fallback);
            if (isActiveGeneration(fallback)) watchJob(fallback.id);
          })
          .catch((error) => {
            forgetRememberedJob();
            setJob(null);
            setMessage(error.message);
          });
      };
    },
    [applyJob, closeStream]
  );

  useEffect(() => {
    loadFiles().catch((error) => setMessage(error.message));
    loadSubjects().catch((error) => setMessage(error.message));
  }, []);

  useEffect(() => {
    const draft = readMemory<GenerationDraft>(generationDraftKey);
    if (draft) {
      setMode(draft.mode);
      setSelected(draft.selected);
      setSaveUploads(draft.saveUploads);
      setForm({ ...defaultForm, ...draft.form });
    }
    setReviewMode(readMemory<ReviewMode>(reviewModeKey) || "hybrid");

    let cancelled = false;
    const rememberedJob = readMemory<GenerationJob>(generationJobKey);
    const rememberedJobId = readMemory<string>(generationJobIdKey);
    const jobId = rememberedJob?.id || rememberedJobId;
    if (rememberedJob) {
      setJob(rememberedJob);
    }
    if (jobId) {
      apiFetch<GenerationJob>(`/api/generate/${jobId}`)
        .then((latest) => {
          if (cancelled) return;
          applyJob(latest);
          setMessage(isActiveGeneration(latest) ? `已恢复上次任务：${latest.status}` : "已恢复上次生成任务。");
          if (isActiveGeneration(latest)) watchJob(latest.id);
        })
        .catch(() => {
          if (cancelled) return;
          forgetRememberedJob();
          setJob(null);
        });
    }

    setMemoryReady(true);
    return () => {
      cancelled = true;
      closeStream();
    };
  }, [applyJob, closeStream, watchJob]);

  useEffect(() => {
    if (!memoryReady) return;
    writeMemory<GenerationDraft>(generationDraftKey, {
      mode,
      selected,
      saveUploads,
      form,
    });
    writeMemory<ReviewMode>(reviewModeKey, reviewMode);
  }, [form, memoryReady, mode, reviewMode, saveUploads, selected]);

  const selectedTokens = useMemo(
    () =>
      files
        .filter((file) => selected.includes(file.id))
        .reduce((sum, file) => sum + (file.token_count || 0), 0),
    [files, selected]
  );
  const activeSubject = useMemo(
    () => subjects.find((subject) => subject.name === form.subject) || null,
    [form.subject, subjects]
  );

  function toggleFile(id: string) {
    setSelected((current) => (current.includes(id) ? current.filter((item) => item !== id) : [...current, id]));
  }

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    setMessage("");
    setJob(null);
    closeStream();
    try {
      if (!form.subject) {
        setMessage("请先在设置页添加学科。");
        return;
      }
      const hasNewUploads = mode === "direct" && Boolean(uploadFiles?.length);
      const response = hasNewUploads ? await submitMultipart() : await submitJson();
      rememberJobId(response.job_id);
      setMessage(`任务已创建：${response.job_id}`);
      const createdJob = await apiFetch<GenerationJob>(`/api/generate/${response.job_id}`);
      applyJob(createdJob);
      if (isActiveGeneration(createdJob)) watchJob(createdJob.id);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "生成失败");
    } finally {
      setSubmitting(false);
    }
  }

  async function submitJson() {
    return apiFetch<{ job_id: string }>("/api/generate", {
      method: "POST",
      body: JSON.stringify({
        mode,
        subject: form.subject,
        category: form.category || null,
        chapter: form.chapter || null,
        content_type: form.content_type,
        options: { pages: Number(form.pages || 10) },
        user_notes: form.user_notes || null,
        library_file_ids: mode === "direct" ? selected : [],
        ragflow_dataset_ids:
          mode === "ragflow"
            ? form.ragflow_dataset_ids.split(/[,\s，]+/).map((item) => item.trim()).filter(Boolean)
            : [],
      }),
    });
  }

  async function submitMultipart() {
    const body = new FormData();
    body.append("subject", form.subject);
    body.append("category", form.category);
    body.append("chapter", form.chapter);
    body.append("content_type", form.content_type);
    body.append("options", JSON.stringify({ pages: Number(form.pages || 10) }));
    body.append("user_notes", form.user_notes);
    body.append("library_file_ids", JSON.stringify(selected));
    body.append("save_uploads_to_library", String(saveUploads));
    body.append(
      "batch_meta",
      JSON.stringify({
        subject: form.subject,
        category: form.category || null,
        chapter: form.chapter || null,
        source_type: "note",
        source_authority: "medium",
        source_title: `${form.subject}-${form.chapter || form.category || "uploaded"}`,
        tags: ["direct-upload"],
      })
    );
    Array.from(uploadFiles || []).forEach((file) => body.append("new_uploads", file));
    return apiFetch<{ job_id: string }>("/api/generate/multipart", { method: "POST", body });
  }

  async function runContentReview() {
    if (!job?.result) return;
    setReviewing(true);
    setMessage("正在内容审查...");
    setJob((current) => {
      const nextJob = current ? { ...current, status: "reviewing" as const } : current;
      if (nextJob) rememberJob(nextJob);
      return nextJob;
    });
    try {
      const updated = await apiFetch<GenerationJob>(`/api/generate/${job.id}/review`, {
        method: "POST",
        body: JSON.stringify({ mode: reviewMode }),
      });
      applyJob(updated);
      setMessage("内容审查完成。");
    } catch (error) {
      const fallback = await apiFetch<GenerationJob>(`/api/generate/${job.id}`).catch(() => null);
      if (fallback) applyJob(fallback);
      setMessage(error instanceof Error ? error.message : "内容审查失败");
    } finally {
      setReviewing(false);
    }
  }

  return (
    <>
      <header className="pageHeader">
        <div>
          <h1>生成中心</h1>
          <p>模式 A 连接 RAGFlow 检索个人知识库；模式 B 使用素材库和补充说明做长上下文直通生成。</p>
        </div>
        <div className="tabs">
          <button className={mode === "direct" ? "tab active" : "tab"} type="button" onClick={() => setMode("direct")}>
            模式 B
          </button>
          <button className={mode === "ragflow" ? "tab active" : "tab"} type="button" onClick={() => setMode("ragflow")}>
            模式 A
          </button>
        </div>
      </header>

      <section className="gridTwo">
        <form className="panel" onSubmit={onSubmit}>
          <div className="panelHeader">
            <h2>任务参数</h2>
            <p>{mode === "direct" ? "资料可选；无资料会自动加未核验标记。" : "填写 RAGFlow dataset id 后检索生成。"}</p>
          </div>
          <div className="panelBody formGrid">
            <div className="row">
              <div className="field">
                <label>学科</label>
                <select
                  value={form.subject}
                  onChange={(e) => setForm(selectSubject(form, subjects, e.target.value))}
                >
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
                <select value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })}>
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
              <input value={form.chapter} onChange={(e) => setForm({ ...form, chapter: e.target.value })} />
            </div>
            <div className="row">
              <div className="field">
                <label>内容类型</label>
                <select
                  value={form.content_type}
                  onChange={(e) => setForm({ ...form, content_type: e.target.value as ContentType })}
                >
                  {contentTypes.map((type) => (
                    <option key={type} value={type}>
                      {contentTypeLabels[type]}
                    </option>
                  ))}
                </select>
              </div>
              <div className="field">
                <label>页数</label>
                <input value={form.pages} onChange={(e) => setForm({ ...form, pages: e.target.value })} />
              </div>
            </div>

            {mode === "ragflow" ? (
              <div className="field">
                <label>RAGFlow Dataset IDs</label>
                <input
                  value={form.ragflow_dataset_ids}
                  onChange={(e) => setForm({ ...form, ragflow_dataset_ids: e.target.value })}
                  placeholder="dataset_1, dataset_2"
                />
              </div>
            ) : (
              <div className="field">
                <label>选择素材</label>
                <div className="filePickList">
                  {files.map((file) => (
                    <label className="filePick" key={file.id}>
                      <input checked={selected.includes(file.id)} type="checkbox" onChange={() => toggleFile(file.id)} />
                      <span>
                        <strong>{file.source_title || file.filename}</strong>
                        <span className="muted" style={{ display: "block" }}>
                          {file.subject} / {file.category || "未分类"} / {file.chapter || "未填章节"}
                        </span>
                      </span>
                      <span className={`badge ${file.source_authority}`}>{file.source_authority}</span>
                    </label>
                  ))}
                  {!files.length && <div className="empty">先去素材库上传资料，或直接无资料生成。</div>}
                </div>
                <p className="muted">已解析素材估算：{selectedTokens.toLocaleString()} token。未解析文件会在提交时解析并拦截超限。</p>
              </div>
            )}

            {mode === "direct" && (
              <div className="field">
                <label>本次新上传</label>
                <label className="dropzone">
                  <UploadCloud size={26} />
                  <strong>{uploadFiles?.length ? `${uploadFiles.length} 个文件已选择` : "选择本次生成资料"}</strong>
                  <span>可与素材库文件混合使用</span>
                  <input
                    hidden
                    multiple
                    type="file"
                    onChange={(event) => setUploadFiles(event.target.files)}
                  />
                </label>
                <label className="checkLine">
                  <input
                    checked={saveUploads}
                    type="checkbox"
                    onChange={(event) => setSaveUploads(event.target.checked)}
                  />
                  保存本次上传到素材库
                </label>
              </div>
            )}

            <div className="field">
              <label>补充说明</label>
              <textarea
                value={form.user_notes}
                onChange={(e) => setForm({ ...form, user_notes: e.target.value })}
                placeholder="例如：偏小红书口吻，重点讲收入确认易错点，适合考前冲刺。"
              />
            </div>

            <div className="buttonRow">
              <button className="button primary" disabled={submitting} type="submit">
                <Wand2 size={17} />
                开始生成
              </button>
              <button className="button" type="button" onClick={loadFiles}>
                <RefreshCw size={17} />
                刷新素材
              </button>
            </div>
            {message && <p className="muted">{message}</p>}
          </div>
        </form>

        <div className="panel">
          <div className="panelHeader">
            <h2>生成结果</h2>
            <p>任务完成后展示 Markdown，可手动发起内容审查。</p>
          </div>
          <div className="panelBody">
            {!job && <div className="empty">还没有生成任务。</div>}
            {job && (
              <div className="formGrid">
                <div className="buttonRow">
                  <span className={`badge ${job.status}`}>{job.status}</span>
                  {job.result?.unverified && <span className="badge unverified">未核验</span>}
                  {job.review?.pass_overall ? (
                    <span className="badge pass">
                      <CheckCircle2 size={14} /> 审查通过
                    </span>
                  ) : job.review ? (
                    <span className="badge low">
                      <AlertTriangle size={14} /> 需复核
                    </span>
                  ) : null}
                  {job.review && <span className="badge">{reviewModeLabels[job.review.mode]}</span>}
                  {job.result && (
                    <button
                      className="button"
                      disabled={reviewing || job.status === "reviewing"}
                      type="button"
                      onClick={runContentReview}
                    >
                      <ShieldCheck size={16} />
                      内容审查
                    </button>
                  )}
                </div>
                {job.result && (
                  <div className="reviewModeGroup" aria-label="审查模式">
                    {reviewModes.map((mode) => (
                      <button
                        className={reviewMode === mode ? "reviewMode active" : "reviewMode"}
                        key={mode}
                        type="button"
                        onClick={() => setReviewMode(mode)}
                      >
                        {reviewModeLabels[mode]}
                      </button>
                    ))}
                  </div>
                )}
                {job.result && <pre className="markdown">{job.result.raw_markdown}</pre>}
                {job.result && !job.review && job.status !== "reviewing" && (
                  <div className="empty">尚未内容审查。</div>
                )}
                {job.status === "reviewing" && <div className="empty">正在内容审查...</div>}
                {job.review && (
                  <ul className="issueList">
                    {(job.review.issues.length ? job.review.issues : ["暂未发现审查问题。"]).map((issue) => (
                      <li key={issue}>{issue}</li>
                    ))}
                  </ul>
                )}
              </div>
            )}
          </div>
        </div>
      </section>
    </>
  );
}

function normalizeFormSubject(form: GenerationForm, subjects: SubjectConfig[]): GenerationForm {
  const subject = findSubject(subjects, form.subject) || subjects[0];
  if (!subject) return { ...form, subject: "", category: "" };
  return {
    ...form,
    subject: subject.name,
    category: subject.categories.includes(form.category) ? form.category : subject.categories[0] || "",
  };
}

function selectSubject(form: GenerationForm, subjects: SubjectConfig[], name: string): GenerationForm {
  const subject = findSubject(subjects, name);
  if (!subject) return { ...form, subject: name, category: "" };
  return {
    ...form,
    subject: subject.name,
    category: subject.categories.includes(form.category) ? form.category : subject.categories[0] || "",
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
