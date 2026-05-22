"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { BookOpenCheck, CircleHelp, FileStack, RotateCcw, Shuffle } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { LoadState } from "../../components/shared/LoadState";
import { StatusBadge } from "../../components/shared/StatusBadge";
import {
  apiFetch,
  ChapterResponse,
  MasterySnapshotResponse,
  PracticeDerivedSessionRequest,
  PracticeSessionCreateRequest,
  PracticeSessionDetailResponse,
  PracticeSessionSummaryResponse,
  QuestionBankExportPaperOptionResponse,
  ReviewDueItemResponse,
  SubjectCategoryResponse,
  SubjectResponse,
} from "../../lib/pro-api";
import { toErrorMessage } from "../../lib/request-guard";

type SessionType = "chapter" | "random" | "paper" | "wrong_book";
type AnswerMode = "memorize" | "exam";

const sessionTypeOptions: Array<{ value: SessionType; label: string; description: string; icon: typeof BookOpenCheck }> = [
  { value: "chapter", label: "章节知识点刷题", description: "按章节筛选正式题库，适合系统复习。", icon: BookOpenCheck },
  { value: "random", label: "乱序刷题", description: "按学科或类目随机抽题，适合日常巩固。", icon: Shuffle },
  { value: "paper", label: "套卷刷题", description: "按来源试卷顺序出题，保留套卷练习节奏。", icon: FileStack },
  { value: "wrong_book", label: "错题模式", description: "优先重练未掌握错题，适合查漏补缺。", icon: RotateCcw },
];

const answerModeOptions: Array<{ value: AnswerMode; label: string; description: string }> = [
  { value: "memorize", label: "背记模式", description: "每题答完立即看答案和解析。" },
  { value: "exam", label: "模拟模式", description: "全部做完后统一交卷看答案。" },
];

const questionTypeOptions = [
  { value: "", label: "全部题型" },
  { value: "single_choice", label: "单选题" },
  { value: "multiple_choice", label: "多选题" },
  { value: "judge", label: "判断题" },
  { value: "fill_blank", label: "填空题" },
  { value: "short_answer", label: "简答题" },
  { value: "calculation", label: "计算题" },
  { value: "case_analysis", label: "案例分析题" },
  { value: "material_analysis", label: "材料分析题" },
  { value: "mixed", label: "混合题型" },
];

