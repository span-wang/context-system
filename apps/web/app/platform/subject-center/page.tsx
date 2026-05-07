"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import {
  apiFetch,
  ChapterResponse,
  KnowledgePointResponse,
  SubjectCategoryResponse,
  SubjectResponse,
  TextbookResponse,
} from "../../../lib/pro-api";
import { LoadState } from "../../../components/shared/LoadState";
import { StatusBadge } from "../../../components/shared/StatusBadge";
import {
  allRejected,
  firstRejectedReason,
  summarizeRejectedRequests,
  toErrorMessage,
  useLatestRequestGate,
} from "../../../lib/request-guard";

type ManageTab = "overview" | "categories" | "textbooks" | "chapters" | "points";
type EditableType = "subject" | "category" | "textbook" | "chapter" | "point";
type EditableItem =
  | SubjectResponse
  | SubjectCategoryResponse
  | TextbookResponse
  | ChapterResponse
  | KnowledgePointResponse
  | null;

const defaultSubjectForm = { code: "", name: "", status: "active" };
const defaultCategoryForm = { name: "", sort_order: "0" };
const defaultTextbookForm = {
  source_title: "",
  filename: "",
  category_id: "",
  year: "",
  region: "",
  source_version: "",
  tags: "",
  parse_status: "metadata",
  token_count: "",
};
const defaultChapterForm = { name: "", parent_id: "", path: "", level: "", sort_order: "0" };
const defaultPointForm = {
  name: "",
  category_id: "",
  chapter_id: "",
  parent_id: "",
  path: "",
  level: "",
  description: "",
  keywords: "",
  status: "active",
  sort_order: "0",
};

