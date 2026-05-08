"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import {
  apiFetch,
  PracticeSessionDetailResponse,
  PracticeSessionResponse,
  PracticeSetDetailResponse,
  PracticeSetQuestionResponse,
  PracticeSetResponse,
} from "../../../../lib/pro-api";
import { LoadState } from "../../../../components/shared/LoadState";
import { StatusBadge } from "../../../../components/shared/StatusBadge";
import { toErrorMessage, useLatestRequestGate } from "../../../../lib/request-guard";

type DetailTab = "question" | "analysis" | "result";
type PracticeMode = PracticeSessionResponse["practice_mode"];
type AnswerMap = Record<number, string>;
type SpentSecondsMap = Record<number, number>;
type QuestionResult = PracticeSessionDetailResponse["answers"][number];

export default function PracticeSetsPage() {
  const [items, setItems] = useState<PracticeSetResponse[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [detail, setDetail] = useState<PracticeSetDetailResponse | null>(null);
  const [session, setSession] = useState<PracticeSessionDetailResponse | null>(null);
  const [practiceMode, setPracticeMode] = useState<PracticeMode>("deferred_feedback");
  const [activeQuestionIndex, setActiveQuestionIndex] = useState(0);
  const [answers, setAnswers] = useState<AnswerMap>({});
  const [spentSecondsMap, setSpentSecondsMap] = useState<SpentSecondsMap>({});
  const [currentQuestionStartedAt, setCurrentQuestionStartedAt] = useState<number>(() => Date.now());
  const [sessionStartedAt, setSessionStartedAt] = useState<number | null>(null);
  const [detailTab, setDetailTab] = useState<DetailTab>("question");
  const [loading, setLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [working, setWorking] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const requestGate = useLatestRequestGate();
  const detailRequestIdRef = useRef(0);

  useEffect(() => {
    loadPracticeSets();
  }, []);

  useEffect(() => {
    setCurrentQuestionStartedAt(Date.now());
  }, [activeQuestionIndex, selectedId]);

  async function loadPracticeSets(preferredId?: number) {
    const requestId = requestGate.begin();
    setLoading(true);
    setError("");
    try {
      const next = await apiFetch<PracticeSetResponse[]>("/api/question-bank/practice-sets");
      if (!requestGate.isCurrent(requestId)) return;
      setItems(next);
      const nextId = preferredId && next.some((item) => item.id === preferredId) ? preferredId : next[0]?.id ?? null;
      setSelectedId(nextId);
      if (nextId) {
        await loadPracticeSetDetail(nextId);
      } else {
        resetWorkspace();
      }
    } catch (err) {
      if (!requestGate.isCurrent(requestId)) return;
      setError(toErrorMessage(err, "加载练习题包失败"));
    } finally {
      if (requestGate.isCurrent(requestId)) setLoading(false);
    }
  }

  async function loadPracticeSetDetail(practiceSetId: number) {
    const requestId = detailRequestIdRef.current + 1;
    detailRequestIdRef.current = requestId;
    setDetailLoading(true);
    setError("");
    try {
      const next = await apiFetch<PracticeSetDetailResponse>(`/api/question-bank/practice-sets/${practiceSetId}`);
      if (detailRequestIdRef.current !== requestId) return;
      setDetail(next);
      setSelectedId(practiceSetId);
      resetAttemptState(next);
    } catch (err) {
      if (detailRequestIdRef.current !== requestId) return;
      setError(toErrorMessage(err, "加载题包详情失败"));
      setDetail(null);
      setSession(null);
    } finally {
      if (detailRequestIdRef.current === requestId) setDetailLoading(false);
    }
  }

  function resetWorkspace() {
    setDetail(null);
    setSession(null);
    setAnswers({});
    setSpentSecondsMap({});
    setActiveQuestionIndex(0);
    setDetailTab("question");
    setSessionStartedAt(null);
    setCurrentQuestionStartedAt(Date.now());
  }

  function resetAttemptState(nextDetail: PracticeSetDetailResponse) {
    setSession(null);
    setAnswers({});
    setSpentSecondsMap({});
    setActiveQuestionIndex(0);
    setDetailTab("question");
    setSessionStartedAt(null);
    setCurrentQuestionStartedAt(Date.now());
    if (!nextDetail.questions.length) {
      setMessage("当前题包暂无题目。");
    } else {
      setMessage("");
    }
  }

  function recordQuestionSpent(questionId: number) {
    const deltaSeconds = Math.max(0, Math.round((Date.now() - currentQuestionStartedAt) / 1000));
    if (!deltaSeconds) return;
    setSpentSecondsMap((current) => ({
      ...current,
      [questionId]: (current[questionId] || 0) + deltaSeconds,
    }));
  }

  function pickQuestion(index: number) {
    const currentQuestion = activeQuestion;
    if (currentQuestion) {
      recordQuestionSpent(currentQuestion.bank_question_id);
    }
    setActiveQuestionIndex(index);
  }

  function handleAnswerChange(question: PracticeSetQuestionResponse, rawValue: string) {
    if (!session || session.status === "submitted") return;
    const nextValue = normalizeDraftAnswer(question.question_type, rawValue, answers[question.bank_question_id] || "");
    setAnswers((current) => ({
      ...current,
      [question.bank_question_id]: nextValue,
    }));
  }

  async function startPractice() {
    if (!detail) return;
    setWorking(true);
    setError("");
    setMessage("");
    try {
      const nextSession = await apiFetch<PracticeSessionResponse>("/api/learning/sessions", {
        method: "POST",
        body: JSON.stringify({ practice_set_id: detail.id, practice_mode: practiceMode }),
      });
      setSession({
        ...nextSession,
        practice_set_title: detail.title,
        questions: detail.questions,
        answers: [],
      });
      setSessionStartedAt(Date.now());
      setDetailTab("question");
      setMessage(
        nextSession.practice_mode === "instant_feedback"
          ? `已开始练习《${detail.title}》（逐题判题模式），每题作答后会立即显示对错和解析。`
          : `已开始练习《${detail.title}》（整套交卷模式），完成整套后统一判题和展示解析。`,
      );
    } catch (err) {
      setError(toErrorMessage(err, "开始练习失败"));
    } finally {
      setWorking(false);
    }
  }

  async function submitPractice() {
    if (!detail || !session) return;
    setWorking(true);
    setError("");
    setMessage("");
    const currentQuestion = activeQuestion;
    let nextSpentSecondsMap = spentSecondsMap;
    if (currentQuestion) {
      nextSpentSecondsMap = mergeSpentSeconds(spentSecondsMap, currentQuestion.bank_question_id, currentQuestionStartedAt);
      setSpentSecondsMap(nextSpentSecondsMap);
    }
    try {
      const totalDuration =
        sessionStartedAt == null ? null : Math.max(1, Math.round((Date.now() - sessionStartedAt) / 1000));
      await apiFetch<PracticeSessionResponse>(`/api/learning/sessions/${session.id}/submit`, {
        method: "POST",
        body: JSON.stringify({
          duration_seconds: totalDuration,
          answers: detail.questions.map((question) => ({
            bank_question_id: question.bank_question_id,
            learner_answer: answers[question.bank_question_id] || "",
            spent_seconds: nextSpentSecondsMap[question.bank_question_id] || 0,
          })),
        }),
      });
      const nextSession = await apiFetch<PracticeSessionDetailResponse>(`/api/learning/sessions/${session.id}`);
      setSession(nextSession);
      setDetailTab("result");
      setMessage(
        `${nextSession.practice_mode === "instant_feedback" ? "已完成练习" : "已交卷"}：得分 ${nextSession.score || 0} / ${sumQuestionScore(
          nextSession.questions,
        )}，正确率 ${formatAccuracy(nextSession.accuracy_rate)}`,
      );
    } catch (err) {
      setError(toErrorMessage(err, "提交练习失败"));
    } finally {
      setWorking(false);
    }
  }

  const questionCount = detail?.questions.length || 0;
  const answeredCount = detail
    ? detail.questions.filter((question) => {
        const value = answers[question.bank_question_id];
        return typeof value === "string" && value.trim().length > 0;
      }).length
    : 0;
  const activeQuestion = detail?.questions[activeQuestionIndex] || null;
  const activePracticeMode = session?.practice_mode || practiceMode;
  const activePracticeModeLabel = practiceModeLabel(activePracticeMode);
  const showInstantFeedback = !!session && session.status !== "submitted" && activePracticeMode === "instant_feedback";
  const questionResultMap = useMemo(() => {
    const map = new Map<number, QuestionResult>();
    session?.answers.forEach((item) => {
      map.set(item.bank_question_id, item);
    });
    return map;
  }, [session]);
  const activeDraftResult = useMemo(() => {
    if (!activeQuestion || !showInstantFeedback) return null;
    return buildDraftQuestionResult(activeQuestion, answers[activeQuestion.bank_question_id] || "");
  }, [activeQuestion, answers, showInstantFeedback]);
  const previousQuestionIndex = activeQuestionIndex > 0 ? activeQuestionIndex - 1 : null;
  const nextQuestionIndex = detail && activeQuestionIndex < detail.questions.length - 1 ? activeQuestionIndex + 1 : null;

  return (
    <>
      <header className="pageHeader">
        <div>
          <h1>练习题包</h1>
          <p>从题包列表直接进入练习，支持“逐题判题”和“整套交卷后统一判题”两种模式。</p>
        </div>
        <div className="buttonRow">
          <button className="button" type="button" disabled={loading} onClick={() => loadPracticeSets(selectedId || undefined)}>
            刷新题包
          </button>
          {detail && !session && (
            <div className="tabs" role="tablist" aria-label="练习模式">
              <button
                className={`tab${practiceMode === "instant_feedback" ? " active" : ""}`}
                type="button"
                onClick={() => setPracticeMode("instant_feedback")}
              >
                逐题判题
              </button>
              <button
                className={`tab${practiceMode === "deferred_feedback" ? " active" : ""}`}
                type="button"
                onClick={() => setPracticeMode("deferred_feedback")}
              >
                整套交卷
              </button>
            </div>
          )}
          {detail && !session && (
            <button className="button primary" type="button" disabled={working || !detail.questions.length} onClick={startPractice}>
              {working ? "启动中..." : "开始练习"}
            </button>
          )}
          {detail && session?.status !== "submitted" && (
            <button className="button primary" type="button" disabled={working} onClick={submitPractice}>
              {working ? "交卷中..." : activePracticeMode === "instant_feedback" ? "完成练习" : "提交练习"}
            </button>
          )}
        </div>
      </header>

      {message ? <div className="calloutBox">{message}</div> : null}

      <LoadState loading={loading} error={error} empty={!items.length} emptyLabel="暂无练习题包" />

      {!loading && !error && !!items.length && (
        <>
          <section className="statsGrid">
            <article className="statCard">
              <span>题包数量</span>
              <strong>{items.length}</strong>
              <small>支持专题训练和高频题包</small>
            </article>
            <article className="statCard">
              <span>当前题目</span>
              <strong>{questionCount}</strong>
              <small>{detail?.set_type || "未选择题包"}</small>
            </article>
            <article className="statCard">
              <span>已作答</span>
              <strong>{answeredCount}</strong>
              <small>{questionCount ? `完成率 ${Math.round((answeredCount / questionCount) * 100)}%` : "暂无题目"}</small>
            </article>
            <article className="statCard">
              <span>练习状态</span>
              <strong>{session?.status === "submitted" ? "已交卷" : session ? "作答中" : "未开始"}</strong>
              <small>{detail ? `${activePracticeModeLabel} · ${detail.title}` : "请先选择题包"}</small>
            </article>
          </section>

          <section className="dashboardGrid twoCol questionWorkspace practiceWorkspace">
            <div className="panel questionPanel questionQueuePanel">
              <div className="panelHeader">
                <h2>题包与题目列表</h2>
                <p>先选择题包和练习模式，再切换到具体题目作答。</p>
              </div>
              <div className="panelBody questionQueueBody">
                <div className="questionQueueControls stackList">
                  <div className="questionQueueStats">
                    <div className="questionMiniStat">
                      <span>已发布题包</span>
                      <strong>{items.length}</strong>
                    </div>
                    <div className="questionMiniStat">
                      <span>当前题目数</span>
                      <strong>{questionCount}</strong>
                    </div>
                  </div>

                  <div className="stackList">
                    {items.map((item) => (
                      <button
                        key={item.id}
                        className={`listButton${selectedId === item.id ? " active" : ""}`}
                        type="button"
                        onClick={() => loadPracticeSetDetail(item.id)}
                        disabled={detailLoading}
                      >
                        <div className="questionListContent">
                          <strong className="questionListTitle">{item.title}</strong>
                          <span className="questionListMeta">
                            {item.set_type} · {item.question_count} 题 · {item.difficulty_policy || "未配置策略"}
                          </span>
                          <span className="questionListNote">{item.description || "暂无说明"}</span>
                        </div>
                        <div className="questionListBadges">
                          <StatusBadge value={item.status} tone="good" />
                        </div>
                      </button>
                    ))}
                  </div>
                </div>

                <div className="questionQueueListHeader">
                  <strong>{detail?.title || "题目列表"}</strong>
                  <span className="muted">
                    {detailLoading ? "题包加载中..." : questionCount ? `共 ${questionCount} 题，点击右侧作答` : "当前题包暂无题目"}
                  </span>
                </div>

                <div className="questionQueueList">
                  <LoadState loading={detailLoading} error="" empty={!detail && !detailLoading} emptyLabel="请选择题包" />
                  {!!detail && (
                    <div className="stackList">
                      {detail.questions.map((question, index) => {
                        const answer = answers[question.bank_question_id] || "";
                        const result = questionResultMap.get(question.bank_question_id);
                        const draftResult = showInstantFeedback ? buildDraftQuestionResult(question, answer) : null;
                        return (
                          <div key={question.id} className="selectableRow questionSelectableRow">
                            <button
                              className={`listButton questionListButton${activeQuestionIndex === index ? " active" : ""}`}
                              type="button"
                              onClick={() => pickQuestion(index)}
                            >
                              <div className="questionListContent">
                                <strong className="questionListTitle">
                                  {question.sort_order}. {question.stem_text}
                                </strong>
                                <span className="questionListMeta">
                                  {questionTypeLabel(question.question_type)} · {question.score || 0} 分 · 难度 {question.difficulty_level || "-"}
                                </span>
                                <span className="questionListNote">
                                  {answer.trim() ? `当前作答：${answer}` : "未作答"}
                                  {question.knowledge_point_names.length ? ` · 考点：${question.knowledge_point_names.join(" / ")}` : ""}
                                </span>
                              </div>
                              <div className="questionListBadges">
                                {session?.status === "submitted" && result ? (
                                  <StatusBadge value={result.is_correct ? "正确" : "错误"} tone={result.is_correct ? "good" : "danger"} />
                                ) : draftResult ? (
                                  <StatusBadge value={draftResult.is_correct ? "正确" : "错误"} tone={draftResult.is_correct ? "good" : "danger"} />
                                ) : (
                                  <StatusBadge value={answer.trim() ? "已作答" : "待作答"} tone={answer.trim() ? "info" : "warn"} />
                                )}
                              </div>
                            </button>
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>
              </div>
            </div>

            <div className="panel questionPanel questionDetailPanel">
              <div className="panelHeader">
                <h2>练习详情</h2>
                <p>逐题判题模式会即时反馈，整套交卷模式会在完成后统一展示结果和解析。</p>
              </div>
              <div className="panelBody questionDetailBody">
                <LoadState loading={detailLoading} error="" empty={!activeQuestion && !detailLoading} emptyLabel="请选择题包中的题目" />
                {activeQuestion && (
                  <>
                    <div className="questionDetailSticky">
                      <div className="questionDetailSummary">
                        <div>
                          <strong>
                            第 {activeQuestion.sort_order} 题 · {detail?.title}
                          </strong>
                          <p className="muted questionDetailLead">{activeQuestion.stem_text}</p>
                        </div>
                        <div className="questionDetailSummaryBadges">
                          <StatusBadge value={questionTypeLabel(activeQuestion.question_type)} tone="info" />
                          <StatusBadge value={`${activeQuestion.score || 0} 分`} tone="warn" />
                        </div>
                      </div>

                      <div className="questionDetailNav">
                        <button className="button" type="button" disabled={previousQuestionIndex === null} onClick={() => previousQuestionIndex !== null && pickQuestion(previousQuestionIndex)}>
                          上一题
                        </button>
                        <span className="muted">
                          {activeQuestionIndex + 1} / {questionCount}
                        </span>
                        <button className="button" type="button" disabled={nextQuestionIndex === null} onClick={() => nextQuestionIndex !== null && pickQuestion(nextQuestionIndex)}>
                          下一题
                        </button>
                      </div>

                      <div className="tabs questionDetailTabs" role="tablist" aria-label="练习详情标签">
                        <button className={`tab${detailTab === "question" ? " active" : ""}`} type="button" onClick={() => setDetailTab("question")}>
                          题目作答
                        </button>
                        <button className={`tab${detailTab === "analysis" ? " active" : ""}`} type="button" onClick={() => setDetailTab("analysis")}>
                          答案解析
                        </button>
                        <button className={`tab${detailTab === "result" ? " active" : ""}`} type="button" onClick={() => setDetailTab("result")}>
                          作答结果
                        </button>
                      </div>
                    </div>

                    <div className="questionDetailScroll">
                      {detailTab === "question" && (
                        <div className="questionDetailSection">
                          {!session ? <div className="calloutBox">请选择练习模式并点击“开始练习”后作答，避免答案未纳入本次练习。</div> : null}
                          <div className="questionMetaGrid">
                            <div className="questionMetaCard">
                              <span>题型</span>
                              <strong>{questionTypeLabel(activeQuestion.question_type)}</strong>
                            </div>
                            <div className="questionMetaCard">
                              <span>分值</span>
                              <strong>{activeQuestion.score || 0} 分</strong>
                            </div>
                            <div className="questionMetaCard">
                              <span>来源次数</span>
                              <strong>{activeQuestion.source_count}</strong>
                            </div>
                            <div className="questionMetaCard">
                              <span>考点</span>
                              <strong>{activeQuestion.knowledge_point_names.join(" / ") || "-"}</strong>
                            </div>
                          </div>

                          <div className="questionCard">
                            <strong>
                              {activeQuestion.sort_order}. {activeQuestion.stem_text}
                            </strong>
                            {activeQuestion.options_json?.length ? (
                              <div className="practiceOptionList">
                                {activeQuestion.options_json.map((option, index) => {
                                  const optionLabel = optionOptionLabel(index);
                                  const normalizedCurrent = normalizeSelectionToken(answers[activeQuestion.bank_question_id] || "");
                                  const checked = activeQuestion.question_type === "multiple_choice"
                                    ? normalizedCurrent.includes(optionLabel)
                                    : normalizedCurrent === optionLabel;
                                  return (
                                    <label key={`${activeQuestion.id}-${index}`} className="practiceOptionRow">
                                      <input
                                        type={activeQuestion.question_type === "multiple_choice" ? "checkbox" : "radio"}
                                        name={`question-${activeQuestion.bank_question_id}`}
                                        checked={checked}
                                        disabled={!session || session.status === "submitted"}
                                        onChange={() => handleAnswerChange(activeQuestion, optionLabel)}
                                      />
                                      <span>{option}</span>
                                    </label>
                                  );
                                })}
                              </div>
                            ) : (
                              <label className="field">
                                <span>作答内容</span>
                                <textarea
                                  value={answers[activeQuestion.bank_question_id] || ""}
                                  onChange={(event) => handleAnswerChange(activeQuestion, event.target.value)}
                                  disabled={!session || session.status === "submitted"}
                                  rows={6}
                                  placeholder="请输入你的答案"
                                />
                              </label>
                            )}
                            {activeQuestion.options_json?.length ? (
                              <div className="detailRow">
                                <span>当前答案</span>
                                <strong>{answers[activeQuestion.bank_question_id] || "未作答"}</strong>
                              </div>
                            ) : null}
                          </div>

                          {showInstantFeedback ? (
                            activeDraftResult ? (
                              <>
                                <div className="questionMetaGrid">
                                  <div className="questionMetaCard">
                                    <span>即时判题</span>
                                    <strong>{activeDraftResult.is_correct ? "回答正确" : "回答错误"}</strong>
                                  </div>
                                  <div className="questionMetaCard">
                                    <span>本题得分</span>
                                    <strong>
                                      {activeDraftResult.score || 0} / {activeDraftResult.full_score || 0}
                                    </strong>
                                  </div>
                                  <div className="questionMetaCard">
                                    <span>你的答案</span>
                                    <strong>{activeDraftResult.learner_answer || "未作答"}</strong>
                                  </div>
                                  <div className="questionMetaCard">
                                    <span>标准答案</span>
                                    <strong>{activeDraftResult.correct_answer || "-"}</strong>
                                  </div>
                                </div>
                                <div className="questionCard">
                                  <strong>即时解析</strong>
                                  <p>{activeDraftResult.analysis_text || "暂无解析"}</p>
                                </div>
                              </>
                            ) : (
                              <div className="calloutBox">当前为逐题判题模式，作答后会立即显示该题对错和答案解析。</div>
                            )
                          ) : null}
                        </div>
                      )}

                      {detailTab === "analysis" && (
                        <div className="questionDetailSection">
                          {!session ? (
                            <div className="calloutBox">开始练习后可按所选模式查看答案解析。</div>
                          ) : activePracticeMode === "deferred_feedback" && session.status !== "submitted" ? (
                            <div className="calloutBox">当前为整套交卷模式，交卷后这里会统一展示参考答案和解析。</div>
                          ) : (
                            <>
                              <div className="questionMetaGrid">
                                <div className="questionMetaCard">
                                  <span>参考答案</span>
                                  <strong>{activeQuestion.answer_text || "-"}</strong>
                                </div>
                                <div className="questionMetaCard">
                                  <span>质量分</span>
                                  <strong>{activeQuestion.quality_score || "-"}</strong>
                                </div>
                              </div>
                              <div className="questionCard">
                                <strong>答案解析</strong>
                                <p>{activeQuestion.analysis_text || "暂无解析"}</p>
                              </div>
                            </>
                          )}
                        </div>
                      )}

                      {detailTab === "result" && (
                        <div className="questionDetailSection">
                          {!session ? (
                            <div className="calloutBox">开始练习后，这里会根据练习模式展示本题结果。</div>
                          ) : session.status === "submitted" ? (
                            (() => {
                              const result = questionResultMap.get(activeQuestion.bank_question_id);
                              return (
                                <>
                                  <div className="questionMetaGrid">
                                    <div className="questionMetaCard">
                                      <span>判题结果</span>
                                      <strong>{result?.is_correct ? "回答正确" : "回答错误"}</strong>
                                    </div>
                                    <div className="questionMetaCard">
                                      <span>本题得分</span>
                                      <strong>
                                        {result?.score || 0} / {result?.full_score || 0}
                                      </strong>
                                    </div>
                                    <div className="questionMetaCard">
                                      <span>你的答案</span>
                                      <strong>{result?.learner_answer || "未作答"}</strong>
                                    </div>
                                    <div className="questionMetaCard">
                                      <span>标准答案</span>
                                      <strong>{result?.correct_answer || "-"}</strong>
                                    </div>
                                  </div>
                                  <div className="questionCard">
                                    <strong>结果说明</strong>
                                    <p>{result?.analysis_text || activeQuestion.analysis_text || "暂无解析"}</p>
                                  </div>
                                </>
                              );
                            })()
                          ) : activePracticeMode === "instant_feedback" ? (
                            activeDraftResult ? (
                              <>
                                <div className="questionMetaGrid">
                                  <div className="questionMetaCard">
                                    <span>判题结果</span>
                                    <strong>{activeDraftResult.is_correct ? "回答正确" : "回答错误"}</strong>
                                  </div>
                                  <div className="questionMetaCard">
                                    <span>本题得分</span>
                                    <strong>
                                      {activeDraftResult.score || 0} / {activeDraftResult.full_score || 0}
                                    </strong>
                                  </div>
                                  <div className="questionMetaCard">
                                    <span>你的答案</span>
                                    <strong>{activeDraftResult.learner_answer || "未作答"}</strong>
                                  </div>
                                  <div className="questionMetaCard">
                                    <span>标准答案</span>
                                    <strong>{activeDraftResult.correct_answer || "-"}</strong>
                                  </div>
                                </div>
                                <div className="questionCard">
                                  <strong>结果说明</strong>
                                  <p>{activeDraftResult.analysis_text || activeQuestion.analysis_text || "暂无解析"}</p>
                                </div>
                              </>
                            ) : (
                              <div className="calloutBox">当前题尚未作答，作答后这里会立即显示对错和得分。</div>
                            )
                          ) : (
                            <div className="calloutBox">当前还未交卷，整套交卷模式会在提交练习后统一展示该题对错、得分和标准答案。</div>
                          )}
                        </div>
                      )}
                    </div>
                  </>
                )}
              </div>
            </div>
          </section>
        </>
      )}
    </>
  );
}

function questionTypeLabel(value: string) {
  if (value === "single_choice") return "单选题";
  if (value === "multiple_choice") return "多选题";
  if (value === "judge") return "判断题";
  if (value === "fill_blank") return "填空题";
  if (value === "short_answer") return "简答题";
  if (value === "calculation") return "计算题";
  if (value === "case_analysis") return "案例分析题";
  if (value === "material_analysis") return "材料分析题";
  if (value === "composite") return "综合题";
  return value || "未分类";
}

function practiceModeLabel(value: PracticeMode) {
  return value === "instant_feedback" ? "逐题判题" : "整套交卷";
}

function optionOptionLabel(index: number) {
  return String.fromCharCode(65 + index);
}

function normalizeSelectionToken(value: string) {
  return value.toUpperCase().replace(/[^A-Z]/g, "");
}

function normalizeDraftAnswer(questionType: string, rawValue: string, currentValue: string) {
  if (questionType === "multiple_choice") {
    const token = normalizeSelectionToken(rawValue).slice(0, 1);
    const currentTokens = new Set(normalizeSelectionToken(currentValue).split("").filter(Boolean));
    if (token) {
      if (currentTokens.has(token)) {
        currentTokens.delete(token);
      } else {
        currentTokens.add(token);
      }
    }
    return Array.from(currentTokens).sort().join("");
  }
  if (questionType === "single_choice" || questionType === "judge") {
    return normalizeSelectionToken(rawValue).slice(0, 1);
  }
  return rawValue;
}

function sumQuestionScore(questions: PracticeSetQuestionResponse[]) {
  return questions.reduce((total, question) => total + (question.score || 0), 0);
}

function buildDraftQuestionResult(question: PracticeSetQuestionResponse, learnerAnswer: string): QuestionResult | null {
  if (!learnerAnswer.trim()) return null;
  const fullScore = question.score || 0;
  const isCorrect = answersMatch(learnerAnswer, question.answer_text || "", question.question_type);
  return {
    bank_question_id: question.bank_question_id,
    learner_answer: learnerAnswer,
    correct_answer: question.answer_text || null,
    is_correct: isCorrect,
    score: isCorrect ? fullScore : 0,
    full_score: fullScore,
    spent_seconds: null,
    analysis_text: question.analysis_text || null,
  };
}

function answersMatch(learnerAnswer: string, correctAnswer: string, questionType: string) {
  const learner = normalizeAutoCheckAnswer(learnerAnswer);
  const correct = normalizeAutoCheckAnswer(correctAnswer);
  if (questionType === "multiple_choice") {
    return learner.split("").sort().join("") === correct.split("").sort().join("");
  }
  return learner === correct;
}

function normalizeAutoCheckAnswer(value: string) {
  return value.toUpperCase().replace(/\s+/g, "");
}

function formatAccuracy(value?: number | null) {
  if (value == null) return "0%";
  return `${Math.round(value * 100)}%`;
}

function mergeSpentSeconds(current: SpentSecondsMap, questionId: number, startedAt: number) {
  const deltaSeconds = Math.max(0, Math.round((Date.now() - startedAt) / 1000));
  if (!deltaSeconds) return current;
  return {
    ...current,
    [questionId]: (current[questionId] || 0) + deltaSeconds,
  };
}
