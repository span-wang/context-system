"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";

import { LoadState } from "../../../../components/shared/LoadState";
import { StatusBadge } from "../../../../components/shared/StatusBadge";
import {
  apiFetch,
  PracticeAnswerSubmitRequest,
  PracticeDerivedSessionRequest,
  PracticeSessionDetailResponse,
  PracticeSessionItemResponse,
} from "../../../../lib/pro-api";
import {
  formatDuration,
  formatPracticeAnswer,
  formatShortDuration,
  modeLabel,
  optionKey,
  questionTypeLabel,
  sessionLabel,
} from "../../../../lib/practice";
import { toErrorMessage } from "../../../../lib/request-guard";

export default function PracticeSessionPage() {
  const params = useParams<{ sessionId: string }>();
  const sessionId = Number(params.sessionId || 0);
  const [detail, setDetail] = useState<PracticeSessionDetailResponse | null>(null);
  const [selectedItemId, setSelectedItemId] = useState<number | null>(null);
  const [answerDraft, setAnswerDraft] = useState("");
  const [marked, setMarked] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [derivingAction, setDerivingAction] = useState<"" | "retry" | "similar">("");
  const [error, setError] = useState("");
  const [actionMessage, setActionMessage] = useState("");
  const [nowTick, setNowTick] = useState(() => Date.now());
  const spentDraftRef = useRef<Record<number, number>>({});
  const activeTrackedItemIdRef = useRef<number | null>(null);
  const activeStartedAtRef = useRef<number | null>(null);

  useEffect(() => {
    spentDraftRef.current = {};
    activeTrackedItemIdRef.current = null;
    activeStartedAtRef.current = null;
  }, [sessionId]);

  useEffect(() => {
    if (!sessionId) return;
    void loadSession();
  }, [sessionId]);

  useEffect(() => {
    if (!detail?.items.length) {
      setSelectedItemId(null);
      return;
    }
    if (selectedItemId && detail.items.some((item) => item.id === selectedItemId)) {
      return;
    }
    const nextItem = detail.items.find((item) => !item.is_answered) || detail.items[0];
    setSelectedItemId(nextItem.id);
  }, [detail, selectedItemId]);

  const activeItem = useMemo(
    () => detail?.items.find((item) => item.id === selectedItemId) || null,
    [detail, selectedItemId],
  );

  useEffect(() => {
    if (!activeItem) {
      setAnswerDraft("");
      setMarked(false);
      return;
    }
    setAnswerDraft(activeItem.user_answer || "");
    setMarked(activeItem.marked);
  }, [activeItem]);

  useEffect(() => {
    const now = Date.now();
    syncTrackedSpentSeconds(now);
    activeTrackedItemIdRef.current = activeItem?.id ?? null;
    activeStartedAtRef.current = activeItem && detail?.status !== "submitted" ? now : null;
  }, [activeItem?.id, detail?.items, detail?.status]);

  useEffect(() => {
    if (!activeItem || detail?.status === "submitted") return;
    setNowTick(Date.now());
    const timer = window.setInterval(() => setNowTick(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [activeItem?.id, detail?.status]);

  const activeIndex = activeItem && detail ? detail.items.findIndex((item) => item.id === activeItem.id) : -1;
  const activeSpentSeconds = activeItem ? getSpentSeconds(activeItem, nowTick) : 0;
  const markedCount = useMemo(() => {
    if (!detail) return 0;
    return detail.items.reduce((count, item) => {
      const itemMarked = item.id === activeItem?.id ? marked : item.marked;
      return count + (itemMarked ? 1 : 0);
    }, 0);
  }, [detail, activeItem?.id, marked]);
  const nextPendingItemId = detail && activeItem ? findNextPendingItemId(detail, activeItem.id) : null;
  const nextItemId = detail && activeItem ? findAdjacentItemId(detail, activeItem.id, 1) : null;

  async function loadSession() {
    setLoading(true);
    setError("");
    try {
      const payload = await apiFetch<PracticeSessionDetailResponse>(`/api/learning/sessions/${sessionId}`);
      setDetail(payload);
    } catch (err) {
      setError(toErrorMessage(err, "加载练习详情失败"));
    } finally {
      setLoading(false);
    }
  }

  function getBaseSpentSeconds(item: PracticeSessionItemResponse) {
    const draft = spentDraftRef.current[item.id];
    return typeof draft === "number" ? draft : item.spent_seconds || 0;
  }

  function getSpentSeconds(item: PracticeSessionItemResponse, now = Date.now()) {
    const base = getBaseSpentSeconds(item);
    if (detail?.status === "submitted" || activeTrackedItemIdRef.current !== item.id || activeStartedAtRef.current === null) {
      return base;
    }
    return base + Math.max(Math.floor((now - activeStartedAtRef.current) / 1000), 0);
  }

  function syncTrackedSpentSeconds(now = Date.now()) {
    const trackedItemId = activeTrackedItemIdRef.current;
    const startedAt = activeStartedAtRef.current;
    if (!trackedItemId || startedAt === null) return;
    const trackedItem = detail?.items.find((item) => item.id === trackedItemId);
    if (!trackedItem) {
      activeStartedAtRef.current = now;
      return;
    }
    const elapsed = Math.floor((now - startedAt) / 1000);
    if (elapsed > 0) {
      spentDraftRef.current[trackedItemId] = getBaseSpentSeconds(trackedItem) + elapsed;
    }
    activeStartedAtRef.current = now;
  }

  async function saveAnswer(advanceAfterSave = false) {
    if (!activeItem) return;
    const now = Date.now();
    const spentSeconds = getSpentSeconds(activeItem, now);
    spentDraftRef.current[activeItem.id] = spentSeconds;
    activeStartedAtRef.current = now;
    setSaving(true);
    setError("");
    setActionMessage("");
    try {
      const payload: PracticeAnswerSubmitRequest = {
        item_id: activeItem.id,
        answer: answerDraft || null,
        spent_seconds: spentSeconds,
        marked,
      };
      const nextDetail = await apiFetch<PracticeSessionDetailResponse>(`/api/learning/sessions/${sessionId}/answer`, {
        method: "POST",
        body: JSON.stringify(payload),
      });
      const savedItem = nextDetail.items.find((item) => item.id === activeItem.id);
      if (savedItem) {
        spentDraftRef.current[activeItem.id] = savedItem.spent_seconds || spentSeconds;
      }
      setDetail(nextDetail);
      if (advanceAfterSave && nextDetail.answer_mode === "exam") {
        const targetItemId = findNextPendingItemId(nextDetail, activeItem.id) || findAdjacentItemId(nextDetail, activeItem.id, 1);
        if (targetItemId) {
          setSelectedItemId(targetItemId);
          setActionMessage("已保存，已切换到下一题。");
          return;
        }
      }
      setActionMessage(nextDetail.answer_mode === "memorize" ? "已保存，本题结果已更新。" : "已保存答案。");
    } catch (err) {
      setError(toErrorMessage(err, "保存答案失败"));
    } finally {
      setSaving(false);
    }
  }

  async function submitSession() {
    setSubmitting(true);
    setError("");
    setActionMessage("");
    try {
      await apiFetch<PracticeSessionDetailResponse>(`/api/learning/sessions/${sessionId}/submit`, {
        method: "POST",
      });
      window.location.href = `/practice/result/${sessionId}`;
    } catch (err) {
      setError(toErrorMessage(err, "交卷失败"));
    } finally {
      setSubmitting(false);
    }
  }

  async function startDerivedPractice(kind: "retry" | "similar") {
    setDerivingAction(kind);
    setError("");
    setActionMessage("");
    try {
      const payload: PracticeDerivedSessionRequest = {
        answer_mode: "memorize",
        question_count: kind === "retry" ? Math.min(Math.max(detail?.retry_wrong_count || 1, 1), 20) : 10,
      };
      const path =
        kind === "retry"
          ? `/api/learning/sessions/${sessionId}/retry-wrong`
          : `/api/learning/sessions/${sessionId}/similar-practice`;
      const nextDetail = await apiFetch<PracticeSessionDetailResponse>(path, {
        method: "POST",
        body: JSON.stringify(payload),
      });
      window.location.href = `/practice/session/${nextDetail.id}`;
    } catch (err) {
      setError(toErrorMessage(err, kind === "retry" ? "创建错题重练失败" : "创建同类题再练失败"));
    } finally {
      setDerivingAction("");
    }
  }

  function moveQuestion(offset: number) {
    if (!detail?.items.length || !activeItem) return;
    const nextIndex = activeIndex + offset;
    if (nextIndex < 0 || nextIndex >= detail.items.length) return;
    setSelectedItemId(detail.items[nextIndex].id);
  }

  return (
    <div className="practiceSessionPage">
      <div className="pageHeader">
        <div>
          <h1>{detail?.title || "练习会话"}</h1>
          <p>模拟模式会在交卷前隐藏答案；背记模式会在每题保存后立即显示结果和解析。答题卡可以随时跳题。</p>
        </div>
        <div className="practiceHeaderActions">
          {detail?.status === "submitted" && <Link className="button" href={`/practice/result/${sessionId}`}>查看结果页</Link>}
          <Link className="button" href="/practice">返回练习首页</Link>
        </div>
      </div>

      <LoadState loading={loading} error={error} />
      {!loading && !error && detail && (
        <div className="practiceSessionGrid">
          <section className="panel practiceSessionMain">
            <div className="panelHeader panelHeaderActions">
              <div>
                <h2>当前练习</h2>
                <p>{sessionLabel(detail.session_type)} · {modeLabel(detail.answer_mode)} · {detail.answered_count}/{detail.total_count} 已作答</p>
              </div>
              <div className="buttonRow">
                <StatusBadge value={detail.status === "submitted" ? `${detail.correct_count}/${detail.total_count}` : `${detail.incomplete_count} 题未完成`} tone={detail.status === "submitted" ? "good" : "warn"} />
                <button className="button" type="button" disabled={!activeItem || saving} onClick={() => moveQuestion(-1)}>上一题</button>
                <button className="button" type="button" disabled={!activeItem || saving} onClick={() => moveQuestion(1)}>下一题</button>
                <button className="button primary" type="button" disabled={!detail.can_submit || submitting} onClick={submitSession}>
                  {submitting ? "正在交卷..." : detail.status === "submitted" ? "已交卷" : "交卷"}
                </button>
              </div>
            </div>

            <div className="panelBody practiceQuestionBody">
              <div className="practiceSessionStatGrid">
                <div className="practiceSessionStatCard">
                  <span>已作答</span>
                  <strong>{detail.answered_count}/{detail.total_count}</strong>
                </div>
                <div className="practiceSessionStatCard">
                  <span>已标记</span>
                  <strong>{markedCount} 题</strong>
                </div>
                <div className="practiceSessionStatCard">
                  <span>未完成</span>
                  <strong>{detail.incomplete_count} 题</strong>
                </div>
                <div className="practiceSessionStatCard">
                  <span>{detail.status === "submitted" ? "本题用时" : "当前停留"}</span>
                  <strong>{formatShortDuration(activeSpentSeconds)}</strong>
                </div>
              </div>

              {actionMessage && <div className="calloutBox">{actionMessage}</div>}
              {!activeItem && <div className="empty compact">当前没有题目。</div>}
              {activeItem && (
                <>
                  <div className="practiceQuestionMeta">
                    <strong>第 {activeItem.sort_order} 题</strong>
                    <div className="practiceTagRow">
                      <StatusBadge value={questionTypeLabel(activeItem.question.question_type)} tone="info" />
                      {activeItem.question.source_question_no && <StatusBadge value={`原题 ${activeItem.question.source_question_no}`} />}
                      {activeItem.question.source_paper_name && <StatusBadge value={activeItem.question.source_paper_name} />}
                      {marked && <StatusBadge value="已标记" tone="warn" />}
                    </div>
                  </div>

                  {activeItem.question.material_text && (
                    <div className="practiceQuestionBlock">
                      <strong>材料</strong>
                      <p>{activeItem.question.material_text}</p>
                    </div>
                  )}

                  {activeItem.question.group_stem && activeItem.question.group_stem !== activeItem.question.stem_text && (
                    <div className="practiceQuestionBlock">
                      <strong>题组导语</strong>
                      <p>{activeItem.question.group_stem}</p>
                    </div>
                  )}

                  <div className="practiceQuestionBlock">
                    <strong>题目</strong>
                    <p>{activeItem.question.stem_text}</p>
                  </div>

                  {!!activeItem.question.knowledge_points.length && (
                    <div className="practiceKnowledgeRow">
                      {activeItem.question.knowledge_points.map((point) => (
                        <span key={`${point.id}-${point.relation_type}`} className="chip">
                          {point.name}
                        </span>
                      ))}
                    </div>
                  )}

                  <div className="practiceAnswerArea">
                    {renderAnswerEditor(activeItem, answerDraft, setAnswerDraft)}
                    <label className="checkLine">
                      <input type="checkbox" checked={marked} onChange={(event) => setMarked(event.target.checked)} />
                      标记这题稍后复查
                    </label>
                    <div className="buttonRow">
                      <button
                        className="button primary"
                        type="button"
                        disabled={detail.status === "submitted" || saving}
                        onClick={() => void saveAnswer(false)}
                      >
                        {saving ? "正在保存..." : "保存答案"}
                      </button>
                      {detail.answer_mode === "exam" && (
                        <button
                          className="button"
                          type="button"
                          disabled={detail.status === "submitted" || saving || (!nextPendingItemId && !nextItemId)}
                          onClick={() => void saveAnswer(true)}
                        >
                          保存并继续
                        </button>
                      )}
                    </div>
                  </div>

                  {activeItem.show_result && (
                    <div className="practiceResultPanel">
                      <div className="practiceResultHeader">
                        <div className="practiceTagRow">
                          <StatusBadge
                            value={resultLabel(activeItem.is_correct)}
                            tone={activeItem.is_correct === true ? "good" : activeItem.is_correct === false ? "danger" : "warn"}
                          />
                          {activeItem.marked && <StatusBadge value="已标记" tone="warn" />}
                        </div>
                        <span>本题用时 {formatShortDuration(activeItem.spent_seconds)}</span>
                      </div>
                      <div className="practiceResultAnswerGrid">
                        <div className="practiceQuestionBlock">
                          <strong>你的答案</strong>
                          <p>{formatPracticeAnswer(activeItem.question, activeItem.user_answer)}</p>
                        </div>
                        <div className="practiceQuestionBlock">
                          <strong>正确答案</strong>
                          <p>{activeItem.question.answer_text ? formatPracticeAnswer(activeItem.question, activeItem.question.answer_text) : "当前题目暂无标准答案"}</p>
                        </div>
                      </div>
                      <div className="practiceQuestionBlock">
                        <strong>解析</strong>
                        <p>{activeItem.question.analysis_text || "当前题目暂无解析"}</p>
                      </div>
                    </div>
                  )}
                </>
              )}
            </div>
          </section>

          <aside className="panel practiceAnswerSheetPanel">
            <div className="panelHeader">
              <h2>答题卡</h2>
              <p>点击题号跳转。标记题会单独高亮，模拟模式交卷后会显示对错状态。</p>
            </div>
            <div className="panelBody">
              <div className="practiceSheetLegend">
                <span><i className="practiceLegendDot answered" />已作答</span>
                <span><i className="practiceLegendDot marked" />已标记</span>
                {detail.status === "submitted" && <span><i className="practiceLegendDot wrong" />错题</span>}
              </div>
              <div className="practiceAnswerSheet">
                {detail.items.map((item) => {
                  const sheetItem = item.id === activeItem?.id ? { ...item, marked } : item;
                  return (
                    <button
                      key={item.id}
                      className={answerSheetClassName(sheetItem, selectedItemId === item.id)}
                      type="button"
                      onClick={() => setSelectedItemId(item.id)}
                    >
                      {item.sort_order}
                    </button>
                  );
                })}
              </div>
              {detail.status === "submitted" && (
                <div className="practiceResultSummary">
                  <div>
                    <strong>正确率</strong>
                    <span>{detail.accuracy_rate ?? 0}%</span>
                  </div>
                  <div>
                    <strong>正确题数</strong>
                    <span>{detail.correct_count}</span>
                  </div>
                  <div>
                    <strong>用时</strong>
                    <span>{formatDuration(detail.duration_seconds)}</span>
                  </div>
                </div>
              )}

              {detail.status === "submitted" && (
                <div className="practiceAfterActions">
                  <button
                    className="button primary"
                    type="button"
                    disabled={!detail.retry_wrong_count || derivingAction !== ""}
                    onClick={() => void startDerivedPractice("retry")}
                  >
                    {derivingAction === "retry" ? "正在生成..." : `只重做错题${detail.retry_wrong_count ? ` · ${detail.retry_wrong_count} 题` : ""}`}
                  </button>
                  <button
                    className="button"
                    type="button"
                    disabled={!detail.similar_practice_available || derivingAction !== ""}
                    onClick={() => void startDerivedPractice("similar")}
                  >
                    {derivingAction === "similar" ? "正在生成..." : "同类题再练 10 题"}
                  </button>
                  <div className="calloutBox">
                    今日待复习 {detail.today_review_count} 题。返回练习首页可以直接开始今天该回顾的一轮。
                  </div>
                </div>
              )}

              {detail.status === "submitted" && !!detail.weak_points.length && (
                <div className="practiceWeakPointPanel">
                  <strong>本次练习后优先复习这些知识点</strong>
                  <div className="practiceWeakPointList">
                    {detail.weak_points.map((item) => (
                      <div key={item.knowledge_point_id} className="practiceWeakPointCard">
                        <div>
                          <strong>{item.name}</strong>
                          <span>{item.path}</span>
                        </div>
                        <StatusBadge
                          value={`${item.mastery_score}%`}
                          tone={item.mastery_score >= 80 ? "good" : item.mastery_score >= 60 ? "warn" : "danger"}
                        />
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </aside>
        </div>
      )}
    </div>
  );
}

function renderAnswerEditor(
  item: PracticeSessionItemResponse,
  answerDraft: string,
  setAnswerDraft: (value: string) => void,
) {
  const questionType = item.question.question_type;
  const options = item.question.options_json || [];

  if (questionType === "single_choice" || questionType === "judge") {
    return (
      <div className="practiceOptionList">
        {options.map((option, index) => {
          const value = optionKey(option, index);
          return (
            <label key={`${value}-${index}`} className={answerDraft === value ? "practiceOption active" : "practiceOption"}>
              <input
                type="radio"
                name={`answer-${item.id}`}
                checked={answerDraft === value}
                onChange={() => setAnswerDraft(value)}
              />
              <span>{option}</span>
            </label>
          );
        })}
      </div>
    );
  }

  if (questionType === "multiple_choice") {
    const selectedValues = new Set(
      answerDraft
        .split(",")
        .map((itemValue) => itemValue.trim())
        .filter(Boolean),
    );
    return (
      <div className="practiceOptionList">
        {options.map((option, index) => {
          const value = optionKey(option, index);
          const checked = selectedValues.has(value);
          return (
            <label key={`${value}-${index}`} className={checked ? "practiceOption active" : "practiceOption"}>
              <input
                type="checkbox"
                checked={checked}
                onChange={() => {
                  const nextValues = new Set(selectedValues);
                  if (checked) {
                    nextValues.delete(value);
                  } else {
                    nextValues.add(value);
                  }
                  setAnswerDraft(Array.from(nextValues).sort().join(","));
                }}
              />
              <span>{option}</span>
            </label>
          );
        })}
      </div>
    );
  }

  return (
    <div className="field">
      <label>作答内容</label>
      <textarea value={answerDraft} onChange={(event) => setAnswerDraft(event.target.value)} placeholder="请输入你的答案" />
    </div>
  );
}

function answerSheetClassName(item: PracticeSessionItemResponse, active: boolean) {
  const classNames = ["practiceAnswerCard"];
  if (item.is_answered) classNames.push("answered");
  if (item.marked) classNames.push("marked");
  if (item.show_result && item.is_correct === true) classNames.push("correct");
  if (item.show_result && item.is_correct === false) classNames.push("wrong");
  if (active) classNames.push("active");
  return classNames.join(" ");
}

function resultLabel(value: boolean | null | undefined) {
  if (value === true) return "回答正确";
  if (value === false) return "回答错误";
  return "待判定";
}

function findAdjacentItemId(detail: PracticeSessionDetailResponse, currentItemId: number, offset: number) {
  const currentIndex = detail.items.findIndex((item) => item.id === currentItemId);
  if (currentIndex < 0) return null;
  const nextIndex = currentIndex + offset;
  if (nextIndex < 0 || nextIndex >= detail.items.length) return null;
  return detail.items[nextIndex].id;
}

function findNextPendingItemId(detail: PracticeSessionDetailResponse, currentItemId: number) {
  const currentIndex = detail.items.findIndex((item) => item.id === currentItemId);
  if (currentIndex < 0) return null;
  for (let index = currentIndex + 1; index < detail.items.length; index += 1) {
    if (!detail.items[index].is_answered) return detail.items[index].id;
  }
  for (let index = 0; index < currentIndex; index += 1) {
    if (!detail.items[index].is_answered) return detail.items[index].id;
  }
  return null;
}
