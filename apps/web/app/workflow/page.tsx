"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import {
  CalendarDays,
  CheckCircle2,
  Download,
  FileText,
  History,
  Pencil,
  RefreshCw,
  Search,
  ShieldCheck,
  Trash2,
  Wand2,
} from "lucide-react";
import {
  API_BASE,
  apiFetch,
  contentTypeLabels,
  ContentType,
  LibraryFile,
  ReviewMode,
  SubjectConfig,
  SystemConfig,
  WorkflowEvent,
  WorkflowGenerateResponse,
  workflowPriorityLabels,
  WorkflowPriority,
  workflowReviewStatusLabels,
  WorkflowTopic,
  WorkflowTopicCreate,
  WorkflowTopicStatus,
  workflowStatusLabels,
} from "../../lib/api";

const statusOrder: WorkflowTopicStatus[] = [
  "idea",
  "planned",
  "drafting",
  "generated",
  "reviewing",
  "needs_changes",
  "awaiting_confirm",
  "approved",
  "exported",
  "published",
  "archived",
];
const priorityOrder: WorkflowPriority[] = ["low", "medium", "high", "urgent"];
const contentTypes = Object.keys(contentTypeLabels) as ContentType[];
const reviewMode: ReviewMode = "hybrid";

type TopicForm = {
  title: string;
  brief: string;
  subject: string;
  category: string;
  chapter: string;
  content_type: ContentType;
  owner: string;
  status: WorkflowTopicStatus;
  priority: WorkflowPriority;
  scheduled_date: string;
  due_date: string;
  publish_channel: string;
  content_goal: string;
  audience: string;
  material_file_ids: string[];
  ragflow_dataset_ids: string;
};

const emptyForm: TopicForm = {
  title: "",
  brief: "",
  subject: "",
  category: "",
  chapter: "",
  content_type: "tri_color",
  owner: "",
  status: "idea",
  priority: "medium",
  scheduled_date: "",
  due_date: "",
  publish_channel: "xiaohongshu",
  content_goal: "",
  audience: "",
  material_file_ids: [],
  ragflow_dataset_ids: "",
};