export default function SubjectCenterPage() {
  const [subjects, setSubjects] = useState<SubjectResponse[]>([]);
  const [categories, setCategories] = useState<SubjectCategoryResponse[]>([]);
  const [textbooks, setTextbooks] = useState<TextbookResponse[]>([]);
  const [chapters, setChapters] = useState<ChapterResponse[]>([]);
  const [points, setPoints] = useState<KnowledgePointResponse[]>([]);
  const [selectedSubjectId, setSelectedSubjectId] = useState<number | null>(null);
  const [activeTab, setActiveTab] = useState<ManageTab>("overview");
  const [editing, setEditing] = useState<{ type: EditableType; item: EditableItem } | null>(null);
  const [subjectForm, setSubjectForm] = useState(defaultSubjectForm);
  const [categoryForm, setCategoryForm] = useState(defaultCategoryForm);
  const [textbookForm, setTextbookForm] = useState(defaultTextbookForm);
  const [chapterForm, setChapterForm] = useState(defaultChapterForm);
  const [pointForm, setPointForm] = useState(defaultPointForm);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [loadWarning, setLoadWarning] = useState("");
  const [actionMessage, setActionMessage] = useState("");
  const requestGate = useLatestRequestGate();

  async function loadAll(preferredSubjectId?: number | null) {
    const requestId = requestGate.begin();
    setLoading(true);
    setError("");
    setLoadWarning("");
    try {
      const [nextSubjects, nextCategories, nextTextbooks, nextChapters, nextPoints] = await Promise.allSettled([
        apiFetch<SubjectResponse[]>("/api/knowledge/subjects"),
        apiFetch<SubjectCategoryResponse[]>("/api/knowledge/categories"),
        apiFetch<TextbookResponse[]>("/api/knowledge/textbooks"),
        apiFetch<ChapterResponse[]>("/api/knowledge/chapters"),
        apiFetch<KnowledgePointResponse[]>("/api/knowledge/points"),
      ]);

      if (!requestGate.isCurrent(requestId)) return;

      const results = [nextSubjects, nextCategories, nextTextbooks, nextChapters, nextPoints];
      if (allRejected(results)) {
        throw firstRejectedReason(results) || new Error("No subject-center requests succeeded.");
      }

      const subjectList = nextSubjects.status === "fulfilled" ? nextSubjects.value : [];
      setSubjects(subjectList);
      setCategories(nextCategories.status === "fulfilled" ? nextCategories.value : []);
      setTextbooks(nextTextbooks.status === "fulfilled" ? nextTextbooks.value : []);
      setChapters(nextChapters.status === "fulfilled" ? nextChapters.value : []);
      setPoints(nextPoints.status === "fulfilled" ? nextPoints.value : []);
      setSelectedSubjectId((current) => {
        const preferred = preferredSubjectId ?? current;
        if (preferred && subjectList.some((subject) => subject.id === preferred)) return preferred;
        return subjectList[0]?.id || null;
      });
      setLoadWarning(
        summarizeRejectedRequests([
          { label: "学科", result: nextSubjects },
          { label: "类目", result: nextCategories },
          { label: "教材", result: nextTextbooks },
          { label: "章节", result: nextChapters },
          { label: "知识点", result: nextPoints },
        ]),
      );
    } catch (err) {
      if (!requestGate.isCurrent(requestId)) return;
      setError(toErrorMessage(err, "加载学科中心失败"));
    } finally {
      if (requestGate.isCurrent(requestId)) setLoading(false);
    }
  }

  useEffect(() => {
    loadAll();
  }, []);

  const selectedSubject = useMemo(
    () => subjects.find((subject) => subject.id === selectedSubjectId) || null,
    [subjects, selectedSubjectId],
  );

  const scopedCategories = useMemo(
    () => categories.filter((category) => category.subject_id === selectedSubjectId),
    [categories, selectedSubjectId],
  );
  const scopedTextbooks = useMemo(
    () => textbooks.filter((textbook) => textbook.subject_id === selectedSubjectId),
    [textbooks, selectedSubjectId],
  );
  const scopedChapters = useMemo(
    () => chapters.filter((chapter) => chapter.subject_id === selectedSubjectId),
    [chapters, selectedSubjectId],
  );
  const scopedPoints = useMemo(
    () => points.filter((point) => point.subject_id === selectedSubjectId),
    [points, selectedSubjectId],
  );

  const pointCountByChapter = useMemo(() => {
    const map = new Map<number, number>();
    for (const point of scopedPoints) {
      if (point.chapter_id) {
        map.set(point.chapter_id, (map.get(point.chapter_id) || 0) + 1);
      }
    }
    return map;
  }, [scopedPoints]);

  const pointCountByCategory = useMemo(() => {
    const map = new Map<number, number>();
    for (const point of scopedPoints) {
      if (point.category_id) {
        map.set(point.category_id, (map.get(point.category_id) || 0) + 1);
      }
    }
    return map;
  }, [scopedPoints]);

  const unmappedPoints = scopedPoints.filter((point) => !point.chapter_id).length;
  const mappedChapters = scopedChapters.filter((chapter) => (pointCountByChapter.get(chapter.id) || 0) > 0).length;

  function pickSubject(subjectId: number) {
    setSelectedSubjectId(subjectId);
    setEditing(null);
    setActionMessage("");
  }

  function beginCreate(type: EditableType) {
    setActionMessage("");
    setEditing({ type, item: null });
    if (type === "subject") setSubjectForm(defaultSubjectForm);
    if (type === "category") setCategoryForm(defaultCategoryForm);
    if (type === "textbook") setTextbookForm(defaultTextbookForm);
    if (type === "chapter") setChapterForm(defaultChapterForm);
    if (type === "point") setPointForm(defaultPointForm);
  }

  function beginEdit(type: EditableType, item: EditableItem) {
    setActionMessage("");
    setEditing({ type, item });
    if (type === "subject") {
      const subject = item as SubjectResponse;
      setSubjectForm({ code: subject.code, name: subject.name, status: subject.status });
    }
    if (type === "category") {
      const category = item as SubjectCategoryResponse;
      setCategoryForm({ name: category.name, sort_order: String(category.sort_order) });
    }
    if (type === "textbook") {
      const textbook = item as TextbookResponse;
      setTextbookForm({
        source_title: textbook.source_title,
        filename: textbook.filename,
        category_id: textbook.category_id ? String(textbook.category_id) : "",
        year: textbook.year ? String(textbook.year) : "",
        region: textbook.region || "",
        source_version: textbook.source_version || "",
        tags: userTags(textbook.tags_json).join(", "),
        parse_status: textbook.parse_status,
        token_count: textbook.token_count ? String(textbook.token_count) : "",
      });
    }
    if (type === "chapter") {
      const chapter = item as ChapterResponse;
      setChapterForm({
        name: chapter.name,
        parent_id: chapter.parent_id ? String(chapter.parent_id) : "",
        path: chapter.path,
        level: String(chapter.level),
        sort_order: String(chapter.sort_order),
      });
    }
    if (type === "point") {
      const point = item as KnowledgePointResponse;
      setPointForm({
        name: point.name,
        category_id: point.category_id ? String(point.category_id) : "",
        chapter_id: point.chapter_id ? String(point.chapter_id) : "",
        parent_id: point.parent_id ? String(point.parent_id) : "",
        path: point.path,
        level: String(point.level),
        description: point.description || "",
        keywords: (point.keywords_json || []).join(", "),
        status: point.status,
        sort_order: String(point.sort_order),
      });
    }
  }

  async function submitSubject(event: FormEvent) {
    event.preventDefault();
    const subject = editing?.item as SubjectResponse | null;
    await saveEntity(
      subject ? `/api/knowledge/subjects/${subject.id}` : "/api/knowledge/subjects",
      subject ? "PATCH" : "POST",
      {
        code: subjectForm.code.trim(),
        name: subjectForm.name.trim(),
        status: subjectForm.status.trim() || "active",
      },
      "学科已保存",
      subject?.id,
    );
  }

  async function submitCategory(event: FormEvent) {
    event.preventDefault();
    if (!selectedSubjectId) return setError("请先选择学科");
    const category = editing?.item as SubjectCategoryResponse | null;
    await saveEntity(
      category ? `/api/knowledge/categories/${category.id}` : "/api/knowledge/categories",
      category ? "PATCH" : "POST",
      {
        subject_id: selectedSubjectId,
        name: categoryForm.name.trim(),
        sort_order: toNumber(categoryForm.sort_order),
      },
      "类目已保存",
    );
  }

  async function submitTextbook(event: FormEvent) {
    event.preventDefault();
    if (!selectedSubjectId) return setError("请先选择学科");
    const textbook = editing?.item as TextbookResponse | null;
    await saveEntity(
      textbook ? `/api/knowledge/textbooks/${textbook.id}` : "/api/knowledge/textbooks",
      textbook ? "PATCH" : "POST",
      {
        subject_id: selectedSubjectId,
        category_id: toNullableNumber(textbookForm.category_id),
        source_title: textbookForm.source_title.trim(),
        filename: textbookForm.filename.trim() || null,
        year: toNullableNumber(textbookForm.year),
        region: textbookForm.region.trim() || null,
        source_version: textbookForm.source_version.trim() || null,
        tags_json: splitList(textbookForm.tags),
        parse_status: textbookForm.parse_status.trim() || "metadata",
        token_count: toNullableNumber(textbookForm.token_count),
      },
      "教材已保存",
    );
  }

  async function submitChapter(event: FormEvent) {
    event.preventDefault();
    if (!selectedSubjectId) return setError("请先选择学科");
    const chapter = editing?.item as ChapterResponse | null;
    await saveEntity(
      chapter ? `/api/knowledge/chapters/${chapter.id}` : "/api/knowledge/chapters",
      chapter ? "PATCH" : "POST",
      {
        subject_id: selectedSubjectId,
        parent_id: toNullableNumber(chapterForm.parent_id),
        name: chapterForm.name.trim(),
        level: toNullableNumber(chapterForm.level),
        path: chapterForm.path.trim() || null,
        sort_order: toNumber(chapterForm.sort_order),
      },
      "章节已保存",
    );
  }

  async function submitPoint(event: FormEvent) {
    event.preventDefault();
    if (!selectedSubjectId) return setError("请先选择学科");
    const point = editing?.item as KnowledgePointResponse | null;
    await saveEntity(
      point ? `/api/knowledge/points/${point.id}` : "/api/knowledge/points",
      point ? "PATCH" : "POST",
      {
        subject_id: selectedSubjectId,
        category_id: toNullableNumber(pointForm.category_id),
        chapter_id: toNullableNumber(pointForm.chapter_id),
        parent_id: toNullableNumber(pointForm.parent_id),
        name: pointForm.name.trim(),
        level: toNullableNumber(pointForm.level),
        path: pointForm.path.trim() || null,
        description: pointForm.description.trim() || null,
        keywords_json: splitList(pointForm.keywords),
        status: pointForm.status.trim() || "active",
        sort_order: toNumber(pointForm.sort_order),
      },
      "知识点已保存",
    );
  }

  async function saveEntity(path: string, method: "POST" | "PATCH", body: object, message: string, preferredSubjectId?: number) {
    setSaving(true);
    setError("");
    setActionMessage("");
    try {
      await apiFetch(path, {
        method,
        body: JSON.stringify(body),
      });
      setEditing(null);
      setActionMessage(message);
      await loadAll(preferredSubjectId ?? selectedSubjectId);
    } catch (err) {
      setError(toErrorMessage(err, "保存失败"));
    } finally {
      setSaving(false);
    }
  }

  return (
    <>
      <header className="pageHeader">
        <div>
          <h1>学科中心</h1>
          <p>统一维护学科、类目、教材、章节和知识点，后续原始题的考点映射会以这里的知识资产为准。</p>
        </div>
        <div className="buttonRow">
          <button className="button" type="button" onClick={() => beginCreate("subject")}>
            新增学科
          </button>
          <button className="button" type="button" onClick={() => loadAll(selectedSubjectId)}>
            刷新
          </button>
        </div>
      </header>

      {loadWarning && <div className="calloutBox">{loadWarning}</div>}
      {actionMessage && <div className="calloutBox">{actionMessage}</div>}

      <LoadState
        loading={loading}
        error={error}
        empty={!subjects.length && !categories.length && !chapters.length && !points.length}
        emptyLabel="暂无学科数据"
      />

      {!loading && !error && (
        <section className="subjectCenterGrid">
          <aside className="panel">
            <div className="panelHeader">
              <h2>学科</h2>
              <p>切换学科后，右侧只显示当前学科下的内容资产。</p>
            </div>
            <div className="panelBody stackList">
              {subjects.map((subject) => {
                const active = subject.id === selectedSubjectId;
                const subjectPoints = points.filter((point) => point.subject_id === subject.id).length;
                return (
                  <button
                    key={subject.id}
                    className={active ? "subjectPickButton active" : "subjectPickButton"}
                    type="button"
                    onClick={() => pickSubject(subject.id)}
                  >
                    <span>
                      <strong>{subject.name}</strong>
                      <small>{subject.code} · {subjectPoints} 个知识点</small>
                    </span>
                    <StatusBadge value={subject.status} tone={subject.status === "active" ? "good" : "info"} />
                  </button>
                );
              })}
              {!subjects.length && <div className="empty compact">请先新增一个学科</div>}
            </div>
          </aside>

          <div className="subjectCenterMain">
            <section className="statsGrid">
              <article className="statCard">
                <span>类目</span>
                <strong>{scopedCategories.length}</strong>
                <small>用于区分教材目录、试卷分类和知识点归属。</small>
              </article>
              <article className="statCard">
                <span>教材</span>
                <strong>{scopedTextbooks.length}</strong>
                <small>已登记到素材资产中的教材资料。</small>
              </article>
              <article className="statCard">
                <span>章节</span>
                <strong>{mappedChapters}/{scopedChapters.length}</strong>
                <small>已有知识点覆盖的章节 / 总章节。</small>
              </article>
              <article className="statCard">
                <span>知识点</span>
                <strong>{scopedPoints.length}</strong>
                <small>{unmappedPoints} 个知识点尚未绑定章节。</small>
              </article>
            </section>

            <section className="panel">
              <div className="panelHeader">
                <div className="panelHeaderActions">
                  <div>
                    <h2>{selectedSubject?.name || "未选择学科"}</h2>
                    <p>{selectedSubject ? `${selectedSubject.code} · ${selectedSubject.status}` : "请选择或新增学科后继续维护内容。"}</p>
                  </div>
                  {selectedSubject && (
                    <button className="button" type="button" onClick={() => beginEdit("subject", selectedSubject)}>
                      编辑学科
                    </button>
                  )}
                </div>
              </div>
              <div className="panelBody stackList">
                <div className="tabs">
                  {[
                    ["overview", "总览"],
                    ["categories", "类目"],
                    ["textbooks", "教材"],
                    ["chapters", "章节"],
                    ["points", "知识点"],
                  ].map(([value, label]) => (
                    <button
                      key={value}
                      className={activeTab === value ? "tab active" : "tab"}
                      type="button"
                      onClick={() => setActiveTab(value as ManageTab)}
                    >
                      {label}
                    </button>
                  ))}
                </div>

                {renderEditor()}
                {activeTab === "overview" && renderOverview()}
                {activeTab === "categories" && renderCategories()}
                {activeTab === "textbooks" && renderTextbooks()}
                {activeTab === "chapters" && renderChapters()}
                {activeTab === "points" && renderPoints()}
              </div>
            </section>
          </div>
        </section>
      )}
    </>
  );

  function renderEditor() {
    if (!editing) return null;
    return (
      <div className="editorPanel">
        <div className="panelHeaderActions">
          <div>
            <strong>{editorTitle(editing.type, !!editing.item)}</strong>
            <p className="muted">保存后会刷新当前学科中心数据。</p>
          </div>
          <button className="button small" type="button" onClick={() => setEditing(null)}>
            取消
          </button>
        </div>
        {editing.type === "subject" && (
          <form className="formGrid" onSubmit={submitSubject}>
            <div className="row">
              <label className="field">
                <span>编码</span>
                <input value={subjectForm.code} onChange={(event) => setSubjectForm({ ...subjectForm, code: event.target.value })} />
              </label>
              <label className="field">
                <span>名称</span>
                <input value={subjectForm.name} onChange={(event) => setSubjectForm({ ...subjectForm, name: event.target.value })} />
              </label>
            </div>
            <label className="field">
              <span>状态</span>
              <select value={subjectForm.status} onChange={(event) => setSubjectForm({ ...subjectForm, status: event.target.value })}>
                <option value="active">active</option>
                <option value="inactive">inactive</option>
              </select>
            </label>
            <SubmitButton saving={saving} />
          </form>
        )}
        {editing.type === "category" && (
          <form className="formGrid" onSubmit={submitCategory}>
            <div className="row">
              <label className="field">
                <span>类目名称</span>
                <input value={categoryForm.name} onChange={(event) => setCategoryForm({ ...categoryForm, name: event.target.value })} />
              </label>
              <label className="field">
                <span>排序</span>
                <input value={categoryForm.sort_order} onChange={(event) => setCategoryForm({ ...categoryForm, sort_order: event.target.value })} />
              </label>
            </div>
            <SubmitButton saving={saving} />
          </form>
        )}
        {editing.type === "textbook" && (
          <form className="formGrid" onSubmit={submitTextbook}>
            <div className="row">
              <label className="field">
                <span>教材名称</span>
                <input value={textbookForm.source_title} onChange={(event) => setTextbookForm({ ...textbookForm, source_title: event.target.value })} />
              </label>
              <label className="field">
                <span>文件名</span>
                <input value={textbookForm.filename} onChange={(event) => setTextbookForm({ ...textbookForm, filename: event.target.value })} />
              </label>
            </div>
            <div className="row">
              <label className="field">
                <span>类目</span>
                <select value={textbookForm.category_id} onChange={(event) => setTextbookForm({ ...textbookForm, category_id: event.target.value })}>
                  <option value="">未分类</option>
                  {scopedCategories.map((category) => (
                    <option key={category.id} value={category.id}>{category.name}</option>
                  ))}
                </select>
              </label>
              <label className="field">
                <span>版本</span>
                <input value={textbookForm.source_version} onChange={(event) => setTextbookForm({ ...textbookForm, source_version: event.target.value })} />
              </label>
            </div>
            <div className="row">
              <label className="field">
                <span>年份</span>
                <input value={textbookForm.year} onChange={(event) => setTextbookForm({ ...textbookForm, year: event.target.value })} />
              </label>
              <label className="field">
                <span>地区</span>
                <input value={textbookForm.region} onChange={(event) => setTextbookForm({ ...textbookForm, region: event.target.value })} />
              </label>
            </div>
            <div className="row">
              <label className="field">
                <span>解析状态</span>
                <input value={textbookForm.parse_status} onChange={(event) => setTextbookForm({ ...textbookForm, parse_status: event.target.value })} />
              </label>
              <label className="field">
                <span>Token</span>
                <input value={textbookForm.token_count} onChange={(event) => setTextbookForm({ ...textbookForm, token_count: event.target.value })} />
              </label>
            </div>
            <label className="field">
              <span>标签</span>
              <input value={textbookForm.tags} onChange={(event) => setTextbookForm({ ...textbookForm, tags: event.target.value })} placeholder="用逗号、空格或顿号分隔" />
            </label>
            <SubmitButton saving={saving} />
          </form>
        )}
        {editing.type === "chapter" && (
          <form className="formGrid" onSubmit={submitChapter}>
            <div className="row">
              <label className="field">
                <span>章节名称</span>
                <input value={chapterForm.name} onChange={(event) => setChapterForm({ ...chapterForm, name: event.target.value })} />
              </label>
              <label className="field">
                <span>父级章节</span>
                <select value={chapterForm.parent_id} onChange={(event) => setChapterForm({ ...chapterForm, parent_id: event.target.value })}>
                  <option value="">无</option>
                  {scopedChapters
                    .filter((chapter) => chapter.id !== (editing.item as ChapterResponse | null)?.id)
                    .map((chapter) => (
                      <option key={chapter.id} value={chapter.id}>{chapter.path}</option>
                    ))}
                </select>
              </label>
            </div>
            <div className="row">
              <label className="field">
                <span>路径</span>
                <input value={chapterForm.path} onChange={(event) => setChapterForm({ ...chapterForm, path: event.target.value })} />
              </label>
              <label className="field">
                <span>层级</span>
                <input value={chapterForm.level} onChange={(event) => setChapterForm({ ...chapterForm, level: event.target.value })} />
              </label>
            </div>
            <label className="field">
              <span>排序</span>
              <input value={chapterForm.sort_order} onChange={(event) => setChapterForm({ ...chapterForm, sort_order: event.target.value })} />
            </label>
            <SubmitButton saving={saving} />
          </form>
        )}
        {editing.type === "point" && (
          <form className="formGrid" onSubmit={submitPoint}>
            <div className="row">
              <label className="field">
                <span>知识点名称</span>
                <input value={pointForm.name} onChange={(event) => setPointForm({ ...pointForm, name: event.target.value })} />
              </label>
              <label className="field">
                <span>章节</span>
                <select value={pointForm.chapter_id} onChange={(event) => setPointForm({ ...pointForm, chapter_id: event.target.value })}>
                  <option value="">未绑定</option>
                  {scopedChapters.map((chapter) => (
                    <option key={chapter.id} value={chapter.id}>{chapter.path}</option>
                  ))}
                </select>
              </label>
            </div>
            <div className="row">
              <label className="field">
                <span>类目</span>
                <select value={pointForm.category_id} onChange={(event) => setPointForm({ ...pointForm, category_id: event.target.value })}>
                  <option value="">未分类</option>
                  {scopedCategories.map((category) => (
                    <option key={category.id} value={category.id}>{category.name}</option>
                  ))}
                </select>
              </label>
              <label className="field">
                <span>父级知识点</span>
                <select value={pointForm.parent_id} onChange={(event) => setPointForm({ ...pointForm, parent_id: event.target.value })}>
                  <option value="">无</option>
                  {scopedPoints
                    .filter((point) => point.id !== (editing.item as KnowledgePointResponse | null)?.id)
                    .map((point) => (
                      <option key={point.id} value={point.id}>{point.path}</option>
                    ))}
                </select>
              </label>
            </div>
            <div className="row">
              <label className="field">
                <span>路径</span>
                <input value={pointForm.path} onChange={(event) => setPointForm({ ...pointForm, path: event.target.value })} />
              </label>
              <label className="field">
                <span>关键词</span>
                <input value={pointForm.keywords} onChange={(event) => setPointForm({ ...pointForm, keywords: event.target.value })} />
              </label>
            </div>
            <label className="field">
              <span>描述</span>
              <textarea rows={3} value={pointForm.description} onChange={(event) => setPointForm({ ...pointForm, description: event.target.value })} />
            </label>
            <div className="row">
              <label className="field">
                <span>状态</span>
                <select value={pointForm.status} onChange={(event) => setPointForm({ ...pointForm, status: event.target.value })}>
                  <option value="active">active</option>
                  <option value="inactive">inactive</option>
                  <option value="draft">draft</option>
                </select>
              </label>
              <label className="field">
                <span>排序</span>
                <input value={pointForm.sort_order} onChange={(event) => setPointForm({ ...pointForm, sort_order: event.target.value })} />
              </label>
            </div>
            <SubmitButton saving={saving} />
          </form>
        )}
      </div>
    );
  }

  function renderOverview() {
    if (!selectedSubject) return <div className="empty compact">请选择学科</div>;
    return (
      <div className="dashboardGrid">
        <div className="panel softPanel">
          <div className="panelHeader">
            <h2>章节覆盖</h2>
            <p>按章节查看知识点数量，便于发现教材目录中尚未覆盖的节点。</p>
          </div>
          <div className="panelBody metricTable">
            {scopedChapters.slice(0, 8).map((chapter) => (
              <div key={chapter.id} className="metricRow">
                <div>
                  <strong>{chapter.name}</strong>
                  <span className="muted">{chapter.path}</span>
                </div>
                <StatusBadge value={`${pointCountByChapter.get(chapter.id) || 0} 个`} tone="info" />
              </div>
            ))}
            {!scopedChapters.length && <div className="empty compact">暂无章节</div>}
          </div>
        </div>
        <div className="panel softPanel">
          <div className="panelHeader">
            <h2>映射准备度</h2>
            <p>原始题映射依赖知识点名称、关键词、章节和类目。</p>
          </div>
          <div className="panelBody stackList">
            <div className="detailRow"><span>知识点总数</span><strong>{scopedPoints.length}</strong></div>
            <div className="detailRow"><span>绑定章节</span><strong>{scopedPoints.length - unmappedPoints}</strong></div>
            <div className="detailRow"><span>未绑定章节</span><strong>{unmappedPoints}</strong></div>
            <div className="detailRow"><span>教材资料</span><strong>{scopedTextbooks.length}</strong></div>
          </div>
        </div>
      </div>
    );
  }

  function renderCategories() {
    return (
      <div className="stackList">
        <div className="buttonRow">
          <button className="button primary" type="button" onClick={() => beginCreate("category")} disabled={!selectedSubject}>
            新增类目
          </button>
        </div>
        <div className="metricTable">
          {scopedCategories.map((category) => (
            <button key={category.id} className="listButton" type="button" onClick={() => beginEdit("category", category)}>
              <div>
                <strong>{category.name}</strong>
                <span className="muted">排序 {category.sort_order}</span>
              </div>
              <StatusBadge value={`${pointCountByCategory.get(category.id) || 0} 个知识点`} tone="info" />
            </button>
          ))}
          {!scopedCategories.length && <div className="empty compact">暂无类目</div>}
        </div>
      </div>
    );
  }

  function renderTextbooks() {
    return (
      <div className="stackList">
        <div className="buttonRow">
          <button className="button primary" type="button" onClick={() => beginCreate("textbook")} disabled={!selectedSubject}>
            新增教材
          </button>
        </div>
        <div className="metricTable">
          {scopedTextbooks.map((textbook) => (
            <button key={textbook.id} className="listButton" type="button" onClick={() => beginEdit("textbook", textbook)}>
              <div>
                <strong>{textbook.source_title}</strong>
                <span className="muted">
                  {[categoryName(textbook.category_id), textbook.source_version, textbook.year].filter(Boolean).join(" / ") || textbook.filename}
                </span>
              </div>
              <StatusBadge value={textbook.parse_status} tone={textbook.parse_status === "parsed" ? "good" : "info"} />
            </button>
          ))}
          {!scopedTextbooks.length && <div className="empty compact">暂无教材</div>}
        </div>
      </div>
    );
  }

  function renderChapters() {
    return (
      <div className="stackList">
        <div className="buttonRow">
          <button className="button primary" type="button" onClick={() => beginCreate("chapter")} disabled={!selectedSubject}>
            新增章节
          </button>
        </div>
        <div className="metricTable">
          {scopedChapters.map((chapter) => (
            <button key={chapter.id} className="listButton" type="button" onClick={() => beginEdit("chapter", chapter)}>
              <div>
                <strong>{chapter.name}</strong>
                <span className="muted">{chapter.path}</span>
              </div>
              <div className="badgeStack">
                <StatusBadge value={`L${chapter.level}`} tone="info" />
                <StatusBadge value={`${pointCountByChapter.get(chapter.id) || 0} 个知识点`} tone="good" />
              </div>
            </button>
          ))}
          {!scopedChapters.length && <div className="empty compact">暂无章节</div>}
        </div>
      </div>
    );
  }

  function renderPoints() {
    return (
      <div className="stackList">
        <div className="buttonRow">
          <button className="button primary" type="button" onClick={() => beginCreate("point")} disabled={!selectedSubject}>
            新增知识点
          </button>
        </div>
        <div className="metricTable">
          {scopedPoints.map((point) => (
            <button key={point.id} className="listButton" type="button" onClick={() => beginEdit("point", point)}>
              <div>
                <strong>{point.name}</strong>
                <span className="muted">{point.description || point.path}</span>
                <span className="muted">
                  {[chapterName(point.chapter_id), categoryName(point.category_id), keywordPreview(point.keywords_json)].filter(Boolean).join(" / ")}
                </span>
              </div>
              <StatusBadge value={point.status} tone={point.status === "active" ? "good" : "info"} />
            </button>
          ))}
          {!scopedPoints.length && <div className="empty compact">暂无知识点</div>}
        </div>
      </div>
    );
  }

  function categoryName(categoryId?: number | null) {
    return scopedCategories.find((category) => category.id === categoryId)?.name || "";
  }

  function chapterName(chapterId?: number | null) {
    return scopedChapters.find((chapter) => chapter.id === chapterId)?.path || "";
  }
}

function SubmitButton({ saving }: { saving: boolean }) {
  return (
    <div className="buttonRow">
      <button className="button primary" type="submit" disabled={saving}>
        {saving ? "保存中..." : "保存"}
      </button>
    </div>
  );
}

function editorTitle(type: EditableType, isEdit: boolean): string {
  const action = isEdit ? "编辑" : "新增";
  const label = type === "subject" ? "学科" : type === "category" ? "类目" : type === "textbook" ? "教材" : type === "chapter" ? "章节" : "知识点";
  return `${action}${label}`;
}

function toNumber(value: string): number {
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : 0;
}

function toNullableNumber(value: string): number | null {
  if (!value.trim()) return null;
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : null;
}

function splitList(value: string): string[] {
  return value.split(/[，,、\s]+/).map((item) => item.trim()).filter(Boolean);
}

function keywordPreview(keywords?: string[] | null): string {
  if (!keywords?.length) return "";
  return `关键词：${keywords.slice(0, 3).join("、")}`;
}

function userTags(tags?: string[] | null): string[] {
  return (tags || []).filter((tag) => !tag.startsWith("category:") && !tag.startsWith("version:"));
}
