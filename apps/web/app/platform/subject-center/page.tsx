"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import {
  apiFetch,
  ChapterBatchDeleteResponse,
  ChapterDeleteResponse,
  ChapterMarkdownImportResponse,
  ChapterResponse,
  KnowledgePointMarkdownImportResponse,
  KnowledgePointResponse,
  SubjectBatchDeleteResponse,
  SubjectDeleteResponse,
  SubjectCategoryResponse,
  SubjectResponse,
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

type ManageTab = "overview" | "categories" | "chapters" | "points" | "pointDetails";
type EditableType = "subject" | "category" | "chapter" | "point" | "pointDetail";
type EditableItem =
  | SubjectResponse
  | SubjectCategoryResponse
  | ChapterResponse
  | KnowledgePointResponse
  | null;

const defaultSubjectForm = { code: "", name: "", status: "active" };
const defaultCategoryForm = { name: "", sort_order: "0" };
const defaultChapterForm = { category_id: "", name: "", parent_id: "", path: "", level: "", sort_order: "0" };
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
  const [chapters, setChapters] = useState<ChapterResponse[]>([]);
  const [points, setPoints] = useState<KnowledgePointResponse[]>([]);
  const [selectedSubjectId, setSelectedSubjectId] = useState<number | null>(null);
  const [activeTab, setActiveTab] = useState<ManageTab>("overview");
  const [editing, setEditing] = useState<{ type: EditableType; item: EditableItem } | null>(null);
  const [subjectForm, setSubjectForm] = useState(defaultSubjectForm);
  const [categoryForm, setCategoryForm] = useState(defaultCategoryForm);
  const [chapterForm, setChapterForm] = useState(defaultChapterForm);
  const [chapterImportMarkdown, setChapterImportMarkdown] = useState("");
  const [chapterImportOpen, setChapterImportOpen] = useState(false);
  const [pointImportMarkdown, setPointImportMarkdown] = useState("");
  const [pointImportOpen, setPointImportOpen] = useState(false);
  const [pointDetailImportMarkdown, setPointDetailImportMarkdown] = useState("");
  const [pointDetailImportOpen, setPointDetailImportOpen] = useState(false);
  const [selectedChapterCategoryId, setSelectedChapterCategoryId] = useState<number | null>(null);
  const [selectedChapterRootId, setSelectedChapterRootId] = useState<number | null>(null);
  const [selectedSubjectIds, setSelectedSubjectIds] = useState<number[]>([]);
  const [selectedChapterIds, setSelectedChapterIds] = useState<number[]>([]);
  const [pointForm, setPointForm] = useState(defaultPointForm);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [importingChapters, setImportingChapters] = useState(false);
  const [importingPoints, setImportingPoints] = useState(false);
  const [importingPointDetails, setImportingPointDetails] = useState(false);
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
      const [nextSubjects, nextCategories, nextChapters, nextPoints] = await Promise.allSettled([
        apiFetch<SubjectResponse[]>("/api/knowledge/subjects"),
        apiFetch<SubjectCategoryResponse[]>("/api/knowledge/categories"),
        apiFetch<ChapterResponse[]>("/api/knowledge/chapters"),
        apiFetch<KnowledgePointResponse[]>("/api/knowledge/points"),
      ]);

      if (!requestGate.isCurrent(requestId)) return;

      const results = [nextSubjects, nextCategories, nextChapters, nextPoints];
      if (allRejected(results)) {
        throw firstRejectedReason(results) || new Error("No subject-center requests succeeded.");
      }

      const subjectList = nextSubjects.status === "fulfilled" ? nextSubjects.value : [];
      setSubjects(subjectList);
      setCategories(nextCategories.status === "fulfilled" ? nextCategories.value : []);
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
          { label: "章 / 节", result: nextChapters },
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
  const scopedChapters = useMemo(
    () => chapters.filter((chapter) => chapter.subject_id === selectedSubjectId),
    [chapters, selectedSubjectId],
  );
  const scopedPoints = useMemo(
    () => points.filter((point) => point.subject_id === selectedSubjectId),
    [points, selectedSubjectId],
  );
  const chapterCategories = useMemo(() => {
    const ranked = [...scopedCategories].sort((left, right) => (
      left.sort_order - right.sort_order || left.id - right.id
    ));
    const uncategorizedCount = scopedChapters.filter((chapter) => !chapter.category_id).length;
    if (uncategorizedCount) {
      return [...ranked, { id: 0, subject_id: selectedSubjectId || 0, name: "未归类章 / 节", sort_order: Number.MAX_SAFE_INTEGER }];
    }
    return ranked;
  }, [scopedCategories, scopedChapters, selectedSubjectId]);
  const activeChapterCategoryId = useMemo(() => {
    if (selectedChapterCategoryId === 0 && scopedChapters.some((chapter) => !chapter.category_id)) return 0;
    if (selectedChapterCategoryId && scopedCategories.some((category) => category.id === selectedChapterCategoryId)) {
      return selectedChapterCategoryId;
    }
    const firstNonEmptyCategory = chapterCategories.find((category) => (
      category.id === 0
        ? scopedChapters.some((chapter) => !chapter.category_id) || scopedPoints.some((point) => !point.category_id)
        : scopedChapters.some((chapter) => chapter.category_id === category.id) || scopedPoints.some((point) => point.category_id === category.id)
    ));
    return firstNonEmptyCategory?.id ?? chapterCategories[0]?.id ?? null;
  }, [chapterCategories, scopedCategories, scopedChapters, selectedChapterCategoryId]);
  const activeChapterCategory = useMemo(
    () => chapterCategories.find((category) => category.id === activeChapterCategoryId) || null,
    [activeChapterCategoryId, chapterCategories],
  );
  const scopedChaptersForCategory = useMemo(
    () => scopedChapters.filter((chapter) => (activeChapterCategoryId === 0 ? !chapter.category_id : chapter.category_id === activeChapterCategoryId)),
    [activeChapterCategoryId, scopedChapters],
  );
  const rootChapters = useMemo(
    () => scopedChaptersForCategory.filter((chapter) => !chapter.parent_id || chapter.level <= 1),
    [scopedChaptersForCategory],
  );
  const childChaptersByParent = useMemo(() => {
    const map = new Map<number, ChapterResponse[]>();
    for (const chapter of scopedChaptersForCategory) {
      if (!chapter.parent_id) continue;
      const children = map.get(chapter.parent_id) || [];
      children.push(chapter);
      map.set(chapter.parent_id, children);
    }
    return map;
  }, [scopedChaptersForCategory]);
  const chapterById = useMemo(
    () => new Map(scopedChapters.map((chapter) => [chapter.id, chapter])),
    [scopedChapters],
  );
  const selectedChapterRoot = useMemo(() => {
    if (selectedChapterRootId && rootChapters.some((chapter) => chapter.id === selectedChapterRootId)) {
      return rootChapters.find((chapter) => chapter.id === selectedChapterRootId) || null;
    }
    return rootChapters[0] || null;
  }, [rootChapters, selectedChapterRootId]);
  const rootPoints = useMemo(
    () => scopedPoints.filter((point) => !point.parent_id),
    [scopedPoints],
  );
  const pointDetails = useMemo(
    () => scopedPoints.filter((point) => !!point.parent_id),
    [scopedPoints],
  );
  const pointById = useMemo(
    () => new Map(scopedPoints.map((point) => [point.id, point])),
    [scopedPoints],
  );
  const rootPointsByChapter = useMemo(() => {
    const map = new Map<number, KnowledgePointResponse[]>();
    for (const point of rootPoints) {
      if (!point.chapter_id) continue;
      const items = map.get(point.chapter_id) || [];
      items.push(point);
      map.set(point.chapter_id, items);
    }
    return map;
  }, [rootPoints]);
  const pointDetailsByParent = useMemo(() => {
    const map = new Map<number, KnowledgePointResponse[]>();
    for (const detail of pointDetails) {
      if (!detail.parent_id) continue;
      const items = map.get(detail.parent_id) || [];
      items.push(detail);
      map.set(detail.parent_id, items);
    }
    return map;
  }, [pointDetails]);
  const detailCountByPoint = useMemo(() => {
    const map = new Map<number, number>();
    for (const detail of pointDetails) {
      if (!detail.parent_id) continue;
      map.set(detail.parent_id, (map.get(detail.parent_id) || 0) + 1);
    }
    return map;
  }, [pointDetails]);
  const bindableChapters = useMemo(
    () => scopedChapters.filter((chapter) => !scopedChapters.some((candidate) => candidate.parent_id === chapter.id)),
    [scopedChapters],
  );
  const bindableChaptersByCategory = useMemo(() => {
    const map = new Map<number, ChapterResponse[]>();
    for (const category of scopedCategories) {
      map.set(
        category.id,
        scopedChapters.filter((chapter) => chapter.category_id === category.id && !scopedChapters.some((candidate) => candidate.parent_id === chapter.id)),
      );
    }
    return map;
  }, [scopedCategories, scopedChapters]);

  const pointCountByChapter = useMemo(() => {
    const map = new Map<number, number>();
    for (const point of scopedPoints) {
      if (point.chapter_id) {
        map.set(point.chapter_id, (map.get(point.chapter_id) || 0) + 1);
      }
    }
    return map;
  }, [scopedPoints]);
  const pointCountByChapterTree = useMemo(() => {
    const map = new Map<number, number>();
    for (const point of scopedPoints) {
      let currentChapterId = point.chapter_id || null;
      while (currentChapterId) {
        map.set(currentChapterId, (map.get(currentChapterId) || 0) + 1);
        currentChapterId = chapterById.get(currentChapterId)?.parent_id || null;
      }
    }
    return map;
  }, [chapterById, scopedPoints]);

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
  const mappedBindableChapters = bindableChapters.filter((chapter) => (pointCountByChapter.get(chapter.id) || 0) > 0).length;
  const selectedDetailParentPoint = useMemo(() => {
    const parentId = toNullableNumber(pointForm.parent_id);
    return parentId ? rootPoints.find((point) => point.id === parentId) || null : null;
  }, [pointForm.parent_id, rootPoints]);
  const pointSectionOptions = useMemo(() => {
    const categoryId = toNullableNumber(pointForm.category_id);
    if (!categoryId) return [] as ChapterResponse[];
    const options = bindableChaptersByCategory.get(categoryId) || [];
    const currentChapterId = toNullableNumber(pointForm.chapter_id);
    if (currentChapterId && !options.some((chapter) => chapter.id === currentChapterId)) {
      const currentChapter = chapterById.get(currentChapterId);
      if (currentChapter) {
        return [currentChapter, ...options];
      }
    }
    return options;
  }, [bindableChaptersByCategory, chapterById, pointForm.category_id, pointForm.chapter_id]);

  function pickSubject(subjectId: number) {
    setSelectedSubjectId(subjectId);
    setEditing(null);
    setChapterImportOpen(false);
    setPointImportOpen(false);
    setPointDetailImportOpen(false);
    setSelectedChapterCategoryId(null);
    setSelectedChapterRootId(null);
    setSelectedChapterIds([]);
    setActionMessage("");
  }

  function beginCreate(type: EditableType) {
    setActionMessage("");
    setChapterImportOpen(false);
    setPointImportOpen(false);
    setPointDetailImportOpen(false);
    setEditing({ type, item: null });
    if (type === "subject") setSubjectForm(defaultSubjectForm);
    if (type === "category") setCategoryForm(defaultCategoryForm);
    if (type === "chapter") {
      setChapterForm({ ...defaultChapterForm, category_id: activeChapterCategoryId && activeChapterCategoryId > 0 ? String(activeChapterCategoryId) : "" });
    }
    if (type === "point" || type === "pointDetail") {
      setPointForm({
        ...defaultPointForm,
        category_id: activeChapterCategoryId && activeChapterCategoryId > 0 ? String(activeChapterCategoryId) : "",
      });
    }
  }

  function beginEdit(type: EditableType, item: EditableItem) {
    setActionMessage("");
    setChapterImportOpen(false);
    setPointImportOpen(false);
    setPointDetailImportOpen(false);
    setEditing({ type, item });
    if (type === "subject") {
      const subject = item as SubjectResponse;
      setSubjectForm({ code: subject.code, name: subject.name, status: subject.status });
    }
    if (type === "category") {
      const category = item as SubjectCategoryResponse;
      setCategoryForm({ name: category.name, sort_order: String(category.sort_order) });
    }
    if (type === "chapter") {
      const chapter = item as ChapterResponse;
      if (chapter.category_id) setSelectedChapterCategoryId(chapter.category_id);
      setChapterForm({
        category_id: chapter.category_id ? String(chapter.category_id) : "",
        name: chapter.name,
        parent_id: chapter.parent_id ? String(chapter.parent_id) : "",
        path: chapter.path,
        level: String(chapter.level),
        sort_order: String(chapter.sort_order),
      });
    }
    if (type === "point" || type === "pointDetail") {
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

  function beginChapterImport() {
    setActionMessage("");
    setEditing(null);
    setPointImportOpen(false);
    setPointDetailImportOpen(false);
    setChapterImportOpen(true);
  }

  function beginPointImport() {
    setActionMessage("");
    setEditing(null);
    setChapterImportOpen(false);
    setPointDetailImportOpen(false);
    setPointImportOpen(true);
  }

  function beginPointDetailImport() {
    setActionMessage("");
    setEditing(null);
    setChapterImportOpen(false);
    setPointImportOpen(false);
    setPointDetailImportOpen(true);
  }

  function beginCreatePointForChapter(chapter: ChapterResponse) {
    setActionMessage("");
    setChapterImportOpen(false);
    setPointImportOpen(false);
    setPointDetailImportOpen(false);
    setEditing({ type: "point", item: null });
    setPointForm({
      ...defaultPointForm,
      category_id: chapter.category_id ? String(chapter.category_id) : "",
      chapter_id: String(chapter.id),
      path: "",
    });
  }

  function beginCreatePointDetailForPoint(point: KnowledgePointResponse) {
    setActionMessage("");
    setChapterImportOpen(false);
    setPointImportOpen(false);
    setPointDetailImportOpen(false);
    setEditing({ type: "pointDetail", item: null });
    setPointForm({
      ...defaultPointForm,
      parent_id: String(point.id),
      category_id: point.category_id ? String(point.category_id) : "",
      chapter_id: point.chapter_id ? String(point.chapter_id) : "",
      path: "",
    });
  }

  function toggleSubjectSelection(subjectId: number) {
    setSelectedSubjectIds((current) =>
      current.includes(subjectId) ? current.filter((id) => id !== subjectId) : [...current, subjectId],
    );
  }

  function toggleChapterSelection(chapterId: number) {
    setSelectedChapterIds((current) =>
      current.includes(chapterId) ? current.filter((id) => id !== chapterId) : [...current, chapterId],
    );
  }

  function toggleSectionGroupSelection(chapterIds: number[]) {
    if (!chapterIds.length) return;
    setSelectedChapterIds((current) => {
      const allSelected = chapterIds.every((id) => current.includes(id));
      if (allSelected) {
        return current.filter((id) => !chapterIds.includes(id));
      }
      return Array.from(new Set([...current, ...chapterIds]));
    });
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

  async function submitChapter(event: FormEvent) {
    event.preventDefault();
    if (!selectedSubjectId) return setError("请先选择学科");
    if (!chapterForm.category_id) return setError("请先选择章 / 节所属类目");
    const chapter = editing?.item as ChapterResponse | null;
    await saveEntity(
      chapter ? `/api/knowledge/chapters/${chapter.id}` : "/api/knowledge/chapters",
      chapter ? "PATCH" : "POST",
      {
        subject_id: selectedSubjectId,
        category_id: toNullableNumber(chapterForm.category_id),
        parent_id: toNullableNumber(chapterForm.parent_id),
        name: chapterForm.name.trim(),
        level: toNullableNumber(chapterForm.level),
        path: chapterForm.path.trim() || null,
        sort_order: toNumber(chapterForm.sort_order),
      },
      "章 / 节已保存",
    );
  }

  async function submitChapterImport(event: FormEvent) {
    event.preventDefault();
    if (!selectedSubjectId) return setError("请先选择学科");
    if (!activeChapterCategoryId || activeChapterCategoryId === 0) return setError("请先选择一个已创建的类目");
    if (!chapterImportMarkdown.trim()) return setError("请粘贴 Markdown 目录");
    const subjectId = selectedSubjectId;
    setImportingChapters(true);
    setError("");
    setActionMessage("");
    try {
      const result = await apiFetch<ChapterMarkdownImportResponse>("/api/knowledge/chapters/import-markdown", {
        method: "POST",
        body: JSON.stringify({
          subject_id: subjectId,
          category_id: activeChapterCategoryId,
          markdown: chapterImportMarkdown,
        }),
      });
      setChapterImportMarkdown("");
      setChapterImportOpen(false);
      setActionMessage(result.message);
      await loadAll(subjectId);
    } catch (err) {
      setError(toErrorMessage(err, "导入目录失败"));
    } finally {
      setImportingChapters(false);
    }
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

  async function submitPointDetail(event: FormEvent) {
    event.preventDefault();
    if (!selectedSubjectId) return setError("请先选择学科");
    if (!selectedDetailParentPoint) return setError("请先选择父级知识点");
    const point = editing?.item as KnowledgePointResponse | null;
    await saveEntity(
      point ? `/api/knowledge/points/${point.id}` : "/api/knowledge/points",
      point ? "PATCH" : "POST",
      {
        subject_id: selectedSubjectId,
        category_id: selectedDetailParentPoint.category_id ?? null,
        chapter_id: selectedDetailParentPoint.chapter_id ?? null,
        parent_id: selectedDetailParentPoint.id,
        name: pointForm.name.trim(),
        level: toNullableNumber(pointForm.level),
        path: pointForm.path.trim() || null,
        description: pointForm.description.trim() || null,
        keywords_json: splitList(pointForm.keywords),
        status: pointForm.status.trim() || "active",
        sort_order: toNumber(pointForm.sort_order),
      },
      "知识点详情已保存",
    );
  }

  async function submitPointImport(event: FormEvent) {
    event.preventDefault();
    if (!selectedSubjectId) return setError("请先选择学科");
    if (!activeChapterCategoryId || activeChapterCategoryId === 0) return setError("请先选择一个已创建的类目");
    if (!pointImportMarkdown.trim()) return setError("请粘贴知识点 Markdown 目录");
    const subjectId = selectedSubjectId;
    setImportingPoints(true);
    setError("");
    setActionMessage("");
    try {
      const result = await apiFetch<KnowledgePointMarkdownImportResponse>("/api/knowledge/points/import-markdown", {
        method: "POST",
        body: JSON.stringify({
          subject_id: subjectId,
          category_id: activeChapterCategoryId,
          markdown: pointImportMarkdown,
          import_mode: "point",
        }),
      });
      setPointImportMarkdown("");
      setPointImportOpen(false);
      setActionMessage(result.message);
      await loadAll(subjectId);
    } catch (err) {
      setError(toErrorMessage(err, "导入知识点失败"));
    } finally {
      setImportingPoints(false);
    }
  }

  async function submitPointDetailImport(event: FormEvent) {
    event.preventDefault();
    if (!selectedSubjectId) return setError("请先选择学科");
    if (!activeChapterCategoryId || activeChapterCategoryId === 0) return setError("请先选择一个已创建的类目");
    if (!pointDetailImportMarkdown.trim()) return setError("请粘贴知识点详情 Markdown 目录");
    const subjectId = selectedSubjectId;
    setImportingPointDetails(true);
    setError("");
    setActionMessage("");
    try {
      const result = await apiFetch<KnowledgePointMarkdownImportResponse>("/api/knowledge/points/import-markdown", {
        method: "POST",
        body: JSON.stringify({
          subject_id: subjectId,
          category_id: activeChapterCategoryId,
          markdown: pointDetailImportMarkdown,
          import_mode: "detail",
        }),
      });
      setPointDetailImportMarkdown("");
      setPointDetailImportOpen(false);
      setActionMessage(result.message);
      await loadAll(subjectId);
    } catch (err) {
      setError(toErrorMessage(err, "导入知识点详情失败"));
    } finally {
      setImportingPointDetails(false);
    }
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

  async function deleteSubject(subject: SubjectResponse) {
    if (!window.confirm(`确定删除学科「${subject.name}」吗？会连同下挂的所有内容一起删除。`)) return;
    setSaving(true);
    setError("");
    setActionMessage("");
    try {
      const result = await apiFetch<SubjectDeleteResponse>(`/api/knowledge/subjects/${subject.id}`, { method: "DELETE" });
      setEditing(null);
      setActionMessage(`学科「${result.name}」已删除`);
      await loadAll(null);
    } catch (err) {
      setError(toErrorMessage(err, "删除学科失败"));
    } finally {
      setSaving(false);
    }
  }

  async function deleteChapter(chapter: ChapterResponse) {
    const childCount = childChaptersByParent.get(chapter.id)?.length || 0;
    const message = childCount > 0
      ? `确定删除章「${chapter.name}」及其 ${childCount} 个节吗？关联知识点会一并删除。`
      : `确定删除${chapter.parent_id ? "节" : "章"}「${chapter.name}」吗？关联知识点会一并删除。`;
    if (!window.confirm(message)) return;
    setSaving(true);
    setError("");
    setActionMessage("");
    try {
      const result = await apiFetch<ChapterDeleteResponse>(`/api/knowledge/chapters/${chapter.id}`, { method: "DELETE" });
      setEditing(null);
      setSelectedChapterRootId(null);
      setActionMessage(`已删除 ${result.removed_chapter_count} 个章 / 节节点，解绑 ${result.unbound_point_count} 个知识点。`);
      await loadAll(selectedSubjectId);
    } catch (err) {
      setError(toErrorMessage(err, "删除章 / 节失败"));
    } finally {
      setSaving(false);
    }
  }

  async function deleteSelectedSubjects() {
    if (!selectedSubjectIds.length) return;
    if (!window.confirm(`确定批量删除选中的 ${selectedSubjectIds.length} 个学科吗？会连同下挂内容一起删除。`)) return;
    setSaving(true);
    setError("");
    setActionMessage("");
    try {
      const result = await apiFetch<SubjectBatchDeleteResponse>("/api/knowledge/subjects/batch-delete", {
        method: "POST",
        body: JSON.stringify({ ids: selectedSubjectIds }),
      });
      setSelectedSubjectIds([]);
      setEditing(null);
      setActionMessage(result.message);
      await loadAll(null);
    } catch (err) {
      setError(toErrorMessage(err, "批量删除学科失败"));
    } finally {
      setSaving(false);
    }
  }

  async function deleteSelectedChapters() {
    if (!selectedChapterIds.length) return;
    if (!window.confirm(`确定批量删除选中的 ${selectedChapterIds.length} 个章 / 节节点吗？子节和关联知识点会一并删除。`)) return;
    setSaving(true);
    setError("");
    setActionMessage("");
    try {
      const result = await apiFetch<ChapterBatchDeleteResponse>("/api/knowledge/chapters/batch-delete", {
        method: "POST",
        body: JSON.stringify({ ids: selectedChapterIds }),
      });
      setSelectedChapterIds([]);
      setEditing(null);
      setSelectedChapterRootId(null);
      setActionMessage(result.message);
      await loadAll(selectedSubjectId);
    } catch (err) {
      setError(toErrorMessage(err, "批量删除章 / 节失败"));
    } finally {
      setSaving(false);
    }
  }

  return (
    <>
      <header className="pageHeader">
        <div>
          <h1>学科中心</h1>
          <p>统一维护学科、类目、章、节和知识点，后续原始题的考点映射会以这里的知识资产为准。</p>
        </div>
        <div className="buttonRow">
          <button className="button" type="button" onClick={() => beginCreate("subject")}>
            新增学科
          </button>
          <button className="button danger" type="button" disabled={saving || !selectedSubjectIds.length} onClick={deleteSelectedSubjects}>
            批量删除学科
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
                  <div key={subject.id} className="selectableRow">
                    <label className="rowCheck">
                      <input
                        type="checkbox"
                        checked={selectedSubjectIds.includes(subject.id)}
                        onChange={() => toggleSubjectSelection(subject.id)}
                      />
                    </label>
                    <button
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
                  </div>
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
                <small>用于区分章、节和知识点归属。</small>
              </article>
              <article className="statCard">
                <span>章 / 节</span>
                <strong>{mappedBindableChapters}/{bindableChapters.length}</strong>
                <small>章、节归属于类目；没有节时知识点可直接绑定到章。</small>
              </article>
              <article className="statCard">
                <span>知识点</span>
                <strong>{rootPoints.length}</strong>
                <small>{unmappedPoints} 个知识点节点尚未绑定章 / 节。</small>
              </article>
              <article className="statCard">
                <span>知识点详情</span>
                <strong>{pointDetails.length}</strong>
                <small>挂在一级知识点下的二级节点。</small>
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
                    <div className="buttonRow">
                      <button className="button" type="button" onClick={() => beginEdit("subject", selectedSubject)}>
                        编辑学科
                      </button>
                      <button className="button danger" type="button" disabled={saving} onClick={() => deleteSubject(selectedSubject)}>
                        删除学科
                      </button>
                    </div>
                  )}
                </div>
              </div>
              <div className="panelBody stackList">
                <p className="muted">默认在“总览”里查看主目录；“类目 / 章 / 节 / 知识点 / 知识点详情”页签保留给后期调整使用。</p>
                <div className="tabs">
                  {[
                    ["overview", "总览"],
                    ["categories", "类目"],
                    ["chapters", "章 / 节"],
                    ["points", "知识点"],
                    ["pointDetails", "知识点详情"],
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
                {activeTab === "chapters" && renderChapters()}
                {activeTab === "points" && renderPoints()}
                {activeTab === "pointDetails" && renderPointDetails()}
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
        {editing.type === "chapter" && (
          <form className="formGrid" onSubmit={submitChapter}>
            <div className="row">
              <label className="field">
                <span>所属类目</span>
                <select
                  value={chapterForm.category_id}
                  onChange={(event) => setChapterForm({ ...chapterForm, category_id: event.target.value, parent_id: "", path: "" })}
                >
                  <option value="">请选择类目</option>
                  {scopedCategories.map((category) => (
                    <option key={category.id} value={category.id}>{category.name}</option>
                  ))}
                </select>
              </label>
              <label className="field">
                <span>章 / 节名称</span>
                <input value={chapterForm.name} onChange={(event) => setChapterForm({ ...chapterForm, name: event.target.value })} />
              </label>
            </div>
            <div className="row">
              <label className="field">
                <span>父级节点</span>
                <select value={chapterForm.parent_id} onChange={(event) => setChapterForm({ ...chapterForm, parent_id: event.target.value, path: "" })}>
                  <option value="">无</option>
                  {scopedChapters
                    .filter((chapter) => chapter.category_id === toNullableNumber(chapterForm.category_id))
                    .filter((chapter) => chapter.id !== (editing.item as ChapterResponse | null)?.id)
                    .map((chapter) => (
                      <option key={chapter.id} value={chapter.id}>{chapter.path}</option>
                    ))}
                </select>
              </label>
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
        {(editing.type === "point" || editing.type === "pointDetail") && (
          <form className="formGrid" onSubmit={editing.type === "pointDetail" ? submitPointDetail : submitPoint}>
            <div className="row">
              <label className="field">
                <span>{editing.type === "pointDetail" ? "知识点详情名称" : "知识点名称"}</span>
                <input value={pointForm.name} onChange={(event) => setPointForm({ ...pointForm, name: event.target.value })} />
              </label>
              {editing.type === "point" ? (
                <label className="field">
                  <span>类目</span>
                  <select value={pointForm.category_id} onChange={(event) => updatePointCategory(event.target.value)}>
                    <option value="">未分类</option>
                    {scopedCategories.map((category) => (
                      <option key={category.id} value={category.id}>{category.name}</option>
                    ))}
                  </select>
                </label>
              ) : (
                <label className="field">
                  <span>父级知识点</span>
                  <select
                    value={pointForm.parent_id}
                    onChange={(event) => updatePointDetailParent(event.target.value, editing.item as KnowledgePointResponse | null)}
                  >
                    <option value="">请选择</option>
                    {rootPoints
                      .filter((point) => point.id !== (editing.item as KnowledgePointResponse | null)?.id)
                      .map((point) => (
                        <option key={point.id} value={point.id}>{point.path}</option>
                      ))}
                  </select>
                </label>
              )}
            </div>
            <div className="row">
              {editing.type === "point" ? (
                <>
                  <label className="field">
                    <span>章 / 节</span>
                    <select value={pointForm.chapter_id} onChange={(event) => setPointForm({ ...pointForm, chapter_id: event.target.value, path: "" })}>
                      <option value="">{pointForm.category_id ? "请选择章 / 节" : "请先选择类目"}</option>
                      {pointSectionOptions.map((chapter) => {
                        const isLegacyBinding = chapter.id === toNullableNumber(pointForm.chapter_id)
                          && scopedChapters.some((candidate) => candidate.parent_id === chapter.id);
                        return (
                          <option key={chapter.id} value={chapter.id}>
                            {isLegacyBinding ? `${chapter.path}（当前绑定，建议改到具体节）` : chapter.path}
                          </option>
                        );
                      })}
                    </select>
                  </label>
                  <label className="field">
                    <span>所属类目</span>
                    <input value={categoryName(toNullableNumber(pointForm.category_id))} readOnly />
                  </label>
                </>
              ) : (
                <>
                  <label className="field">
                    <span>所属章 / 节</span>
                    <input value={selectedDetailParentPoint ? chapterName(selectedDetailParentPoint.chapter_id) : ""} readOnly />
                  </label>
                  <label className="field">
                    <span>所属知识点</span>
                    <input value={selectedDetailParentPoint?.name || ""} readOnly />
                  </label>
                </>
              )}
            </div>
            {editing.type === "point" && toNullableNumber(pointForm.chapter_id) && scopedChapters.some((chapter) => chapter.parent_id === toNullableNumber(pointForm.chapter_id)) ? (
              <div className="calloutBox">当前知识点仍绑定在章上，建议改到该类目下的具体节。</div>
            ) : null}
            {editing.type === "pointDetail" && !selectedDetailParentPoint ? (
              <div className="calloutBox">知识点详情会自动继承父级知识点所在的章 / 节和类目。</div>
            ) : null}
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
      <div className="subjectDirectoryWorkspace">
        <aside className="directoryCategoryRail">
          <div className="directoryRailHeader">
            <div>
              <h2>类目总览</h2>
              <p>先选类目，再在右侧查看完整目录树。</p>
            </div>
            <button className="button primary" type="button" onClick={() => beginCreate("category")} disabled={!selectedSubject}>
              新增类目
            </button>
          </div>
          <div className="directoryCategoryList">
            {chapterCategories.map((category) => {
              const active = activeChapterCategory?.id === category.id;
              const categoryChapters = scopedChapters.filter((chapter) => (
                category.id === 0 ? !chapter.category_id : chapter.category_id === category.id
              ));
              const pointCount = category.id === 0
                ? scopedPoints.filter((point) => !point.category_id).length
                : (pointCountByCategory.get(category.id) || 0);
              return (
                <button
                  key={category.id}
                  className={active ? "directoryCategoryCard active" : "directoryCategoryCard"}
                  type="button"
                  onClick={() => {
                    setSelectedChapterCategoryId(category.id);
                    setSelectedChapterRootId(null);
                  }}
                >
                  <div className="directoryCategoryCardMain">
                    <span className="directoryCategoryEyebrow">{category.id === 0 ? "未归类" : "类目"}</span>
                    <strong>{category.name}</strong>
                    <small>{categoryChapters.length} 个章/节节点 · {pointCount} 个知识点相关节点</small>
                  </div>
                  <StatusBadge value={`${categoryChapters.length} 节点`} tone={active ? "good" : "info"} />
                </button>
              );
            })}
            {!chapterCategories.length && <div className="empty compact">暂无类目</div>}
          </div>
        </aside>

        <section className="directoryStage">
          <div className="directoryStageHeader">
            <div className="directoryStageTitle">
              <h2>{activeChapterCategory?.name || "目录主视图"}</h2>
              <p>按“学科 → 类目 → 章 → 节 → 知识点 → 知识点详情”浏览，调整操作保留到后面的页签里。</p>
              <div className="directoryStageMeta">
                <StatusBadge value={`${rootChapters.length} 个章入口`} tone="info" />
                <StatusBadge value={`${scopedChaptersForCategory.length} 个章/节节点`} tone="info" />
                <StatusBadge value={`${rootPoints.length} 个知识点`} tone="good" />
                <StatusBadge value={`${pointDetails.length} 个详情`} tone="good" />
              </div>
            </div>
            <div className="buttonRow">
              <button className="button small" type="button" onClick={() => setActiveTab("chapters")}>
                调整章 / 节
              </button>
              <button className="button small" type="button" onClick={() => setActiveTab("points")}>
                调整知识点
              </button>
            </div>
          </div>

          <div className="directoryStageBody">
            {!activeChapterCategory && <div className="empty compact">请先新增类目，并在类目下维护章和节</div>}
            {!!activeChapterCategory && !rootChapters.length && <div className="empty compact">当前类目下暂无章目录</div>}
            {rootChapters.map((chapter) => renderOverviewChapterTree(chapter, true))}
          </div>
        </section>
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

  function renderChapters() {
    return (
      <div className="stackList">
        <div className="buttonRow">
          <button className="button primary" type="button" onClick={() => beginCreate("chapter")} disabled={!selectedSubject}>
            新增章 / 节
          </button>
          <button className="button danger" type="button" disabled={saving || !selectedChapterIds.length} onClick={deleteSelectedChapters}>
            批量删除章 / 节
          </button>
          <button className="button" type="button" onClick={beginChapterImport} disabled={!selectedSubject}>
            导入目录
          </button>
          <button className="button" type="button" onClick={beginPointImport} disabled={!selectedSubject}>
            导入知识点
          </button>
          <button className="button" type="button" onClick={beginPointDetailImport} disabled={!selectedSubject || !rootPoints.length}>
            导入知识点详情
          </button>
        </div>
        {chapterImportOpen && (
          <div className="editorPanel">
            <div className="panelHeaderActions">
              <div>
                <strong>导入章 / 节目录</strong>
                <p className="muted">章 / 节会导入到当前选中的类目下，保存后会刷新当前学科中心数据。</p>
              </div>
              <button className="button small" type="button" onClick={() => setChapterImportOpen(false)}>
                取消
              </button>
            </div>
            <form className="formGrid" onSubmit={submitChapterImport}>
              <label className="field">
                <span>Markdown 目录</span>
                <textarea rows={10} value={chapterImportMarkdown} onChange={(event) => setChapterImportMarkdown(event.target.value)} />
              </label>
              <div className="buttonRow">
                <button className="button primary" type="submit" disabled={importingChapters}>
                  {importingChapters ? "导入中..." : "导入"}
                </button>
              </div>
            </form>
          </div>
        )}
        {pointImportOpen && (
          <div className="editorPanel">
            <div className="panelHeaderActions">
              <div>
                <strong>导入知识点</strong>
                <p className="muted">请按“章 / 节 / 知识点”结构粘贴 Markdown，保存后会自动绑定到当前类目下的对应章或节。</p>
              </div>
              <button className="button small" type="button" onClick={() => setPointImportOpen(false)}>
                取消
              </button>
            </div>
            <form className="formGrid" onSubmit={submitPointImport}>
              <label className="field">
                <span>Markdown 目录</span>
                <textarea rows={10} value={pointImportMarkdown} onChange={(event) => setPointImportMarkdown(event.target.value)} />
              </label>
              <div className="buttonRow">
                <button className="button primary" type="submit" disabled={importingPoints}>
                  {importingPoints ? "导入中..." : "导入"}
                </button>
              </div>
            </form>
          </div>
        )}
        {pointDetailImportOpen && (
          <div className="editorPanel">
            <div className="panelHeaderActions">
              <div>
                <strong>导入知识点详情</strong>
                <p className="muted">请按“章 / 节 / 知识点 / 知识点详情”结构粘贴 Markdown，保存后会自动挂到当前类目下对应知识点。</p>
              </div>
              <button className="button small" type="button" onClick={() => setPointDetailImportOpen(false)}>
                取消
              </button>
            </div>
            <form className="formGrid" onSubmit={submitPointDetailImport}>
              <label className="field">
                <span>Markdown 目录</span>
                <textarea rows={10} value={pointDetailImportMarkdown} onChange={(event) => setPointDetailImportMarkdown(event.target.value)} />
              </label>
              <div className="buttonRow">
                <button className="button primary" type="submit" disabled={importingPointDetails}>
                  {importingPointDetails ? "导入中..." : "导入"}
                </button>
              </div>
            </form>
          </div>
        )}
        <div className="chapterDirectory">
          <div className="chapterRootList">
            {chapterCategories.map((category) => {
              const active = activeChapterCategory?.id === category.id;
              const categoryChapters = scopedChapters.filter((chapter) => (
                category.id === 0 ? !chapter.category_id : chapter.category_id === category.id
              ));
              const pointCount = categoryChapters.reduce((total, chapter) => total + (pointCountByChapterTree.get(chapter.id) || 0), 0);
              return (
                <div key={category.id} className="selectableRow">
                  <button
                    className={active ? "chapterRootButton active" : "chapterRootButton"}
                    type="button"
                    onClick={() => {
                      setSelectedChapterCategoryId(category.id);
                      setSelectedChapterRootId(null);
                    }}
                  >
                    <span>
                      <strong>{category.name}</strong>
                      <small>{categoryChapters.length} 个章/节节点 · {pointCount} 个知识点相关节点</small>
                    </span>
                    <StatusBadge value="类目" tone="info" />
                  </button>
                </div>
              );
            })}
          </div>
          <div className="chapterSectionList">
            {activeChapterCategory && (
              <div className="chapterSectionHeader">
                <div>
                  <strong>{activeChapterCategory.name}</strong>
                  <span className="muted">
                    {rootChapters.length} 个章入口 · {scopedChaptersForCategory.length} 个章/节节点
                  </span>
                </div>
              </div>
            )}
            {rootChapters.map((chapter) => {
              const expanded = selectedChapterRoot ? selectedChapterRoot.id === chapter.id : true;
              const sectionIds = [chapter.id, ...(childChaptersByParent.get(chapter.id) || []).map((item) => item.id)];
              return (
                <div key={chapter.id} className="stackList">
                  <div className="chapterSectionHeader">
                    <div>
                      <strong>{chapter.name}</strong>
                      <span className="muted">
                        {(childChaptersByParent.get(chapter.id)?.length || 0)} 个节 · {pointCountByChapterTree.get(chapter.id) || 0} 个知识点相关节点
                      </span>
                    </div>
                    <label className="rowCheck inlineCheck">
                      <input
                        type="checkbox"
                        checked={sectionIds.every((id) => selectedChapterIds.includes(id))}
                        onChange={() => toggleSectionGroupSelection(sectionIds)}
                      />
                      <span>全选本组</span>
                    </label>
                    <div className="buttonRow">
                      <button className="button small" type="button" onClick={() => setSelectedChapterRootId(expanded ? null : chapter.id)}>
                        {expanded ? "收起" : "展开"}
                      </button>
                      <button className="button small" type="button" onClick={() => beginEdit("chapter", chapter)}>
                        编辑
                      </button>
                      <button className="button small danger" type="button" disabled={saving} onClick={() => deleteChapter(chapter)}>
                        删除
                      </button>
                    </div>
                  </div>
                  {expanded && renderSectionTree(chapter, { showCheckbox: true, showDelete: true, isRootChapter: true })}
                </div>
              );
            })}
            {!activeChapterCategory && <div className="empty compact">请先新增类目，并在类目下维护章和节</div>}
          </div>
          {!scopedChapters.length && <div className="empty compact">暂无章 / 节</div>}
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
          <button className="button" type="button" onClick={beginPointImport} disabled={!selectedSubject}>
            导入知识点
          </button>
        </div>
        {pointImportOpen && (
          <div className="editorPanel">
            <div className="panelHeaderActions">
              <div>
                <strong>导入知识点</strong>
                <p className="muted">请按“章 / 节 / 知识点”结构粘贴 Markdown，保存后会自动绑定到当前类目下的对应章或节。</p>
              </div>
              <button className="button small" type="button" onClick={() => setPointImportOpen(false)}>
                取消
              </button>
            </div>
            <form className="formGrid" onSubmit={submitPointImport}>
              <label className="field">
                <span>Markdown 目录</span>
                <textarea rows={10} value={pointImportMarkdown} onChange={(event) => setPointImportMarkdown(event.target.value)} />
              </label>
              <div className="buttonRow">
                <button className="button primary" type="submit" disabled={importingPoints}>
                  {importingPoints ? "导入中..." : "导入"}
                </button>
              </div>
            </form>
          </div>
        )}
        <div className="metricTable">
          {rootPoints.map((point) => (
            <button key={point.id} className="listButton" type="button" onClick={() => beginEdit("point", point)}>
              <div>
                <strong>{point.name}</strong>
                <span className="muted">{point.description || point.path}</span>
                <span className="muted">
                  {[chapterName(point.chapter_id), categoryName(point.category_id), keywordPreview(point.keywords_json)].filter(Boolean).join(" / ")}
                </span>
              </div>
              <div className="badgeStack">
                <StatusBadge value={`${detailCountByPoint.get(point.id) || 0} 个详情`} tone="info" />
                <StatusBadge value={point.status} tone={point.status === "active" ? "good" : point.status === "draft" ? "warn" : "info"} />
              </div>
            </button>
          ))}
          {!rootPoints.length && <div className="empty compact">暂无知识点</div>}
        </div>
      </div>
    );
  }

  function renderPointDetails() {
    return (
      <div className="stackList">
        <div className="buttonRow">
          <button className="button primary" type="button" onClick={() => beginCreate("pointDetail")} disabled={!selectedSubject || !rootPoints.length}>
            新增知识点详情
          </button>
          <button className="button" type="button" onClick={beginPointDetailImport} disabled={!selectedSubject || !rootPoints.length}>
            导入知识点详情
          </button>
        </div>
        {pointDetailImportOpen && (
          <div className="editorPanel">
            <div className="panelHeaderActions">
              <div>
                <strong>导入知识点详情</strong>
                <p className="muted">请按“章 / 节 / 知识点 / 知识点详情”结构粘贴 Markdown，保存后会自动挂到当前类目下对应知识点。</p>
              </div>
              <button className="button small" type="button" onClick={() => setPointDetailImportOpen(false)}>
                取消
              </button>
            </div>
            <form className="formGrid" onSubmit={submitPointDetailImport}>
              <label className="field">
                <span>Markdown 目录</span>
                <textarea rows={10} value={pointDetailImportMarkdown} onChange={(event) => setPointDetailImportMarkdown(event.target.value)} />
              </label>
              <div className="buttonRow">
                <button className="button primary" type="submit" disabled={importingPointDetails}>
                  {importingPointDetails ? "导入中..." : "导入"}
                </button>
              </div>
            </form>
          </div>
        )}
        <div className="metricTable">
          {pointDetails.map((point) => (
            <button key={point.id} className="listButton" type="button" onClick={() => beginEdit("pointDetail", point)}>
              <div>
                <strong>{point.name}</strong>
                <span className="muted">{point.description || point.path}</span>
                <span className="muted">
                  {[pointById.get(point.parent_id || 0)?.name || "", chapterName(point.chapter_id), keywordPreview(point.keywords_json)].filter(Boolean).join(" / ")}
                </span>
              </div>
              <StatusBadge value={point.status} tone={point.status === "active" ? "good" : point.status === "draft" ? "warn" : "info"} />
            </button>
          ))}
          {!pointDetails.length && <div className="empty compact">暂无知识点详情</div>}
        </div>
      </div>
    );
  }

  function renderOverviewChapterTree(chapter: ChapterResponse, isRoot: boolean) {
    const childSections = childChaptersByParent.get(chapter.id) || [];
    const pointsInChapter = rootPointsByChapter.get(chapter.id) || [];
    const detailCount = pointsInChapter.reduce((total, point) => total + (detailCountByPoint.get(point.id) || 0), 0);
    const expanded = isRoot ? (selectedChapterRoot ? selectedChapterRoot.id === chapter.id : true) : true;
    const summary = isRoot
      ? `${childSections.length} 个节 · ${pointCountByChapterTree.get(chapter.id) || 0} 个知识点相关节点`
      : `${pointsInChapter.length} 个知识点 · ${detailCount} 个详情`;

    return (
      <article key={chapter.id} className={isRoot ? "directoryNode root" : "directoryNode section"}>
        <div className="directoryNodeHeader">
          <div className="directoryNodeTitle">
            <span className="chapterLevelPill section">{isRoot ? "章" : "节"}</span>
            <div>
              <strong>{chapter.name}</strong>
              <small>{summary}</small>
            </div>
          </div>
          <div className="directoryNodeTools">
            {!isRoot && <StatusBadge value={`${detailCount} 个详情`} tone={detailCount ? "good" : "info"} />}
            {isRoot && (
              <button className="button small" type="button" onClick={() => setSelectedChapterRootId(expanded ? null : chapter.id)}>
                {expanded ? "收起" : "展开"}
              </button>
            )}
          </div>
        </div>
        {expanded && (
          <div className="directoryNodeBody">
            {!!childSections.length && (
              <div className="directorySectionStack">
                {childSections.map((child) => renderOverviewChapterTree(child, false))}
              </div>
            )}
            {!!pointsInChapter.length && (
              <div className="directoryPointGrid">
                {pointsInChapter.map((point) => renderOverviewPointCard(point))}
              </div>
            )}
            {!childSections.length && !pointsInChapter.length && <div className="directoryNodeEmpty">当前层级下还没有知识点</div>}
          </div>
        )}
      </article>
    );
  }

  function renderOverviewPointCard(point: KnowledgePointResponse) {
    const details = pointDetailsByParent.get(point.id) || [];
    const preview = point.description || keywordPreview(point.keywords_json) || "暂无知识点说明";
    return (
      <article key={point.id} className="directoryPointCard">
        <div className="directoryPointHeader">
          <span className="chapterLevelPill point">知识点</span>
          <StatusBadge value={`${details.length} 个详情`} tone={details.length ? "good" : "info"} />
        </div>
        <strong className="directoryPointName">{point.name}</strong>
        <p className="directoryPointMeta">{preview}</p>
        {!!details.length && (
          <div className="directoryDetailList">
            {details.map((detail) => (
              <div key={detail.id} className="directoryDetailItem">
                <span className="directoryDetailLabel">详情</span>
                <strong>{detail.name}</strong>
                <small>{detail.description || keywordPreview(detail.keywords_json) || "暂无详情说明"}</small>
              </div>
            ))}
          </div>
        )}
      </article>
    );
  }

  function renderSectionTree(
    chapter: ChapterResponse,
    options: { showCheckbox: boolean; showDelete: boolean; isRootChapter?: boolean },
  ) {
    const childSections = childChaptersByParent.get(chapter.id) || [];
    const pointsInChapter = rootPointsByChapter.get(chapter.id) || [];
    const detailCount = pointsInChapter.reduce((total, point) => total + (detailCountByPoint.get(point.id) || 0), 0);

    return (
      <div key={chapter.id} className="chapterSectionTree">
        <div className="chapterSectionShell">
          {options.showCheckbox && (
            <label className="rowCheck chapterTreeCheck">
              <input
                type="checkbox"
                checked={selectedChapterIds.includes(chapter.id)}
                onChange={() => toggleChapterSelection(chapter.id)}
              />
            </label>
          )}
          <div className="chapterSectionCard">
            <div className="chapterSectionCardTop">
              <button className="chapterSectionCardButton" type="button" onClick={() => beginEdit("chapter", chapter)}>
                <div className="chapterSectionCardTitle">
                  <span className="chapterLevelPill section">{options.isRootChapter ? "章" : "节"}</span>
                  <div>
                    <strong>{chapter.name}</strong>
                    <small>{pointsInChapter.length} 个知识点 · {detailCount} 个详情</small>
                  </div>
                </div>
              </button>
              <div className="chapterNodeActions compact">
                <button className="button small" type="button" onClick={() => beginCreatePointForChapter(chapter)}>
                  新增知识点
                </button>
                {options.showDelete && (
                  <button className="button small danger" type="button" disabled={saving} onClick={() => deleteChapter(chapter)}>
                    删除
                  </button>
                )}
              </div>
            </div>
            {!!childSections.length && (
              <div className="chapterSectionList">
                {childSections.map((child) => renderSectionTree(child, { showCheckbox: true, showDelete: true, isRootChapter: false }))}
              </div>
            )}
            <div className="chapterTreeLane">
              {pointsInChapter.map((point) => {
                const details = pointDetailsByParent.get(point.id) || [];
                return (
                  <div key={point.id} className="chapterTreeNode">
                    <div className="chapterPointNode">
                      <button className="chapterTreeButton point" type="button" onClick={() => beginEdit("point", point)}>
                        <div className="chapterTreeButtonMain">
                          <span className="chapterLevelPill point">知识点</span>
                          <div>
                            <strong>{point.name}</strong>
                            <small>{point.description || keywordPreview(point.keywords_json) || "点击编辑知识点说明"}</small>
                          </div>
                        </div>
                        <div className="badgeStack">
                          <StatusBadge value={`${details.length} 个详情`} tone="good" />
                        </div>
                      </button>
                      <div className="chapterNodeActions compact">
                        <button className="button small" type="button" onClick={() => beginCreatePointDetailForPoint(point)}>
                          新增详情
                        </button>
                      </div>
                    </div>
                    {!!details.length && (
                      <div className="chapterDetailLane">
                        {details.map((detail) => (
                          <button key={detail.id} className="chapterTreeButton detail" type="button" onClick={() => beginEdit("pointDetail", detail)}>
                            <div className="chapterTreeButtonMain">
                              <span className="chapterLevelPill detail">详情</span>
                              <div>
                                <strong>{detail.name}</strong>
                                <small>{detail.description || keywordPreview(detail.keywords_json) || "点击编辑详情说明"}</small>
                              </div>
                            </div>
                          </button>
                        ))}
                      </div>
                    )}
                  </div>
                );
              })}
              {!pointsInChapter.length && !childSections.length && <div className="empty compact">当前层级下还没有知识点</div>}
            </div>
          </div>
        </div>
      </div>
    );
  }

  function updatePointCategory(categoryId: string) {
    const numericCategoryId = toNullableNumber(categoryId);
    if (!numericCategoryId) {
      setPointForm((current) => ({ ...current, category_id: "", chapter_id: "", path: "" }));
      return;
    }
    const nextOptions = bindableChaptersByCategory.get(numericCategoryId) || [];
    setPointForm((current) => {
      const currentChapterId = toNullableNumber(current.chapter_id);
      const nextChapterId = nextOptions.some((chapter) => chapter.id === currentChapterId)
        ? current.chapter_id
        : (nextOptions[0] ? String(nextOptions[0].id) : "");
      return {
        ...current,
        category_id: categoryId,
        chapter_id: nextChapterId,
        path: "",
      };
    });
  }

  function updatePointDetailParent(parentId: string, currentItem: KnowledgePointResponse | null) {
    const selectedParent = rootPoints.find((point) => point.id === toNullableNumber(parentId)) || null;
    setPointForm((current) => ({
      ...current,
      parent_id: parentId,
      category_id: selectedParent?.category_id ? String(selectedParent.category_id) : "",
      chapter_id: selectedParent?.chapter_id ? String(selectedParent.chapter_id) : "",
      path: selectedParent && currentItem?.parent_id !== selectedParent.id ? "" : current.path,
    }));
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
  const label = type === "subject"
    ? "学科"
    : type === "category"
      ? "类目"
      : type === "chapter"
          ? "章 / 节"
          : type === "pointDetail"
            ? "知识点详情"
            : "知识点";
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