export default function WorkflowPage() {
  const [topics, setTopics] = useState<WorkflowTopic[]>([]);
  const [selected, setSelected] = useState<WorkflowTopic | null>(null);
  const [events, setEvents] = useState<WorkflowEvent[]>([]);
  const [files, setFiles] = useState<LibraryFile[]>([]);
  const [subjects, setSubjects] = useState<SubjectConfig[]>([]);
  const [form, setForm] = useState<TopicForm>(emptyForm);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState<WorkflowTopicStatus | "all">("all");
  const [search, setSearch] = useState("");
  const [message, setMessage] = useState("");
  const [saving, setSaving] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);

  async function loadTopics() {
    const params = new URLSearchParams();
    if (statusFilter !== "all") params.set("status", statusFilter);
    if (search.trim()) params.set("search", search.trim());
    const suffix = params.toString() ? `?${params.toString()}` : "";
    const data = await apiFetch<WorkflowTopic[]>(`/api/workflow/topics${suffix}`);
    setTopics(data);
    setSelected((current) => {
      if (current && data.some((topic) => topic.id === current.id)) {
        return data.find((topic) => topic.id === current.id) || current;
      }
      return data[0] || null;
    });
  }

  async function loadFiles() {
    setFiles(await apiFetch<LibraryFile[]>("/api/library/files"));
  }

  async function loadSubjects() {
    const config = await apiFetch<SystemConfig>("/api/system/config");
    setSubjects(config.subjects);
    setForm((current) => normalizeFormSubject(current, config.subjects));
  }

  async function loadEvents(topicId: string) {
    setEvents(await apiFetch<WorkflowEvent[]>(`/api/workflow/topics/${topicId}/events`));
  }

  useEffect(() => {
    loadSubjects().catch((error) => setMessage(error.message));
    loadFiles().catch((error) => setMessage(error.message));
  }, []);

  useEffect(() => {
    loadTopics().catch((error) => setMessage(error.message));
  }, [statusFilter]);

  useEffect(() => {
    if (selected) {
      loadEvents(selected.id).catch((error) => setMessage(error.message));
    } else {
      setEvents([]);
    }
  }, [selected?.id]);

  const activeSubject = useMemo(
    () => subjects.find((subject) => subject.name === form.subject) || null,
    [form.subject, subjects]
  );
  const selectedFiles = useMemo(
    () => files.filter((file) => form.material_file_ids.includes(file.id)),
    [files, form.material_file_ids]
  );
  const owners = useMemo(() => {
    const names = topics.map((topic) => topic.owner).filter(Boolean) as string[];
    return Array.from(new Set(names));
  }, [topics]);
  const scheduledTopics = useMemo(
    () =>
      topics
        .filter((topic) => topic.scheduled_date)
        .slice()
        .sort((a, b) => String(a.scheduled_date).localeCompare(String(b.scheduled_date))),
    [topics]
  );
  const boardColumns = useMemo(
    () =>
      [
        { key: "idea", title: "选题库" },
        { key: "planned", title: "内容日历" },
        { key: "generated", title: "待审查" },
        { key: "needs_changes", title: "需修改" },
        { key: "awaiting_confirm", title: "待确认" },
        { key: "approved", title: "可导出" },
      ] as Array<{ key: WorkflowTopicStatus; title: string }>,
    []
  );

  function resetForm() {
    setEditingId(null);
    setForm(normalizeFormSubject(emptyForm, subjects));
  }

  function editTopic(topic: WorkflowTopic) {
    setEditingId(topic.id);
    setForm({
      title: topic.title,
      brief: topic.brief || "",
      subject: topic.subject,
      category: topic.category || "",
      chapter: topic.chapter || "",
      content_type: topic.content_type,
      owner: topic.owner || "",
      status: topic.status,
      priority: topic.priority,
      scheduled_date: topic.scheduled_date || "",
      due_date: topic.due_date || "",
      publish_channel: topic.publish_channel,
      content_goal: topic.content_goal || "",
      audience: topic.audience || "",
      material_file_ids: topic.material_file_ids,
      ragflow_dataset_ids: topic.ragflow_dataset_ids.join(", "),
    });
    setSelected(topic);
  }

  async function saveTopic(event: FormEvent) {
    event.preventDefault();
    if (!form.title.trim()) {
      setMessage("请先填写选题标题。");
      return;
    }
    if (!form.subject) {
      setMessage("请先在设置页添加学科。");
      return;
    }
    setSaving(true);
    setMessage("");
    try {
      const payload = formToPayload(form);
      const topic = editingId
        ? await apiFetch<WorkflowTopic>(`/api/workflow/topics/${editingId}`, {
            method: "PATCH",
            body: JSON.stringify({ ...payload, actor: form.owner || null, note: "更新选题信息" }),
          })
        : await apiFetch<WorkflowTopic>("/api/workflow/topics", {
            method: "POST",
            body: JSON.stringify(payload),
          });
      setSelected(topic);
      setMessage(editingId ? "选题已更新。" : "选题已入库。");
      resetForm();
      await loadTopics();
      await loadEvents(topic.id);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "保存失败");
    } finally {
      setSaving(false);
    }
  }

  async function patchTopic(topic: WorkflowTopic, patch: Record<string, unknown>, note: string) {
    setBusyId(topic.id);
    setMessage("");
    try {
      const updated = await apiFetch<WorkflowTopic>(`/api/workflow/topics/${topic.id}`, {
        method: "PATCH",
        body: JSON.stringify({ ...patch, actor: topic.owner || null, note }),
      });
      applyTopic(updated);
      await loadEvents(updated.id);
      setMessage(note);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "操作失败");
    } finally {
      setBusyId(null);
    }
  }

  async function startGeneration(topic: WorkflowTopic) {
    setBusyId(topic.id);
    setMessage("");
    try {
      const response = await apiFetch<WorkflowGenerateResponse>(`/api/workflow/topics/${topic.id}/generate`, {
        method: "POST",
        body: JSON.stringify({
          mode: topic.ragflow_dataset_ids.length ? "ragflow" : "direct",
          pages: 10,
        }),
      });
      applyTopic(response.topic);
      await loadEvents(topic.id);
      await loadTopics();
      setMessage(`生成任务已创建：${response.job_id}`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "发起生成失败");
    } finally {
      setBusyId(null);
    }
  }

  async function runReview(topic: WorkflowTopic) {
    setBusyId(topic.id);
    setMessage("");
    try {
      const updated = await apiFetch<WorkflowTopic>(`/api/workflow/topics/${topic.id}/review`, {
        method: "POST",
        body: JSON.stringify({ mode: reviewMode }),
      });
      applyTopic(updated);
      await loadEvents(topic.id);
      await loadTopics();
      setMessage("内容审查已入队。");
      pollTopicReview(topic.id);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "内容审查失败");
    } finally {
      setBusyId(null);
    }
  }

  async function pollTopicReview(topicId: string) {
    for (let index = 0; index < 120; index += 1) {
      await new Promise((resolve) => setTimeout(resolve, 1000));
      const latest = await apiFetch<WorkflowTopic>(`/api/workflow/topics/${topicId}`).catch(() => null);
      if (!latest) return;
      applyTopic(latest);
      if (latest.status !== "reviewing") {
        await loadEvents(topicId);
        await loadTopics();
        setMessage(latest.review_status === "passed" ? "内容审查完成。" : "内容审查需要复核。");
        return;
      }
    }
    setMessage("内容审查仍在运行，请稍后刷新。");
  }

  async function confirmTopic(topic: WorkflowTopic) {
    setBusyId(topic.id);
    setMessage("");
    try {
      const updated = await apiFetch<WorkflowTopic>(`/api/workflow/topics/${topic.id}/confirm`, {
        method: "POST",
        body: JSON.stringify({ confirmed_by: topic.owner, note: "人工确认通过" }),
      });
      applyTopic(updated);
      await loadEvents(topic.id);
      await loadTopics();
      setMessage("已人工确认。");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "确认失败");
    } finally {
      setBusyId(null);
    }
  }

  async function deleteTopic(topic: WorkflowTopic) {
    setBusyId(topic.id);
    setMessage("");
    try {
      await apiFetch(`/api/workflow/topics/${topic.id}`, { method: "DELETE" });
      if (selected?.id === topic.id) setSelected(null);
      await loadTopics();
      setMessage("选题已删除。");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "删除失败");
    } finally {
      setBusyId(null);
    }
  }

  function applyTopic(topic: WorkflowTopic) {
    setTopics((current) => current.map((item) => (item.id === topic.id ? topic : item)));
    setSelected((current) => (current?.id === topic.id ? topic : current));
  }

  function toggleMaterial(fileId: string) {
    setForm((current) => ({
      ...current,
      material_file_ids: current.material_file_ids.includes(fileId)
        ? current.material_file_ids.filter((item) => item !== fileId)
        : [...current.material_file_ids, fileId],
    }));
  }

  return (
    <>
      <header className="pageHeader">
        <div>
          <h1>内容工作流</h1>
          <p>选题库、素材引用、生成、审查、人工确认、导出发布包和历史复盘都在这里串起来。</p>
        </div>
        <div className="buttonRow">
          <button className="button" type="button" onClick={() => loadTopics().catch((error) => setMessage(error.message))}>
            <RefreshCw size={17} />
            刷新
          </button>
          <button className="button" type="button" onClick={resetForm}>
            <Pencil size={17} />
            新选题
          </button>
        </div>
      </header>

      <section className="workflowGrid">
        <form className="panel" onSubmit={saveTopic}>
          <div className="panelHeader">
            <h2>{editingId ? "编辑选题" : "选题入库"}</h2>
            <p>补齐责任人、排期、素材和内容目标后，可直接进入生成链路。</p>
          </div>
          <div className="panelBody formGrid">
            <div className="field">
              <label>标题</label>
              <input value={form.title} onChange={(event) => setForm({ ...form, title: event.target.value })} />
            </div>
            <div className="field">
              <label>选题说明</label>
              <textarea value={form.brief} onChange={(event) => setForm({ ...form, brief: event.target.value })} />
            </div>
            <div className="row">
              <div className="field">
                <label>学科</label>
                <select
                  value={form.subject}
                  onChange={(event) => setForm(selectSubject(form, subjects, event.target.value))}
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
                <select value={form.category} onChange={(event) => setForm({ ...form, category: event.target.value })}>
                  {activeSubject?.categories.map((category) => (
                    <option key={category} value={category}>
                      {category}
                    </option>
                  ))}
                  {!activeSubject?.categories.length && <option value="">未分类</option>}
                </select>
              </div>
            </div>
            <div className="row">
              <div className="field">
                <label>章节</label>
                <input value={form.chapter} onChange={(event) => setForm({ ...form, chapter: event.target.value })} />
              </div>
              <div className="field">
                <label>内容类型</label>
                <select
                  value={form.content_type}
                  onChange={(event) => setForm({ ...form, content_type: event.target.value as ContentType })}
                >
                  {contentTypes.map((type) => (
                    <option key={type} value={type}>
                      {contentTypeLabels[type]}
                    </option>
                  ))}
                </select>
              </div>
            </div>
            <div className="row">
              <div className="field">
                <label>责任人</label>
                <input
                  list="workflowOwners"
                  value={form.owner}
                  onChange={(event) => setForm({ ...form, owner: event.target.value })}
                />
                <datalist id="workflowOwners">
                  {owners.map((owner) => (
                    <option key={owner} value={owner} />
                  ))}
                </datalist>
              </div>
              <div className="field">
                <label>优先级</label>
                <select
                  value={form.priority}
                  onChange={(event) => setForm({ ...form, priority: event.target.value as WorkflowPriority })}
                >
                  {priorityOrder.map((priority) => (
                    <option key={priority} value={priority}>
                      {workflowPriorityLabels[priority]}
                    </option>
                  ))}
                </select>
              </div>
            </div>
            <div className="row">
              <div className="field">
                <label>计划日期</label>
                <input
                  type="date"
                  value={form.scheduled_date}
                  onChange={(event) => setForm({ ...form, scheduled_date: event.target.value })}
                />
              </div>
              <div className="field">
                <label>截止日期</label>
                <input
                  type="date"
                  value={form.due_date}
                  onChange={(event) => setForm({ ...form, due_date: event.target.value })}
                />
              </div>
            </div>
            <div className="row">
              <div className="field">
                <label>状态</label>
                <select
                  value={form.status}
                  onChange={(event) => setForm({ ...form, status: event.target.value as WorkflowTopicStatus })}
                >
                  {statusOrder.map((status) => (
                    <option key={status} value={status}>
                      {workflowStatusLabels[status]}
                    </option>
                  ))}
                </select>
              </div>
              <div className="field">
                <label>发布渠道</label>
                <input
                  value={form.publish_channel}
                  onChange={(event) => setForm({ ...form, publish_channel: event.target.value })}
                />
              </div>
            </div>
            <div className="field">
              <label>内容目标</label>
              <input
                value={form.content_goal}
                onChange={(event) => setForm({ ...form, content_goal: event.target.value })}
              />
            </div>
            <div className="field">
              <label>目标读者</label>
              <input value={form.audience} onChange={(event) => setForm({ ...form, audience: event.target.value })} />
            </div>
            <div className="field">
              <label>素材引用</label>
              <div className="materialPicker">
                {files.map((file) => (
                  <label className="materialOption" key={file.id}>
                    <input
                      checked={form.material_file_ids.includes(file.id)}
                      type="checkbox"
                      onChange={() => toggleMaterial(file.id)}
                    />
                    <span>
                      <strong>{file.source_title || file.filename}</strong>
                      <small>
                        {file.subject} / {file.category || "未分类"} / {file.chapter || "未填章节"}
                      </small>
                    </span>
                  </label>
                ))}
                {!files.length && <div className="empty compact">素材库暂无资料。</div>}
              </div>
              <p className="muted">已选 {selectedFiles.length} 个素材。</p>
            </div>
            <div className="field">
              <label>RAGFlow Dataset IDs</label>
              <input
                value={form.ragflow_dataset_ids}
                onChange={(event) => setForm({ ...form, ragflow_dataset_ids: event.target.value })}
              />
            </div>
            <div className="buttonRow">
              <button className="button primary" disabled={saving} type="submit">
                <CheckCircle2 size={17} />
                {editingId ? "保存修改" : "加入选题库"}
              </button>
              {editingId && (
                <button className="button" type="button" onClick={resetForm}>
                  取消编辑
                </button>
              )}
            </div>
            {message && <p className="muted">{message}</p>}
          </div>
        </form>

        <div className="workflowMain">
          <section className="panel">
            <div className="panelHeader">
              <div className="panelHeaderActions">
                <div>
                  <h2>选题看板</h2>
                  <p>{topics.length} 个选题，按当前链路阶段聚合。</p>
                </div>
                <div className="workflowFilters">
                  <div className="field">
                    <label>状态</label>
                    <select
                      value={statusFilter}
                      onChange={(event) => setStatusFilter(event.target.value as WorkflowTopicStatus | "all")}
                    >
                      <option value="all">全部</option>
                      {statusOrder.map((status) => (
                        <option key={status} value={status}>
                          {workflowStatusLabels[status]}
                        </option>
                      ))}
                    </select>
                  </div>
                  <form
                    className="searchBox"
                    onSubmit={(event) => {
                      event.preventDefault();
                      loadTopics().catch((error) => setMessage(error.message));
                    }}
                  >
                    <Search size={16} />
                    <input value={search} onChange={(event) => setSearch(event.target.value)} />
                  </form>
                </div>
              </div>
            </div>
            <div className="panelBody">
              <div className="workflowBoard">
                {boardColumns.map((column) => {
                  const columnTopics = topics.filter((topic) => topic.status === column.key);
                  return (
                    <div className="workflowColumn" key={column.key}>
                      <div className="workflowColumnHeader">
                        <strong>{column.title}</strong>
                        <span>{columnTopics.length}</span>
                      </div>
                      <div className="workflowCards">
                        {columnTopics.map((topic) => (
                          <button
                            className={selected?.id === topic.id ? "workflowCard active" : "workflowCard"}
                            key={topic.id}
                            type="button"
                            onClick={() => setSelected(topic)}
                          >
                            <span className={`badge priority ${topic.priority}`}>{workflowPriorityLabels[topic.priority]}</span>
                            <strong>{topic.title}</strong>
                            <small>
                              {topic.owner || "未分配"} / {topic.scheduled_date || "未排期"}
                            </small>
                            <small>{contentTypeLabels[topic.content_type]}</small>
                          </button>
                        ))}
                        {!columnTopics.length && <div className="workflowColumnEmpty">暂无</div>}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          </section>

          <section className="workflowLowerGrid">
            <div className="panel">
              <div className="panelHeader">
                <h2>
                  <CalendarDays size={18} />
                  内容日历
                </h2>
                <p>按计划日期排序，方便排产和催办。</p>
              </div>
              <div className="panelBody">
                <div className="calendarList">
                  {scheduledTopics.map((topic) => (
                    <button className="calendarItem" key={topic.id} type="button" onClick={() => setSelected(topic)}>
                      <span>{formatMonthDay(topic.scheduled_date)}</span>
                      <strong>{topic.title}</strong>
                      <small>
                        {workflowStatusLabels[topic.status]} / {topic.owner || "未分配"}
                      </small>
                    </button>
                  ))}
                  {!scheduledTopics.length && <div className="empty compact">还没有排期。</div>}
                </div>
              </div>
            </div>

            <aside className="panel">
              <div className="panelHeader">
                <h2>任务详情</h2>
                <p>{selected ? selected.id : "选择一个选题查看链路状态"}</p>
              </div>
              <div className="panelBody formGrid">
                {!selected && <div className="empty compact">未选择选题。</div>}
                {selected && (
                  <>
                    <div className="workflowDetailTitle">
                      <div>
                        <strong>{selected.title}</strong>
                        <span>{selected.brief || "暂无说明"}</span>
                      </div>
                      <span className={`badge ${selected.status}`}>{workflowStatusLabels[selected.status]}</span>
                    </div>
                    <div className="workflowMetaGrid">
                      <span>责任人</span>
                      <strong>{selected.owner || "未分配"}</strong>
                      <span>审查</span>
                      <strong>{workflowReviewStatusLabels[selected.review_status]}</strong>
                      <span>排期</span>
                      <strong>{selected.scheduled_date || "未排期"}</strong>
                      <span>生成任务</span>
                      <strong>{selected.generation_job_id || "未生成"}</strong>
                    </div>
                    <div className="buttonRow">
                      <button className="button" type="button" onClick={() => editTopic(selected)}>
                        <Pencil size={16} />
                        编辑
                      </button>
                      <button
                        className="button"
                        disabled={busyId === selected.id}
                        type="button"
                        onClick={() => patchTopic(selected, { status: "planned" }, "已加入内容日历")}
                      >
                        <CalendarDays size={16} />
                        排期
                      </button>
                      <button
                        className="button"
                        disabled={busyId === selected.id}
                        type="button"
                        onClick={() => startGeneration(selected)}
                      >
                        <Wand2 size={16} />
                        生成
                      </button>
                      <button
                        className="button"
                        disabled={busyId === selected.id || !selected.generation_job_id}
                        type="button"
                        onClick={() => runReview(selected)}
                      >
                        <ShieldCheck size={16} />
                        审查
                      </button>
                      <button
                        className="button"
                        disabled={busyId === selected.id}
                        type="button"
                        onClick={() => confirmTopic(selected)}
                      >
                        <CheckCircle2 size={16} />
                        确认
                      </button>
                      <a
                        className={selected.generation_job_id ? "button" : "button disabled"}
                        href={
                          selected.generation_job_id
                            ? `${API_BASE}/api/workflow/topics/${selected.id}/export`
                            : undefined
                        }
                        onClick={(event) => {
                          if (!selected.generation_job_id) event.preventDefault();
                        }}
                      >
                        <Download size={16} />
                        导出
                      </a>
                      <button
                        className="button danger"
                        disabled={busyId === selected.id}
                        type="button"
                        onClick={() => deleteTopic(selected)}
                      >
                        <Trash2 size={16} />
                      </button>
                    </div>
                    <div className="materialSummary">
                      <strong>
                        <FileText size={16} />
                        素材引用
                      </strong>
                      {(selected.material_file_ids || []).map((fileId) => {
                        const file = files.find((item) => item.id === fileId);
                        return <span key={fileId}>{file?.source_title || file?.filename || fileId}</span>;
                      })}
                      {!(selected.material_file_ids || []).length && !(selected.ragflow_dataset_ids || []).length && <span>未绑定素材</span>}
                      {(selected.ragflow_dataset_ids || []).map((datasetId) => (
                        <span key={datasetId}>RAGFlow: {datasetId}</span>
                      ))}
                    </div>
                    <div className="versionList">
                      <strong>
                        <History size={16} />
                        版本记录
                      </strong>
                      {events.map((event) => (
                        <div className="versionItem" key={event.id}>
                          <span>v{event.version}</span>
                          <div>
                            <strong>{event.event_type}</strong>
                            <small>
                              {new Date(event.created_at).toLocaleString()} {event.actor ? `/ ${event.actor}` : ""}
                            </small>
                            {event.note && <p>{event.note}</p>}
                          </div>
                        </div>
                      ))}
                    </div>
                  </>
                )}
              </div>
            </aside>
          </section>
        </div>
      </section>
    </>
  );
}

function normalizeFormSubject(form: TopicForm, subjects: SubjectConfig[]): TopicForm {
  const subject = findSubject(subjects, form.subject) || subjects[0];
  if (!subject) return { ...form, subject: "", category: "" };
  return {
    ...form,
    subject: subject.name,
    category: subject.categories.includes(form.category) ? form.category : subject.categories[0] || "",
  };
}

function selectSubject(form: TopicForm, subjects: SubjectConfig[], name: string): TopicForm {
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

function formToPayload(form: TopicForm): WorkflowTopicCreate {
  return {
    title: form.title.trim(),
    brief: optionalText(form.brief),
    subject: form.subject,
    category: optionalText(form.category),
    chapter: optionalText(form.chapter),
    content_type: form.content_type,
    owner: optionalText(form.owner),
    status: form.status,
    priority: form.priority,
    scheduled_date: optionalText(form.scheduled_date),
    due_date: optionalText(form.due_date),
    publish_channel: form.publish_channel || "xiaohongshu",
    content_goal: optionalText(form.content_goal),
    audience: optionalText(form.audience),
    material_file_ids: form.material_file_ids,
    ragflow_dataset_ids: parseIds(form.ragflow_dataset_ids),
  };
}

function optionalText(value: string) {
  const text = value.trim();
  return text || null;
}

function parseIds(value: string) {
  return value
    .split(/[,\s，]+/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function formatMonthDay(value?: string | null) {
  if (!value) return "未排期";
  const date = new Date(`${value}T00:00:00`);
  return `${date.getMonth() + 1}/${date.getDate()}`;
}