export default function PracticeHomePage() {
  const router = useRouter();
  const [subjects, setSubjects] = useState<SubjectResponse[]>([]);
  const [categories, setCategories] = useState<SubjectCategoryResponse[]>([]);
  const [chapters, setChapters] = useState<ChapterResponse[]>([]);
  const [papers, setPapers] = useState<QuestionBankExportPaperOptionResponse[]>([]);
  const [recentSessions, setRecentSessions] = useState<PracticeSessionSummaryResponse[]>([]);
  const [reviewToday, setReviewToday] = useState<ReviewDueItemResponse[]>([]);
  const [mastery, setMastery] = useState<MasterySnapshotResponse[]>([]);
  const [sessionType, setSessionType] = useState<SessionType>("chapter");
  const [answerMode, setAnswerMode] = useState<AnswerMode>("memorize");
  const [subjectId, setSubjectId] = useState("");
  const [categoryId, setCategoryId] = useState("");
  const [chapterId, setChapterId] = useState("");
  const [paperId, setPaperId] = useState("");
  const [questionType, setQuestionType] = useState("");
  const [questionCount, setQuestionCount] = useState(20);
  const [loading, setLoading] = useState(true);
  const [starting, setStarting] = useState(false);
  const [startingReviewToday, setStartingReviewToday] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    void loadInitialData();
  }, []);

  useEffect(() => {
    if (!subjects.length || subjectId) return;
    setSubjectId(String(subjects[0].id));
  }, [subjectId, subjects]);

  useEffect(() => {
    const currentCategories = scopedCategories(subjects, categories, subjectId);
    if (!currentCategories.length) {
      setCategoryId("");
      return;
    }
    if (!categoryId || !currentCategories.some((item) => String(item.id) === categoryId)) {
      setCategoryId(String(currentCategories[0].id));
    }
  }, [categories, categoryId, subjectId, subjects]);

  useEffect(() => {
    const currentChapters = scopedChapters(chapters, subjectId, categoryId);
    if (!currentChapters.length) {
      setChapterId("");
      return;
    }
    if (!chapterId || !currentChapters.some((item) => String(item.id) === chapterId)) {
      setChapterId(String(currentChapters[0].id));
    }
  }, [chapterId, categoryId, chapters, subjectId]);

  const availableCategories = useMemo(() => scopedCategories(subjects, categories, subjectId), [categories, subjectId, subjects]);
  const availableChapters = useMemo(() => scopedChapters(chapters, subjectId, categoryId), [categoryId, chapters, subjectId]);

  async function loadInitialData() {
    setLoading(true);
    setError("");
    try {
      const [
        subjectPayload,
        categoryPayload,
        chapterPayload,
        paperPayload,
        sessionPayload,
        reviewTodayPayload,
        masteryPayload,
      ] = await Promise.all([
        apiFetch<SubjectResponse[]>("/api/knowledge/subjects"),
        apiFetch<SubjectCategoryResponse[]>("/api/knowledge/categories"),
        apiFetch<ChapterResponse[]>("/api/knowledge/chapters"),
        apiFetch<QuestionBankExportPaperOptionResponse[]>("/api/question-bank/export/papers"),
        apiFetch<PracticeSessionSummaryResponse[]>("/api/learning/sessions?limit=8"),
        apiFetch<ReviewDueItemResponse[]>("/api/learning/review-today?limit=8"),
        apiFetch<MasterySnapshotResponse[]>("/api/learning/mastery?limit=8"),
      ]);
      setSubjects(subjectPayload);
      setCategories(categoryPayload);
      setChapters(chapterPayload);
      setPapers(paperPayload);
      setRecentSessions(sessionPayload);
      setReviewToday(reviewTodayPayload);
      setMastery(masteryPayload);
    } catch (err) {
      setError(toErrorMessage(err, "加载练习数据失败"));
    } finally {
      setLoading(false);
    }
  }

  async function startPractice() {
    setStarting(true);
    setError("");
    try {
      const payload: PracticeSessionCreateRequest = {
        session_type: sessionType,
        answer_mode: answerMode,
        subject_id: subjectId ? Number(subjectId) : null,
        category_id: categoryId ? Number(categoryId) : null,
        chapter_id: sessionType === "chapter" && chapterId ? Number(chapterId) : null,
        paper_id: sessionType === "paper" && paperId ? Number(paperId) : null,
        question_type: questionType || null,
        question_count: questionCount,
      };
      const detail = await apiFetch<PracticeSessionDetailResponse>("/api/learning/sessions", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      router.push(`/practice/session/${detail.id}`);
    } catch (err) {
      setError(toErrorMessage(err, "创建练习失败"));
    } finally {
      setStarting(false);
    }
  }

  async function startTodayReview() {
    setStartingReviewToday(true);
    setError("");
    try {
      const payload: PracticeDerivedSessionRequest = {
        answer_mode: "memorize",
        question_count: Math.min(Math.max(reviewToday.length, 1), 20),
      };
      const detail = await apiFetch<PracticeSessionDetailResponse>("/api/learning/review-today/start", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      router.push(`/practice/session/${detail.id}`);
    } catch (err) {
      setError(toErrorMessage(err, "创建今日复习失败"));
    } finally {
      setStartingReviewToday(false);
    }
  }

  return (
    <div className="practiceHome">
      <div className="pageHeader">
        <div>
          <h1>刷题练习</h1>
          <p>题目直接来自正式题库，学习域只做单向引用，不反向改动题库数据。先把章节、乱序、套卷、错题四个入口跑通，再继续往更高级的推荐和复习策略扩展。</p>
        </div>
        <div className="practiceHeaderActions">
          <Link className="button" href="/practice/plan">每日计划</Link>
          <Link className="button" href="/question-bank">查看正式题库</Link>
        </div>
      </div>

      <LoadState loading={loading} error={error} />
      {!loading && !error && (
        <div className="practiceHomeGrid">
          <section className="panel">
            <div className="panelHeader">
              <h2>开始练习</h2>
              <p>先选练习入口和答题模式，再从正式题库抽题生成会话。</p>
            </div>
            <div className="panelBody formGrid">
              <div className="practiceModeGrid">
                {sessionTypeOptions.map((item) => {
                  const Icon = item.icon;
                  const active = sessionType === item.value;
                  return (
                    <button
                      key={item.value}
                      className={active ? "practiceModeCard active" : "practiceModeCard"}
                      type="button"
                      onClick={() => setSessionType(item.value)}
                    >
                      <Icon size={18} />
                      <strong>{item.label}</strong>
                      <span>{item.description}</span>
                    </button>
                  );
                })}
              </div>

              <div className="tabs">
                {answerModeOptions.map((item) => (
                  <button
                    key={item.value}
                    className={answerMode === item.value ? "tab active" : "tab"}
                    type="button"
                    onClick={() => setAnswerMode(item.value)}
                  >
                    <strong>{item.label}</strong>
                    <span>{item.description}</span>
                  </button>
                ))}
              </div>

              <div className="row">
                <div className="field">
                  <label>学科</label>
                  <select value={subjectId} onChange={(event) => setSubjectId(event.target.value)}>
                    {!subjects.length && <option value="">暂无学科</option>}
                    {subjects.map((item) => (
                      <option key={item.id} value={item.id}>
                        {item.name}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="field">
                  <label>类目</label>
                  <select value={categoryId} onChange={(event) => setCategoryId(event.target.value)} disabled={!availableCategories.length}>
                    {!availableCategories.length && <option value="">暂无类目</option>}
                    {availableCategories.map((item) => (
                      <option key={item.id} value={item.id}>
                        {item.name}
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              <div className="row">
                <div className="field">
                  <label>章节</label>
                  <select
                    value={chapterId}
                    onChange={(event) => setChapterId(event.target.value)}
                    disabled={sessionType !== "chapter" || !availableChapters.length}
                  >
                    {!availableChapters.length && <option value="">暂无章节</option>}
                    {availableChapters.map((item) => (
                      <option key={item.id} value={item.id}>
                        {item.path}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="field">
                  <label>来源试卷</label>
                  <select value={paperId} onChange={(event) => setPaperId(event.target.value)} disabled={sessionType !== "paper"}>
                    <option value="">请选择试卷</option>
                    {papers.map((item) => (
                      <option key={item.paper_id} value={item.paper_id}>
                        {item.paper_name} · {item.question_count} 题
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              <div className="row">
                <div className="field">
                  <label>题型</label>
                  <select value={questionType} onChange={(event) => setQuestionType(event.target.value)}>
                    {questionTypeOptions.map((item) => (
                      <option key={item.value || "all"} value={item.value}>
                        {item.label}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="field">
                  <label>题量</label>
                  <input
                    type="number"
                    min={1}
                    max={100}
                    value={questionCount}
                    onChange={(event) => setQuestionCount(Number(event.target.value) || 1)}
                  />
                </div>
              </div>

              <div className="calloutBox">
                <CircleHelp size={16} />
                {answerMode === "memorize"
                  ? "背记模式会在每题保存后立刻显示答案和解析，适合边刷边记。"
                  : "模拟模式会隐藏答案直到全部做完并交卷，答题卡可跳题但不会提前透题。"}
              </div>

              <div className="buttonRow">
                <button className="button primary" type="button" disabled={starting} onClick={startPractice}>
                  {starting ? "正在生成练习..." : "开始练习"}
                </button>
                <button className="button" type="button" disabled={loading || starting} onClick={() => void loadInitialData()}>
                  刷新数据
                </button>
              </div>
            </div>
          </section>

          <div className="practiceSideGrid">
            <section className="panel">
              <div className="panelHeader">
                <h2>今日待复习</h2>
                <p>按错题节奏自动汇总今天该回顾的题，适合顺手做一轮回炉。</p>
              </div>
              <div className="panelBody practiceListStack">
                <div className="buttonRow">
                  <button className="button primary" type="button" disabled={!reviewToday.length || startingReviewToday} onClick={startTodayReview}>
                    {startingReviewToday ? "正在生成复习..." : `开始今日复习${reviewToday.length ? ` · ${reviewToday.length} 题` : ""}`}
                  </button>
                </div>
                {!reviewToday.length && <div className="empty compact">今天没有待复习错题。</div>}
                {reviewToday.map((item) => (
                  <div key={item.id} className="practiceWrongCard">
                    <div>
                      <strong>{item.stem_text}</strong>
                      <span>{item.due_reason}</span>
                    </div>
                    <div className="practiceWrongMeta">
                      <StatusBadge value={`错 ${item.wrong_count} 次`} tone="warn" />
                      <small>{formatTime(item.due_at)}</small>
                    </div>
                  </div>
                ))}
              </div>
            </section>

            <section className="panel">
              <div className="panelHeader">
                <h2>最近练习</h2>
                <p>继续上次未完成的会话，或者回看刚交卷的结果。</p>
              </div>
              <div className="panelBody practiceListStack">
                {!recentSessions.length && <div className="empty compact">还没有练习记录，先开始一组题吧。</div>}
                {recentSessions.map((item) => (
                  <Link key={item.id} className="practiceListCard" href={`/practice/session/${item.id}`}>
                    <div>
                      <strong>{item.title}</strong>
                      <span>{sessionLabel(item.session_type)} · {modeLabel(item.answer_mode)}</span>
                    </div>
                    <div className="practiceListMeta">
                      <StatusBadge
                        value={item.status === "submitted" ? `${item.correct_count}/${item.total_count}` : `${item.answered_count}/${item.total_count}`}
                        tone={item.status === "submitted" ? "good" : "info"}
                      />
                      <small>{formatTime(item.created_at)}</small>
                    </div>
                  </Link>
                ))}
              </div>
            </section>

            <section className="panel">
              <div className="panelHeader">
                <h2>薄弱知识点</h2>
                <p>按最近练习累计掌握度排序，分数越低越该优先补。</p>
              </div>
              <div className="panelBody practiceListStack">
                {!mastery.length && <div className="empty compact">完成交卷后，这里会开始累计知识点掌握度。</div>}
                {mastery.map((item) => (
                  <div key={item.knowledge_point_id} className="practiceWrongCard">
                    <div>
                      <strong>{item.name}</strong>
                      <span>{item.path}</span>
                    </div>
                    <div className="practiceWrongMeta">
                      <StatusBadge value={`${item.mastery_score}%`} tone={item.mastery_score >= 80 ? "good" : item.mastery_score >= 60 ? "warn" : "danger"} />
                      <small>{item.correct_count}/{item.answered_count}</small>
                    </div>
                  </div>
                ))}
              </div>
            </section>
          </div>
        </div>
      )}
    </div>
  );
}

function scopedCategories(
  subjects: SubjectResponse[],
  categories: SubjectCategoryResponse[],
  subjectId: string,
) {
  if (!subjectId) return categories;
  const subjectExists = subjects.some((item) => String(item.id) === subjectId);
  if (!subjectExists) return categories;
  return categories.filter((item) => String(item.subject_id) === subjectId);
}

function scopedChapters(chapters: ChapterResponse[], subjectId: string, categoryId: string) {
  return chapters.filter((item) => {
    if (subjectId && String(item.subject_id) !== subjectId) return false;
    if (categoryId && String(item.category_id || "") !== categoryId) return false;
    return true;
  });
}

function sessionLabel(value: SessionType) {
  return sessionTypeOptions.find((item) => item.value === value)?.label || value;
}

function modeLabel(value: AnswerMode) {
  return answerModeOptions.find((item) => item.value === value)?.label || value;
}

function formatTime(value: string) {
  try {
    return new Date(value).toLocaleString("zh-CN", { hour12: false });
  } catch {
    return value;
  }
}
