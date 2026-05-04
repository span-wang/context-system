"use client";

import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  ChevronDown,
  Clipboard,
  Database,
  ExternalLink,
  FileText,
  RefreshCw,
  Send,
  ShieldCheck,
  SquareCheck,
  UploadCloud,
  Wand2,
} from "lucide-react";
import ReviewActionList from "../../components/ReviewActionList";
import {
  API_BASE,
  LAYOUT_API_BASE,
  apiFetch,
  contentTypeLabels,
  ContentType,
  GenerationJob,
  layoutFetch,
  LayoutMarkdownDocument,
  LayoutMode,
  LayoutTemplatePayload,
  LibraryFile,
  LibraryFilePreview,
  RAGFlowDataset,
  RAGFlowDatasetList,
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
const layoutPromptKey = "context-for-xhs:layout-prompt";
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
  layout_mode_id: string;
};
type LayoutPromptDraft = {
  enabled: boolean;
  modeId: string;
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
  layout_mode_id: "knowledge",
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
  const markdownRef = useRef<HTMLPreElement | null>(null);
  const librarySelectRef = useRef<HTMLDivElement | null>(null);
  const ragflowSelectRef = useRef<HTMLDivElement | null>(null);
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
  const [layoutModes, setLayoutModes] = useState<LayoutMode[]>([]);
  const [layoutTemplate, setLayoutTemplate] = useState<LayoutTemplatePayload | null>(null);
  const [useLayoutPrompt, setUseLayoutPrompt] = useState(true);
  const [layoutMessage, setLayoutMessage] = useState("");
  const [layoutLoading, setLayoutLoading] = useState(false);
  const [promptPreview, setPromptPreview] = useState("");
  const [promptBuilding, setPromptBuilding] = useState(false);
  const [publishingLayout, setPublishingLayout] = useState(false);
  const [ragflowDatasets, setRagflowDatasets] = useState<RAGFlowDataset[]>([]);
  const [ragflowLoading, setRagflowLoading] = useState(false);
  const [ragflowMessage, setRagflowMessage] = useState("");
  const [openMultiSelect, setOpenMultiSelect] = useState<"library" | "ragflow" | null>(null);

  async function loadFiles() {
    const data = await apiFetch<LibraryFile[]>("/api/library/files");
    setFiles(data);
  }

  async function loadSubjects() {
    const data = await apiFetch<SystemConfig>("/api/system/config");
    setSubjects(data.subjects);
    setForm((current) => normalizeFormSubject(current, data.subjects));
  }

  async function loadLayoutModes() {
    const data = await layoutFetch<LayoutMode[]>("/api/v1/modes");
    setLayoutModes(data);
    setForm((current) => {
      if (current.layout_mode_id && data.some((item) => item.id === current.layout_mode_id)) return current;
      return { ...current, layout_mode_id: data[0]?.id || current.layout_mode_id };
    });
  }

  async function loadRagflowDatasets() {
    setRagflowLoading(true);
    setRagflowMessage("");
    try {
      const data = await apiFetch<RAGFlowDatasetList>("/api/system/ragflow/datasets");
      setRagflowDatasets(data.datasets);
      setRagflowMessage(data.datasets.length ? `已拉取 ${data.datasets.length} 个 dataset。` : "RAGFlow 暂无可用 dataset。");
    } catch (error) {
      const text = error instanceof Error ? error.message : "拉取 RAGFlow dataset 清单失败";
      setRagflowMessage(text);
      throw error;
    } finally {
      setRagflowLoading(false);
    }
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
    loadLayoutModes().catch((error) => {
      setUseLayoutPrompt(false);
      setLayoutMessage(`排版服务未连接：${error.message}`);
    });
  }, []);

  useEffect(() => {
    if (mode !== "ragflow" || ragflowDatasets.length || ragflowLoading) return;
    loadRagflowDatasets().catch((error) => setMessage(error.message));
  }, [mode, ragflowDatasets.length, ragflowLoading]);

  useEffect(() => {
    setOpenMultiSelect(null);
  }, [mode]);

  useEffect(() => {
    function handlePointerDown(event: PointerEvent) {
      const target = event.target as Node;
      if (
        librarySelectRef.current?.contains(target) ||
        ragflowSelectRef.current?.contains(target)
      ) {
        return;
      }
      setOpenMultiSelect(null);
    }

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") setOpenMultiSelect(null);
    }

    document.addEventListener("pointerdown", handlePointerDown);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("pointerdown", handlePointerDown);
      document.removeEventListener("keydown", handleKeyDown);
    };
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
    const layoutDraft = readMemory<LayoutPromptDraft>(layoutPromptKey);
    if (layoutDraft) {
      setUseLayoutPrompt(layoutDraft.enabled);
      if (layoutDraft.modeId) {
        setForm((current) => ({ ...current, layout_mode_id: layoutDraft.modeId }));
      }
    }

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
    writeMemory<LayoutPromptDraft>(layoutPromptKey, {
      enabled: useLayoutPrompt,
      modeId: form.layout_mode_id,
    });
  }, [form, memoryReady, mode, reviewMode, saveUploads, selected, useLayoutPrompt]);

  const selectedFiles = useMemo(() => files.filter((file) => selected.includes(file.id)), [files, selected]);
  const selectedMissingFileIds = useMemo(
    () => selected.filter((fileId) => !files.some((file) => file.id === fileId)),
    [files, selected]
  );
  const selectedFileNames = useMemo(
    () => [...selectedFiles.map((file) => file.source_title || file.filename), ...selectedMissingFileIds],
    [selectedFiles, selectedMissingFileIds]
  );
  const selectedFileSummary = selected.length
    ? `${selected.length} 个素材：${selectedFileNames.slice(0, 2).join("、")}${selected.length > 2 ? " 等" : ""}`
    : files.length
      ? "选择素材库资料"
      : "暂无素材库资料";
  const selectedTokens = useMemo(
    () => selectedFiles.reduce((sum, file) => sum + (file.token_count || 0), 0),
    [selectedFiles]
  );
  const activeSubject = useMemo(
    () => subjects.find((subject) => subject.name === form.subject) || null,
    [form.subject, subjects]
  );
  const activeLayoutMode = useMemo(
    () => layoutModes.find((layoutMode) => layoutMode.id === form.layout_mode_id) || null,
    [form.layout_mode_id, layoutModes]
  );
  const selectedRagflowDatasetIds = useMemo(
    () => parseDatasetIds(form.ragflow_dataset_ids),
    [form.ragflow_dataset_ids]
  );
  const selectedRagflowDatasets = useMemo(
    () => ragflowDatasets.filter((dataset) => selectedRagflowDatasetIds.includes(dataset.id)),
    [ragflowDatasets, selectedRagflowDatasetIds]
  );
  const selectedRagflowDatasetMissingIds = useMemo(
    () => selectedRagflowDatasetIds.filter((datasetId) => !ragflowDatasets.some((dataset) => dataset.id === datasetId)),
    [ragflowDatasets, selectedRagflowDatasetIds]
  );
  const selectedRagflowDatasetNames = useMemo(
    () => [
      ...selectedRagflowDatasets.map((dataset) => dataset.name || dataset.id),
      ...selectedRagflowDatasetMissingIds,
    ],
    [selectedRagflowDatasets, selectedRagflowDatasetMissingIds]
  );
  const ragflowDatasetSummary = selectedRagflowDatasetIds.length
    ? `${selectedRagflowDatasetIds.length} 个 dataset：${selectedRagflowDatasetNames.slice(0, 2).join("、")}${
        selectedRagflowDatasetIds.length > 2 ? " 等" : ""
      }`
    : ragflowLoading
      ? "正在拉取 RAGFlow dataset 清单..."
      : ragflowDatasets.length
        ? "选择 RAGFlow dataset"
        : "还没有拉取到可用 dataset";

  function toggleFile(id: string) {
    setSelected((current) => (current.includes(id) ? current.filter((item) => item !== id) : [...current, id]));
  }

  function toggleRagflowDataset(id: string) {
    setForm((current) => {
      const datasetIds = parseDatasetIds(current.ragflow_dataset_ids);
      const nextIds = datasetIds.includes(id) ? datasetIds.filter((item) => item !== id) : [...datasetIds, id];
      return { ...current, ragflow_dataset_ids: nextIds.join(", ") };
    });
  }

  async function loadLayoutTemplate(modeId = form.layout_mode_id) {
    if (!modeId) {
      setLayoutMessage("请先选择排版模式。");
      return null;
    }
    setLayoutLoading(true);
    setLayoutMessage("");
    try {
      const data = await layoutFetch<LayoutTemplatePayload>(
        `/api/v1/modes/${encodeURIComponent(modeId)}/markdown-template`
      );
      setLayoutTemplate(data);
      return data;
    } catch (error) {
      const text = error instanceof Error ? error.message : "排版模板加载失败";
      setLayoutMessage(text);
      throw error;
    } finally {
      setLayoutLoading(false);
    }
  }

  async function buildLayoutPrompt(options: { refresh?: boolean } = {}) {
    if (!form.layout_mode_id) return "";
    setPromptBuilding(true);
    setLayoutMessage("");
    try {
      const template =
        options.refresh || layoutTemplate?.modeId !== form.layout_mode_id
          ? await loadLayoutTemplate(form.layout_mode_id)
          : layoutTemplate;
      if (!template) return "";
      const sourceContent = await collectPromptSourceContent();
      const prompt = composeLayoutPrompt(template.template, sourceContent);
      setPromptPreview(prompt);
      return prompt;
    } catch (error) {
      setPromptPreview("");
      setLayoutMessage(error instanceof Error ? error.message : "提示词拼接失败");
      return "";
    } finally {
      setPromptBuilding(false);
    }
  }

  async function collectPromptSourceContent() {
    const blocks: string[] = [];
    blocks.push(`【任务信息】`);
    blocks.push(`学科：${form.subject || "未填写"}`);
    blocks.push(`类目：${form.category || "未填写"}`);
    blocks.push(`章节：${form.chapter || "未填写"}`);
    blocks.push(`内容类型：${contentTypeLabels[form.content_type]}`);
    blocks.push(`目标页数：${form.pages || "未填写"}`);
    blocks.push("");

    if (form.user_notes.trim()) {
      blocks.push("【补充说明】");
      blocks.push(form.user_notes.trim());
      blocks.push("");
    }

    if (mode === "direct" && selected.length) {
      const previews = await Promise.all(
        selected.map((fileId) => apiFetch<LibraryFilePreview>(`/api/library/files/${fileId}/preview`))
      );
      blocks.push("【素材库资料】");
      previews.forEach((preview, index) => {
        blocks.push(`--- 素材 ${index + 1}：${preview.filename}${preview.truncated ? "（已截断预览）" : ""} ---`);
        blocks.push(preview.text.trim() || "（无可用文本）");
      });
      blocks.push("");
    }

    if (mode === "ragflow") {
      blocks.push("【RAGFlow 检索要求】");
      blocks.push(`Dataset IDs：${selectedRagflowDatasetIds.join(", ") || "未填写"}`);
      blocks.push("生成时请结合后端检索到的资料正文；本预览仅包含检索条件。");
      blocks.push("");
    }

    if (mode === "direct" && uploadFiles?.length) {
      blocks.push("【本次新上传】");
      const uploadBlocks = await Promise.all(
        Array.from(uploadFiles).map(async (file, index) => {
          const text = await readUploadPreview(file);
          return [`--- 上传 ${index + 1}：${file.name} ---`, text || "（无法在浏览器中预览该文件，提交生成后由后端解析。）"].join("\n");
        })
      );
      blocks.push(uploadBlocks.join("\n\n"));
      blocks.push("");
    }

    if (blocks.length <= 8) {
      blocks.push("【原始资料】");
      blocks.push("本次未选择素材，请仅生成可复核的结构初稿，并保留未核验提示。");
    }

    return blocks.join("\n").trim();
  }

  async function copyPrompt() {
    const prompt = promptPreview || (await buildLayoutPrompt());
    if (!prompt) return;
    await navigator.clipboard.writeText(prompt);
    setLayoutMessage("完整提示词已复制。");
  }

  async function publishToLayout() {
    if (!job?.result?.raw_markdown) return;
    setPublishingLayout(true);
    setLayoutMessage("");
    try {
      const created = await layoutFetch<LayoutMarkdownDocument>("/api/v1/markdown-documents", {
        method: "POST",
        body: JSON.stringify({
          markdown: job.result.raw_markdown,
          modeId: form.layout_mode_id || activeLayoutMode?.id,
          title: job.result.title,
          source: "context-for-xhs",
          metadata: {
            jobId: job.id,
            subject: job.context.subject,
            category: job.context.category,
            chapter: job.context.chapter,
            contentType: job.context.content_type,
          },
        }),
      });
      setLayoutMessage(`已发送到排版工具：${created.title}`);
      window.open(`${LAYOUT_API_BASE}/`, "_blank", "noopener,noreferrer");
    } catch (error) {
      setLayoutMessage(error instanceof Error ? error.message : "发送到排版工具失败");
    } finally {
      setPublishingLayout(false);
    }
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
      if (mode === "ragflow" && !selectedRagflowDatasetIds.length) {
        setMessage("请先选择一个 RAGFlow dataset。");
        return;
      }
      const layoutPrompt = useLayoutPrompt ? await buildLayoutPrompt() : "";
      if (useLayoutPrompt && !layoutPrompt) {
        setMessage("排版提示词未生成，请确认 Layout_For_Xhs 已启动并能拉取模板。");
        return;
      }
      const hasNewUploads = mode === "direct" && Boolean(uploadFiles?.length);
      const response = hasNewUploads ? await submitMultipart(layoutPrompt) : await submitJson(layoutPrompt);
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

  async function submitJson(layoutPrompt: string) {
    return apiFetch<{ job_id: string }>("/api/generate", {
      method: "POST",
      body: JSON.stringify({
        mode,
        subject: form.subject,
        category: form.category || null,
        chapter: form.chapter || null,
        content_type: form.content_type,
        options: buildGenerationOptions(form.pages, layoutPrompt, activeLayoutMode),
        user_notes: form.user_notes || null,
        library_file_ids: mode === "direct" ? selected : [],
        ragflow_dataset_ids: mode === "ragflow" ? selectedRagflowDatasetIds : [],
      }),
    });
  }

  async function submitMultipart(layoutPrompt: string) {
    const body = new FormData();
    body.append("subject", form.subject);
    body.append("category", form.category);
    body.append("chapter", form.chapter);
    body.append("content_type", form.content_type);
    body.append("options", JSON.stringify(buildGenerationOptions(form.pages, layoutPrompt, activeLayoutMode)));
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
                <div className="fieldHeader">
                  <label>RAGFlow Dataset</label>
                  <button className="button small" disabled={ragflowLoading} type="button" onClick={loadRagflowDatasets}>
                    <RefreshCw size={15} />
                    刷新
                  </button>
                </div>
                <div className="multiSelect" ref={ragflowSelectRef}>
                  <button
                    aria-expanded={openMultiSelect === "ragflow"}
                    className="multiSelectButton"
                    disabled={ragflowLoading || (!ragflowDatasets.length && !selectedRagflowDatasetMissingIds.length)}
                    type="button"
                    onClick={() => setOpenMultiSelect((current) => (current === "ragflow" ? null : "ragflow"))}
                  >
                    <span className="multiSelectIcon">
                      <Database size={17} />
                    </span>
                    <span>
                      <strong>{ragflowDatasetSummary}</strong>
                      <small>{selectedRagflowDatasetIds.length ? "可继续选择多个 dataset" : "RAGFlow 检索会使用选中的 dataset"}</small>
                    </span>
                    <ChevronDown size={16} />
                  </button>
                  {openMultiSelect === "ragflow" && (
                    <div className="multiSelectPanel">
                      {ragflowDatasets.map((dataset) => (
                        <label className="multiSelectOption" key={dataset.id}>
                          <input
                            checked={selectedRagflowDatasetIds.includes(dataset.id)}
                            type="checkbox"
                            onChange={() => toggleRagflowDataset(dataset.id)}
                          />
                          <span className="multiSelectCheck">
                            <SquareCheck size={15} />
                          </span>
                          <span className="multiSelectOptionBody">
                            <strong>{dataset.name || dataset.id}</strong>
                            <small>{dataset.id}</small>
                          </span>
                          <span className="multiSelectBadges">
                            {dataset.document_count != null && <span className="badge">{dataset.document_count} docs</span>}
                            {dataset.chunk_count != null && <span className="badge">{dataset.chunk_count} chunks</span>}
                            {dataset.running_count ? <span className="badge medium">{dataset.running_count} parsing</span> : null}
                            {dataset.fail_count ? <span className="badge low">{dataset.fail_count} failed</span> : null}
                          </span>
                        </label>
                      ))}
                      {selectedRagflowDatasetMissingIds.map((datasetId) => (
                        <label className="multiSelectOption" key={datasetId}>
                          <input checked type="checkbox" onChange={() => toggleRagflowDataset(datasetId)} />
                          <span className="multiSelectCheck">
                            <SquareCheck size={15} />
                          </span>
                          <span className="multiSelectOptionBody">
                            <strong>{datasetId}</strong>
                            <small>已保存的 dataset id</small>
                          </span>
                        </label>
                      ))}
                    </div>
                  )}
                </div>
                <div className="selectMetaLine">
                  <span>{selectedRagflowDatasetIds.length ? `已选 ${selectedRagflowDatasetIds.length} 个 dataset` : "未选择 dataset"}</span>
                  {selectedRagflowDatasets.reduce((sum, dataset) => sum + (dataset.document_count || 0), 0) > 0 && (
                    <span>{selectedRagflowDatasets.reduce((sum, dataset) => sum + (dataset.document_count || 0), 0)} docs</span>
                  )}
                  {selectedRagflowDatasets.reduce((sum, dataset) => sum + (dataset.chunk_count || 0), 0) > 0 && (
                    <span>{selectedRagflowDatasets.reduce((sum, dataset) => sum + (dataset.chunk_count || 0), 0)} chunks</span>
                  )}
                </div>
                {ragflowMessage && <p className="muted">{ragflowMessage}</p>}
              </div>
            ) : (
              <div className="field">
                <label>选择素材</label>
                <div className="multiSelect" ref={librarySelectRef}>
                  <button
                    aria-expanded={openMultiSelect === "library"}
                    className="multiSelectButton"
                    disabled={!files.length && !selectedMissingFileIds.length}
                    type="button"
                    onClick={() => setOpenMultiSelect((current) => (current === "library" ? null : "library"))}
                  >
                    <span className="multiSelectIcon">
                      <FileText size={17} />
                    </span>
                    <span>
                      <strong>{selectedFileSummary}</strong>
                      <small>{selected.length ? `${selectedTokens.toLocaleString()} token` : "可与本次新上传资料混合使用"}</small>
                    </span>
                    <ChevronDown size={16} />
                  </button>
                  {openMultiSelect === "library" && (
                    <div className="multiSelectPanel">
                      {files.map((file) => (
                        <label className="multiSelectOption" key={file.id}>
                          <input checked={selected.includes(file.id)} type="checkbox" onChange={() => toggleFile(file.id)} />
                          <span className="multiSelectCheck">
                            <SquareCheck size={15} />
                          </span>
                          <span className="multiSelectOptionBody">
                            <strong>{file.source_title || file.filename}</strong>
                            <small>
                              {file.subject} / {file.category || "未分类"} / {file.chapter || "未填章节"}
                            </small>
                          </span>
                          <span className="multiSelectBadges">
                            <span className={`badge ${file.source_authority}`}>{file.source_authority}</span>
                            {file.token_count != null && <span className="badge">{file.token_count.toLocaleString()} token</span>}
                          </span>
                        </label>
                      ))}
                      {selectedMissingFileIds.map((fileId) => (
                        <label className="multiSelectOption" key={fileId}>
                          <input checked type="checkbox" onChange={() => toggleFile(fileId)} />
                          <span className="multiSelectCheck">
                            <SquareCheck size={15} />
                          </span>
                          <span className="multiSelectOptionBody">
                            <strong>{fileId}</strong>
                            <small>已保存的素材 id</small>
                          </span>
                        </label>
                      ))}
                      {!files.length && !selectedMissingFileIds.length && (
                        <div className="multiSelectEmpty">先去素材库上传资料，或直接无资料生成。</div>
                      )}
                    </div>
                  )}
                </div>
                <div className="selectMetaLine">
                  <span>已选 {selected.length} 个素材</span>
                  <span>{selectedTokens.toLocaleString()} token</span>
                  <span>未解析文件会在提交时解析并拦截超限</span>
                </div>
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

            <div className="layoutPromptBox">
              <div className="layoutPromptTop">
                <label className="checkLine">
                  <input
                    checked={useLayoutPrompt}
                    type="checkbox"
                    onChange={(event) => setUseLayoutPrompt(event.target.checked)}
                  />
                  使用 Layout_For_Xhs 排版提示词
                </label>
                <span className={layoutModes.length ? "badge high" : "badge unverified"}>
                  {layoutModes.length ? "已连接" : "未连接"}
                </span>
              </div>
              <div className="field">
                <label>排版模式</label>
                <select
                  disabled={!useLayoutPrompt || !layoutModes.length}
                  value={form.layout_mode_id}
                  onChange={(event) => {
                    setForm({ ...form, layout_mode_id: event.target.value });
                    setLayoutTemplate(null);
                    setPromptPreview("");
                  }}
                >
                  {!layoutModes.length && <option value={form.layout_mode_id}>请先启动 Layout_For_Xhs</option>}
                  {layoutModes.map((layoutMode) => (
                    <option key={layoutMode.id} value={layoutMode.id}>
                      {layoutMode.name} · {layoutMode.title}
                    </option>
                  ))}
                </select>
                {activeLayoutMode && <p className="muted">{activeLayoutMode.summary}</p>}
              </div>
              <div className="buttonRow">
                <button
                  className="button"
                  disabled={!useLayoutPrompt || layoutLoading}
                  type="button"
                  onClick={() => loadLayoutTemplate()}
                >
                  <FileText size={16} />
                  拉取模板
                </button>
                <button
                  className="button"
                  disabled={!useLayoutPrompt || promptBuilding}
                  type="button"
                  onClick={() => buildLayoutPrompt({ refresh: true })}
                >
                  <RefreshCw size={16} />
                  拼接预览
                </button>
                <button
                  className="button"
                  disabled={!promptPreview && !useLayoutPrompt}
                  type="button"
                  onClick={copyPrompt}
                >
                  <Clipboard size={16} />
                  复制提示词
                </button>
                <a className="button" href={LAYOUT_API_BASE} rel="noreferrer" target="_blank">
                  <ExternalLink size={16} />
                  打开排版
                </a>
              </div>
              {layoutMessage && <p className="muted">{layoutMessage}</p>}
              {promptPreview && (
                <details className="promptPreview" open>
                  <summary>完整提示词预览</summary>
                  <pre>{promptPreview}</pre>
                </details>
              )}
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
                  {job.result && (
                    <button
                      className="button"
                      disabled={publishingLayout || !form.layout_mode_id}
                      type="button"
                      onClick={publishToLayout}
                    >
                      <Send size={16} />
                      发送排版
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
                {job.error && (
                  <div className="errorPanel">
                    <strong>{job.status === "failed" ? "失败原因" : "提示"}</strong>
                    <span>{job.error}</span>
                  </div>
                )}
                {job.result && (
                  <pre className="markdown" ref={markdownRef}>
                    {job.result.raw_markdown}
                  </pre>
                )}
                {job.result && !job.review && job.status !== "reviewing" && (
                  <div className="empty">尚未内容审查。</div>
                )}
                {job.status === "reviewing" && <div className="empty">正在内容审查...</div>}
                {job.review && (
                  <ReviewActionList
                    job={job}
                    markdownRef={markdownRef}
                    onJobChange={applyJob}
                    onMessage={setMessage}
                  />
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

function parseDatasetIds(value: string) {
  return value
    .split(/[,\s，]+/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function composeLayoutPrompt(template: string, sourceContent: string) {
  const content = sourceContent.trim() || "本次未提供原始资料，请生成可复核的结构初稿。";
  return template.includes("{{sourceContent}}")
    ? template.replaceAll("{{sourceContent}}", content)
    : `${template.trim()}\n\n原始资料：\n\n${content}`;
}

async function readUploadPreview(file: File) {
  if (!isTextLikeFile(file)) return "";
  const text = await file.text();
  return text.length > 80_000 ? `${text.slice(0, 80_000)}\n\n（本地预览已截断，完整文件会随生成请求提交。）` : text;
}

function isTextLikeFile(file: File) {
  const name = file.name.toLowerCase();
  return (
    file.type.startsWith("text/") ||
    file.type.includes("json") ||
    file.type.includes("xml") ||
    [".md", ".markdown", ".txt", ".csv", ".json"].some((suffix) => name.endsWith(suffix))
  );
}

function buildGenerationOptions(pages: string, layoutPrompt: string, layoutMode: LayoutMode | null) {
  return {
    pages: Number(pages || 10),
    layout_prompt: layoutPrompt || null,
    layout_mode_id: layoutMode?.id || null,
    layout_mode_name: layoutMode?.name || null,
    layout_render_mode: layoutMode?.renderMode || null,
    layout_template_version: layoutMode?.templateVersion || null,
  };
}
