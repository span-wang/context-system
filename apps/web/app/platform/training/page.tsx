"use client";

import { useEffect, useMemo, useState } from "react";

import { LoadState } from "../../../components/shared/LoadState";
import { StatusBadge } from "../../../components/shared/StatusBadge";
import { renderDocumentPreviewHtml } from "../../../lib/document-preview";

type TrainingSampleSummary = {
  id: string;
  paper_id: number | null;
  paper_name: string;
  subject_name: string | null;
  category_name: string | null;
  predicted_question_count: number;
  stored_needs_review_count: number;
  gold_exists: boolean;
  label_status: string;
  source_text_length: number;
  updated_at: string | null;
};

type TrainingDatasetSummary = {
  dataset_root: string;
  sample_count: number;
  gold_count: number;
  prediction_count: number;
  source_count: number;
  public_web_url: string | null;
  public_hostnames: string[];
  api_base: string | null;
  web_url: string | null;
  started_at: string | null;
  samples: TrainingSampleSummary[];
};

type TrainingSampleDetail = {
  sample: TrainingSampleSummary;
  meta: Record<string, unknown>;
  source_text: string;
  prediction_text: string;
  gold_template_text: string;
  gold_text: string;
};

type TrainingSampleDeleteResult = {
  id: string;
  paper_name: string;
};

type TrainingQuestion = {
  question_no: string;
  question_type: string;
  stem_text: string;
  options: string[];
  answer_text: string;
  analysis_text: string;
};

type TrainingSection = {
  title: string;
  section_type: string;
  questions: TrainingQuestion[];
};

type TrainingDocument = {
  version: number;
  label_status: string;
  notes: string;
  sections: TrainingSection[];
};

type TrainingSectionTab = {
  title: string;
  section_type: string;
  question_count: number;
};

type TrainingWorkbenchView = "fields" | "json";

export default function TrainingPage() {
  const [summary, setSummary] = useState<TrainingDatasetSummary | null>(null);
  const [selectedId, setSelectedId] = useState("");
  const [detail, setDetail] = useState<TrainingSampleDetail | null>(null);
  const [goldDoc, setGoldDoc] = useState<TrainingDocument | null>(null);
  const [activeSectionIndex, setActiveSectionIndex] = useState(0);
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState("");
  const [detailError, setDetailError] = useState("");
  const [message, setMessage] = useState("");
  const [workbenchView, setWorkbenchView] = useState<TrainingWorkbenchView>("fields");
  const [goldJsonText, setGoldJsonText] = useState("");
  const [goldJsonError, setGoldJsonError] = useState("");

  useEffect(() => {
    void loadSummary();
  }, []);

  useEffect(() => {
    if (!selectedId) {
      setDetail(null);
      setGoldDoc(null);
      setActiveSectionIndex(0);
      setGoldJsonText("");
      setGoldJsonError("");
      return;
    }
    void loadDetail(selectedId);
  }, [selectedId]);

  const filteredSamples = useMemo(() => {
    const keyword = search.trim().toLowerCase();
    if (!keyword) return summary?.samples || [];
    return (summary?.samples || []).filter((sample) => {
      return [sample.paper_name, sample.subject_name, sample.category_name, sample.id]
        .filter(Boolean)
        .some((value) => String(value).toLowerCase().includes(keyword));
    });
  }, [search, summary]);

  const predictionDoc = useMemo(() => parseTrainingDocument(detail?.prediction_text || ""), [detail?.prediction_text]);
  const templateDoc = useMemo(
    () => parseTrainingDocument(detail?.gold_template_text || "", predictionDoc),
    [detail?.gold_template_text, predictionDoc]
  );
  const editableDoc = goldDoc || templateDoc;
  const sectionTabs = useMemo(
    () => buildSectionTabs(editableDoc.sections, predictionDoc.sections),
    [editableDoc.sections, predictionDoc.sections]
  );

  useEffect(() => {
    if (!sectionTabs.length) {
      if (activeSectionIndex !== 0) {
        setActiveSectionIndex(0);
      }
      return;
    }
    if (activeSectionIndex > sectionTabs.length - 1) {
      setActiveSectionIndex(sectionTabs.length - 1);
    }
  }, [activeSectionIndex, sectionTabs]);

  const activePredictionSection = predictionDoc.sections[activeSectionIndex] || null;
  const activeGoldSection = editableDoc.sections[activeSectionIndex] || null;
  const activeSection = sectionTabs[activeSectionIndex] || null;
  const unlabeledCount = (summary?.samples || []).filter((sample) => isPendingLabelStatus(sample.label_status)).length;

  async function loadSummary() {
    setLoading(true);
    setError("");
    try {
      const response = await fetch("/api/training/samples", { cache: "no-store" });
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(String(payload.detail || "读取训练样本列表失败"));
      }
      const nextSummary = payload as TrainingDatasetSummary;
      setSummary(nextSummary);
      setSelectedId((current) => {
        if (current && nextSummary.samples.some((sample) => sample.id === current)) {
          return current;
        }
        return nextSummary.samples[0]?.id || "";
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "读取训练样本列表失败");
    } finally {
      setLoading(false);
    }
  }

  async function loadDetail(sampleId: string) {
    setDetailLoading(true);
    setDetailError("");
    try {
      const response = await fetch(`/api/training/samples?sample_id=${encodeURIComponent(sampleId)}`, { cache: "no-store" });
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(String(payload.detail || "读取训练样本详情失败"));
      }
      const nextDetail = payload as TrainingSampleDetail;
      const nextPrediction = parseTrainingDocument(nextDetail.prediction_text || "");
      const nextTemplate = parseTrainingDocument(nextDetail.gold_template_text || "", nextPrediction);
      setDetail(nextDetail);
      setGoldDoc(parseTrainingDocument(nextDetail.gold_text || "", nextTemplate));
      setGoldJsonText(nextDetail.gold_text || serializeTrainingDocument(nextTemplate));
      setGoldJsonError("");
      setActiveSectionIndex(0);
    } catch (err) {
      setDetailError(err instanceof Error ? err.message : "读取训练样本详情失败");
    } finally {
      setDetailLoading(false);
    }
  }

  async function saveGold() {
    if (!selectedId) return;
    setSaving(true);
    setMessage("");
    setDetailError("");
    try {
      let goldText = "";
      if (workbenchView === "json") {
        const validationError = validateTrainingJsonText(goldJsonText);
        if (validationError) {
          setGoldJsonError(validationError);
          return;
        }
        goldText = goldJsonText;
      } else {
        if (!goldDoc) return;
        goldText = serializeTrainingDocument(goldDoc);
        setGoldJsonText(goldText);
        setGoldJsonError("");
      }
      const response = await fetch(`/api/training/samples?sample_id=${encodeURIComponent(selectedId)}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ gold_text: goldText }),
      });
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(String(payload.detail || "保存 gold.json 失败"));
      }
      const nextDetail = payload as TrainingSampleDetail;
      const nextPrediction = parseTrainingDocument(nextDetail.prediction_text || "");
      const nextTemplate = parseTrainingDocument(nextDetail.gold_template_text || "", nextPrediction);
      setDetail(nextDetail);
      setGoldDoc(parseTrainingDocument(nextDetail.gold_text || "", nextTemplate));
      setGoldJsonText(nextDetail.gold_text || serializeTrainingDocument(nextTemplate));
      setGoldJsonError("");
      setMessage(`已保存 ${nextDetail.sample.paper_name} 的 gold.json`);
      await loadSummary();
      setSelectedId(nextDetail.sample.id);
    } catch (err) {
      setDetailError(err instanceof Error ? err.message : "保存 gold.json 失败");
    } finally {
      setSaving(false);
    }
  }

  async function deleteSelectedSample() {
    if (!detail) return;
    const confirmed = window.confirm(`确定删除样本“${detail.sample.paper_name}”吗？会连同当前样本目录下的 source、prediction、gold 文件一起删除。`);
    if (!confirmed) return;
    setDeleting(true);
    setMessage("");
    setDetailError("");
    try {
      const sampleId = detail.sample.id;
      const response = await fetch(`/api/training/samples?sample_id=${encodeURIComponent(sampleId)}`, {
        method: "DELETE",
      });
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(String(payload.detail || "删除训练样本失败"));
      }
      const result = payload as TrainingSampleDeleteResult;
      setSelectedId("");
      await loadSummary();
      setMessage(`已删除样本：${result.paper_name}`);
    } catch (err) {
      setDetailError(err instanceof Error ? err.message : "删除训练样本失败");
    } finally {
      setDeleting(false);
    }
  }

  function replaceEditorWithTemplate() {
    const nextDoc = cloneTrainingDocument(templateDoc);
    setGoldDoc(nextDoc);
    setGoldJsonText(serializeTrainingDocument(nextDoc));
    setGoldJsonError("");
    setMessage("已把标注填写区切回 gold.template.json");
  }

  function replaceEditorWithPrediction() {
    const nextDoc = parseTrainingDocument(detail?.prediction_text || "", predictionDoc);
    setGoldDoc(nextDoc);
    setGoldJsonText(serializeTrainingDocument(nextDoc));
    setGoldJsonError("");
    setMessage("已把标注填写区切成当前 prediction.json，适合从预测结果开始修。");
  }

  function switchWorkbenchView(nextView: TrainingWorkbenchView) {
    if (nextView === workbenchView) {
      return;
    }
    if (nextView === "json") {
      setGoldJsonText(goldDoc ? serializeTrainingDocument(goldDoc) : detail?.gold_text || serializeTrainingDocument(editableDoc));
      setGoldJsonError("");
      setWorkbenchView("json");
      return;
    }
    const validationError = validateTrainingJsonText(goldJsonText);
    if (validationError) {
      setGoldJsonError(validationError);
      return;
    }
    setGoldDoc(parseTrainingDocument(goldJsonText, templateDoc));
    setGoldJsonError("");
    setWorkbenchView("fields");
  }

  function updateGoldMeta(field: "label_status" | "notes", value: string) {
    setGoldDoc((current) => {
      if (!current) return current;
      return { ...current, [field]: value };
    });
  }

  function updateGoldSectionField(sectionIndex: number, field: "title" | "section_type", value: string) {
    setGoldDoc((current) => {
      if (!current) return current;
      return {
        ...current,
        sections: current.sections.map((section, index) =>
          index === sectionIndex ? { ...section, [field]: value } : section
        ),
      };
    });
  }

  function updateGoldQuestionField(
    sectionIndex: number,
    questionIndex: number,
    field: Exclude<keyof TrainingQuestion, "options">,
    value: string
  ) {
    setGoldDoc((current) => {
      if (!current) return current;
      return {
        ...current,
        sections: current.sections.map((section, currentSectionIndex) => {
          if (currentSectionIndex !== sectionIndex) {
            return section;
          }
          return {
            ...section,
            questions: section.questions.map((question, currentQuestionIndex) =>
              currentQuestionIndex === questionIndex ? { ...question, [field]: value } : question
            ),
          };
        }),
      };
    });
  }

  function updateGoldOption(sectionIndex: number, questionIndex: number, optionIndex: number, value: string) {
    setGoldDoc((current) => {
      if (!current) return current;
      return {
        ...current,
        sections: current.sections.map((section, currentSectionIndex) => {
          if (currentSectionIndex !== sectionIndex) {
            return section;
          }
          return {
            ...section,
            questions: section.questions.map((question, currentQuestionIndex) => {
              if (currentQuestionIndex !== questionIndex) {
                return question;
              }
              return {
                ...question,
                options: question.options.map((option, currentOptionIndex) =>
                  currentOptionIndex === optionIndex ? value : option
                ),
              };
            }),
          };
        }),
      };
    });
  }

  function addGoldOption(sectionIndex: number, questionIndex: number) {
    setGoldDoc((current) => {
      if (!current) return current;
      return {
        ...current,
        sections: current.sections.map((section, currentSectionIndex) => {
          if (currentSectionIndex !== sectionIndex) {
            return section;
          }
          return {
            ...section,
            questions: section.questions.map((question, currentQuestionIndex) =>
              currentQuestionIndex === questionIndex
                ? { ...question, options: [...question.options, ""] }
                : question
            ),
          };
        }),
      };
    });
  }

  return (
    <div className="trainingPageRoot">
      <header className="pageHeader">
        <div>
          <h1>模型训练</h1>
          <p>这里可以直接查看自动沉淀的样本，并在线用题型、题干、选项、答案、解析等字段做结构化标注。</p>
        </div>
      </header>

      {message ? <div className="calloutBox">{message}</div> : null}
      <LoadState loading={loading} error={error} empty={!summary} emptyLabel="训练样本暂不可用" />

      {!loading && !error && summary ? (
        <>
          <section className="dashboardGrid twoCol" style={{ marginBottom: 20 }}>
            <article className="panel">
              <div className="panelHeader">
                <h2>远程入口</h2>
                <p>训练标注已并入当前业务入口，与试卷和学科页面共用同一域名。</p>
              </div>
              <div className="panelBody stackList">
                <div className="detailRow">
                  <span>训练公网地址</span>
                  <strong>{summary.public_web_url || "-"}</strong>
                </div>
                <div className="detailRow">
                  <span>训练 hostname</span>
                  <strong>{summary.public_hostnames.join(", ") || "-"}</strong>
                </div>
                <div className="detailRow">
                  <span>样本目录</span>
                  <strong>{summary.dataset_root}</strong>
                </div>
              </div>
            </article>

            <article className="panel">
              <div className="panelHeader">
                <h2>样本概览</h2>
                <p>先选样本，再按 section 对照 prediction，把 gold 按字段填完整。</p>
              </div>
              <div className="panelBody trainingStatsGrid">
                <div className="questionMiniStat">
                  <span>样本总数</span>
                  <strong>{summary.sample_count}</strong>
                </div>
                <div className="questionMiniStat">
                  <span>已生成 gold</span>
                  <strong>{summary.gold_count}</strong>
                </div>
                <div className="questionMiniStat">
                  <span>待人工标注</span>
                  <strong>{unlabeledCount}</strong>
                </div>
                <div className="questionMiniStat">
                  <span>prediction 数量</span>
                  <strong>{summary.prediction_count}</strong>
                </div>
              </div>
            </article>
          </section>

          <section className="dashboardGrid twoCol questionWorkspace trainingWorkspace">
            <article className="panel questionPanel questionQueuePanel">
              <div className="panelHeader">
                <h2>训练样本</h2>
                <p>当前支持按 section 对照查看，再按题号逐题填写字段。</p>
              </div>
              <div className="panelBody questionQueueBody trainingQueueBody">
                <input
                  className="input"
                  value={search}
                  onChange={(event) => setSearch(event.target.value)}
                  placeholder="搜索试卷名 / 学科 / 样本目录"
                />
                <div className="questionQueueList trainingSampleList">
                  {filteredSamples.map((sample) => {
                    const active = sample.id === selectedId;
                    return (
                      <div key={sample.id} className="selectableRow questionSelectableRow">
                        <button
                          type="button"
                          className={active ? "listButton questionListButton active trainingSampleCard" : "listButton questionListButton trainingSampleCard"}
                          onClick={() => setSelectedId(sample.id)}
                        >
                          <div className="questionListContent">
                            <div className="trainingSampleCardHead">
                              <strong className="questionListTitle">{sample.paper_name}</strong>
                              <StatusBadge
                                value={sample.label_status}
                                tone={isPendingLabelStatus(sample.label_status) ? "warn" : "good"}
                              />
                            </div>
                            <span className="questionListMeta">
                              {sample.subject_name || "未绑定学科"} · {sample.category_name || "未分类"} · 预测 {sample.predicted_question_count} 题
                            </span>
                            <span className="questionListNote">
                              待复核 {sample.stored_needs_review_count} · 文本 {sample.source_text_length} 字 · {sample.id}
                            </span>
                          </div>
                        </button>
                      </div>
                    );
                  })}
                  {!filteredSamples.length ? (
                    <div className="empty compact">
                      {summary.sample_count ? "没有匹配到样本" : "当前还没有样本，先去试卷中心解析一份试卷。"}
                    </div>
                  ) : null}
                </div>
              </div>
            </article>

            <article className="panel questionPanel questionDetailPanel">
              <div className="panelHeader">
                <div>
                  <h2>标注工作台</h2>
                  <p>
                    {workbenchView === "json"
                      ? "左侧看 source.txt，中间直接查看 prediction.json，右侧直接编辑和保存 gold.json。"
                      : "左侧看 source.txt，中间看 prediction 切分结果，右侧直接按题型、题干、选项、答案、解析填写 gold。"}
                  </p>
                </div>
                <div className="trainingEditorActions">
                  <button className="button danger small" type="button" disabled={!detail || deleting || saving} onClick={deleteSelectedSample}>
                    {deleting ? "删除中..." : "删除样本"}
                  </button>
                  <button
                    className={workbenchView === "fields" ? "button primary small" : "button small"}
                    type="button"
                    onClick={() => switchWorkbenchView("fields")}
                  >
                    字段视图
                  </button>
                  <button
                    className={workbenchView === "json" ? "button primary small" : "button small"}
                    type="button"
                    onClick={() => switchWorkbenchView("json")}
                  >
                    JSON 视图
                  </button>
                </div>
              </div>
              <div className="panelBody questionDetailBody trainingDetailBody">
                <LoadState loading={detailLoading} error={detailError} empty={!detail && !detailLoading} emptyLabel="请选择一个样本开始标注" />
                {detail ? (
                  <div className="trainingEditorGrid">
                    <div className="trainingMetaGrid">
                      <div className="detailRow">
                        <span>试卷</span>
                        <strong>{detail.sample.paper_name}</strong>
                      </div>
                      <div className="detailRow">
                        <span>样本目录</span>
                        <strong>{detail.sample.id}</strong>
                      </div>
                      <div className="detailRow">
                        <span>题目数</span>
                        <strong>{detail.sample.predicted_question_count}</strong>
                      </div>
                      <div className="detailRow">
                        <span>当前视图</span>
                        <strong>
                          {workbenchView === "json"
                            ? "整份 JSON 文档"
                            : activeSection
                              ? `${activeSection.title || `分区 ${activeSectionIndex + 1}`} · ${activeSection.question_count} 题`
                              : "-"}
                        </strong>
                      </div>
                    </div>

                    {workbenchView === "fields" && sectionTabs.length ? (
                      <div className="trainingSectionTabs">
                        {sectionTabs.map((section, index) => (
                          <button
                            key={`${section.title}-${index}`}
                            className={index === activeSectionIndex ? "trainingSectionTab active" : "trainingSectionTab"}
                            type="button"
                            onClick={() => setActiveSectionIndex(index)}
                          >
                            <strong>{section.title || `分区 ${index + 1}`}</strong>
                            <span>{section.section_type || "未标注类型"} · {section.question_count} 题</span>
                          </button>
                        ))}
                      </div>
                    ) : null}

                    <div className="trainingEditorSection">
                      <div className="trainingEditorHeader">
                        <strong>source.txt</strong>
                        <span className="muted">原始切题文本</span>
                      </div>
                      <textarea className="trainingTextarea trainingReadonly trainingSourceTextarea" value={detail.source_text} readOnly spellCheck={false} />
                    </div>

                    <div className="trainingEditorSection">
                      <div className="trainingEditorHeader">
                        <strong>{workbenchView === "json" ? "prediction.json" : "prediction 切分预览"}</strong>
                        <span className="muted">{workbenchView === "json" ? "整份预测结果，只读查看" : "按字段只读查看当前 section"}</span>
                      </div>
                      {workbenchView === "json" ? (
                        <textarea
                          className="trainingTextarea trainingReadonly trainingEditorTextarea"
                          value={detail.prediction_text || "{}"}
                          readOnly
                          spellCheck={false}
                        />
                      ) : (
                        <div className="trainingStructuredPanel trainingStructuredReadonly">
                          {activePredictionSection ? (
                            <TrainingReadonlySection section={activePredictionSection} sampleId={detail.sample.id} />
                          ) : (
                            <div className="empty compact">prediction 中暂无切分结果</div>
                          )}
                        </div>
                      )}
                    </div>

                    <div className="trainingEditorSection">
                      <div className="trainingEditorHeader">
                        <strong>{workbenchView === "json" ? "gold.json" : "gold 标注填写区"}</strong>
                        <div className="trainingEditorActions">
                          <button className="button small" type="button" onClick={replaceEditorWithTemplate}>
                            载入模板
                          </button>
                          <button className="button small" type="button" onClick={replaceEditorWithPrediction}>
                            载入预测结果
                          </button>
                          <button className="button primary small" type="button" disabled={saving} onClick={saveGold}>
                            {saving ? "保存中..." : "保存 gold.json"}
                          </button>
                        </div>
                      </div>
                      {workbenchView === "json" ? (
                        <div className="trainingStructuredPanel">
                          {goldJsonError ? <div className="errorPanel">{goldJsonError}</div> : null}
                          <textarea
                            className="trainingTextarea trainingEditorTextarea"
                            value={goldJsonText}
                            onChange={(event) => {
                              setGoldJsonText(event.target.value);
                              if (goldJsonError) {
                                setGoldJsonError("");
                              }
                            }}
                            spellCheck={false}
                          />
                        </div>
                      ) : (
                        <div className="trainingStructuredPanel">
                          <div className="trainingGoldMetaGrid">
                            <label className="trainingField">
                              <span>标注状态</span>
                              <input
                                className="input"
                                value={editableDoc.label_status}
                                onChange={(event) => updateGoldMeta("label_status", event.target.value)}
                              />
                            </label>
                            <label className="trainingField trainingFieldFull">
                              <span>备注</span>
                              <textarea
                                className="trainingFormTextarea trainingNotesTextarea"
                                value={editableDoc.notes}
                                onChange={(event) => updateGoldMeta("notes", event.target.value)}
                                spellCheck={false}
                              />
                            </label>
                          </div>

                          {activeGoldSection ? (
                            <TrainingEditableSection
                              section={activeGoldSection}
                              sectionIndex={activeSectionIndex}
                              onSectionFieldChange={updateGoldSectionField}
                              onQuestionFieldChange={updateGoldQuestionField}
                              onOptionChange={updateGoldOption}
                              onAddOption={addGoldOption}
                            />
                          ) : (
                            <div className="empty compact">gold 中暂无可填写题目</div>
                          )}
                        </div>
                      )}
                    </div>
                  </div>
                ) : null}
              </div>
            </article>
          </section>
        </>
      ) : null}
    </div>
  );
}

function TrainingReadonlySection({ section, sampleId }: { section: TrainingSection; sampleId: string }) {
  return (
    <div className="trainingSectionStack">
      <div className="trainingSectionCard">
        <div className="trainingQuestionCardHead">
          <strong>{section.title || "未命名分区"}</strong>
          <span className="muted">{section.section_type || "未标注类型"} · {section.questions.length} 题</span>
        </div>
      </div>

      <div className="trainingQuestionList">
        {section.questions.map((question, questionIndex) => (
          <article key={`prediction-${questionIndex}`} className="trainingQuestionCard trainingQuestionCardReadonly">
            <div className="trainingQuestionCardHead">
              <strong>{question.question_no ? `第 ${question.question_no} 题` : `题目 ${questionIndex + 1}`}</strong>
              <span className="muted">{question.question_type || "未填写题型"}</span>
            </div>
            <div className="trainingQuestionGrid">
              <ReadonlyField label="题号" value={question.question_no} />
              <ReadonlyField label="题型" value={question.question_type} />
              <ReadonlyField label="答案" value={question.answer_text} />
              <ReadonlyField className="trainingFieldFull" label="题干" value={question.stem_text} multiline sampleId={sampleId} />
              <ReadonlyOptions options={question.options} sampleId={sampleId} />
              <ReadonlyField className="trainingFieldFull" label="解析" value={question.analysis_text} multiline sampleId={sampleId} />
            </div>
          </article>
        ))}
      </div>
    </div>
  );
}

type TrainingEditableSectionProps = {
  section: TrainingSection;
  sectionIndex: number;
  onSectionFieldChange: (sectionIndex: number, field: "title" | "section_type", value: string) => void;
  onQuestionFieldChange: (
    sectionIndex: number,
    questionIndex: number,
    field: Exclude<keyof TrainingQuestion, "options">,
    value: string
  ) => void;
  onOptionChange: (sectionIndex: number, questionIndex: number, optionIndex: number, value: string) => void;
  onAddOption: (sectionIndex: number, questionIndex: number) => void;
};

function TrainingEditableSection({
  section,
  sectionIndex,
  onSectionFieldChange,
  onQuestionFieldChange,
  onOptionChange,
  onAddOption,
}: TrainingEditableSectionProps) {
  return (
    <div className="trainingSectionStack">
      <div className="trainingSectionCard">
        <div className="trainingQuestionGrid">
          <label className="trainingField">
            <span>分区标题</span>
            <input
              className="input"
              value={section.title}
              onChange={(event) => onSectionFieldChange(sectionIndex, "title", event.target.value)}
            />
          </label>
          <label className="trainingField">
            <span>分区类型</span>
            <input
              className="input"
              value={section.section_type}
              onChange={(event) => onSectionFieldChange(sectionIndex, "section_type", event.target.value)}
            />
          </label>
          <div className="trainingField">
            <span>题目数</span>
            <div className="trainingFieldValue">{section.questions.length}</div>
          </div>
        </div>
      </div>

      <div className="trainingQuestionList">
        {section.questions.map((question, questionIndex) => (
          <article key={`gold-${questionIndex}`} className="trainingQuestionCard">
            <div className="trainingQuestionCardHead">
              <strong>{question.question_no ? `第 ${question.question_no} 题` : `题目 ${questionIndex + 1}`}</strong>
              <span className="muted">按字段填写后会自动保存成 JSON</span>
            </div>
            <div className="trainingQuestionGrid">
              <label className="trainingField">
                <span>题号</span>
                <input
                  className="input"
                  value={question.question_no}
                  onChange={(event) => onQuestionFieldChange(sectionIndex, questionIndex, "question_no", event.target.value)}
                />
              </label>
              <label className="trainingField">
                <span>题型</span>
                <input
                  className="input"
                  value={question.question_type}
                  onChange={(event) => onQuestionFieldChange(sectionIndex, questionIndex, "question_type", event.target.value)}
                />
              </label>
              <label className="trainingField">
                <span>答案</span>
                <input
                  className="input"
                  value={question.answer_text}
                  onChange={(event) => onQuestionFieldChange(sectionIndex, questionIndex, "answer_text", event.target.value)}
                />
              </label>
              <label className="trainingField trainingFieldFull">
                <span>题干</span>
                <textarea
                  className="trainingFormTextarea"
                  value={question.stem_text}
                  onChange={(event) => onQuestionFieldChange(sectionIndex, questionIndex, "stem_text", event.target.value)}
                  spellCheck={false}
                />
              </label>
              <div className="trainingField trainingFieldFull">
                <div className="trainingFieldLabelRow">
                  <span>选项</span>
                  <button className="button small" type="button" onClick={() => onAddOption(sectionIndex, questionIndex)}>
                    新增选项
                  </button>
                </div>
                <div className="trainingOptionList">
                  {question.options.map((option, optionIndex) => (
                    <div key={`option-${optionIndex}`} className="trainingOptionRow">
                      <textarea
                        className="trainingFormTextarea trainingOptionTextarea"
                        value={option}
                        onChange={(event) => onOptionChange(sectionIndex, questionIndex, optionIndex, event.target.value)}
                        spellCheck={false}
                      />
                    </div>
                  ))}
                  {!question.options.length ? <div className="empty compact">当前没有选项，点“新增选项”开始填写。</div> : null}
                </div>
              </div>
              <label className="trainingField trainingFieldFull">
                <span>解析</span>
                <textarea
                  className="trainingFormTextarea"
                  value={question.analysis_text}
                  onChange={(event) => onQuestionFieldChange(sectionIndex, questionIndex, "analysis_text", event.target.value)}
                  spellCheck={false}
                />
              </label>
            </div>
          </article>
        ))}
      </div>
    </div>
  );
}

function ReadonlyField({
  label,
  value,
  multiline = false,
  className = "",
  sampleId = "",
}: {
  label: string;
  value: string;
  multiline?: boolean;
  className?: string;
  sampleId?: string;
}) {
  return (
    <div className={`trainingField ${className}`.trim()}>
      <span>{label}</span>
      {multiline ? (
        <div
          className="trainingFieldValue trainingFieldValueMultiline paperPreviewHtml"
          dangerouslySetInnerHTML={{ __html: renderDocumentPreviewHtml(value || "—", (src) => resolveTrainingImageSrc(sampleId, src)) }}
        />
      ) : (
        <div className="trainingFieldValue">{value || "—"}</div>
      )}
    </div>
  );
}

function ReadonlyOptions({ options, sampleId = "" }: { options: string[]; sampleId?: string }) {
  return (
    <div className="trainingField trainingFieldFull">
      <span>选项</span>
      <div className="trainingOptionList">
        {options.length ? (
          options.map((option, index) => (
            <div
              key={`readonly-option-${index}`}
              className="trainingFieldValue trainingFieldValueMultiline paperPreviewHtml"
              dangerouslySetInnerHTML={{ __html: renderDocumentPreviewHtml(option, (src) => resolveTrainingImageSrc(sampleId, src)) }}
            />
          ))
        ) : (
          <div className="trainingFieldValue">—</div>
        )}
      </div>
    </div>
  );
}

function buildSectionTabs(primarySections: TrainingSection[], secondarySections: TrainingSection[]): TrainingSectionTab[] {
  const total = Math.max(primarySections.length, secondarySections.length);
  return Array.from({ length: total }, (_, index) => {
    const primary = primarySections[index];
    const secondary = secondarySections[index];
    return {
      title: primary?.title || secondary?.title || `分区 ${index + 1}`,
      section_type: primary?.section_type || secondary?.section_type || "",
      question_count: primary?.questions.length || secondary?.questions.length || 0,
    };
  });
}

function resolveTrainingImageSrc(sampleId: string, src: string) {
  if (!src.startsWith("imgs/")) {
    return src;
  }
  if (!sampleId) {
    return src;
  }
  return `/api/training/samples?sample_id=${encodeURIComponent(sampleId)}&image_path=${encodeURIComponent(src)}`;
}

function parseTrainingDocument(text: string, fallback?: TrainingDocument): TrainingDocument {
  const base = fallback ? cloneTrainingDocument(fallback) : createEmptyTrainingDocument();
  if (!text.trim()) {
    return base;
  }
  try {
    return normalizeTrainingDocument(JSON.parse(text), base);
  } catch {
    return base;
  }
}

function normalizeTrainingDocument(value: unknown, fallback: TrainingDocument): TrainingDocument {
  const record = asRecord(value);
  return {
    version: asFiniteNumber(record.version) || fallback.version || 1,
    label_status: asEditableString(record.label_status, fallback.label_status),
    notes: asEditableString(record.notes, fallback.notes),
    sections: normalizeSections(record.sections, fallback.sections),
  };
}

function normalizeSections(value: unknown, fallback: TrainingSection[]): TrainingSection[] {
  if (!Array.isArray(value)) {
    return fallback.map(cloneTrainingSection);
  }
  return value.map((section, index) => normalizeSection(section, fallback[index]));
}

function normalizeSection(value: unknown, fallback?: TrainingSection): TrainingSection {
  const record = asRecord(value);
  return {
    title: asEditableString(record.title, fallback?.title || ""),
    section_type: asEditableString(record.section_type, fallback?.section_type || ""),
    questions: normalizeQuestions(record.questions, fallback?.questions || []),
  };
}

function normalizeQuestions(value: unknown, fallback: TrainingQuestion[]): TrainingQuestion[] {
  if (!Array.isArray(value)) {
    return fallback.map(cloneTrainingQuestion);
  }
  return value.map((question, index) => normalizeQuestion(question, fallback[index]));
}

function normalizeQuestion(value: unknown, fallback?: TrainingQuestion): TrainingQuestion {
  const record = asRecord(value);
  return {
    question_no: asEditableString(record.question_no, fallback?.question_no || ""),
    question_type: asEditableString(record.question_type, fallback?.question_type || ""),
    stem_text: asEditableString(record.stem_text, fallback?.stem_text || ""),
    options: normalizeOptions(record.options, fallback?.options || []),
    answer_text: asEditableString(record.answer_text, fallback?.answer_text || ""),
    analysis_text: asEditableString(record.analysis_text, fallback?.analysis_text || ""),
  };
}

function normalizeOptions(value: unknown, fallback: string[]): string[] {
  if (!Array.isArray(value)) {
    return [...fallback];
  }
  return value.map((option) => (typeof option === "string" ? option : ""));
}

function serializeTrainingDocument(document: TrainingDocument): string {
  return `${JSON.stringify(
    {
      version: document.version || 1,
      label_status: document.label_status || "draft",
      notes: document.notes || "",
      sections: document.sections.map((section) => ({
        title: section.title,
        section_type: section.section_type,
        questions: section.questions.map((question) => ({
          question_no: question.question_no,
          question_type: question.question_type,
          stem_text: question.stem_text,
          options: question.options.filter((option) => option.trim()),
          answer_text: question.answer_text,
          analysis_text: question.analysis_text,
        })),
      })),
    },
    null,
    2
  )}\n`;
}

function createEmptyTrainingDocument(): TrainingDocument {
  return {
    version: 1,
    label_status: "draft",
    notes: "",
    sections: [],
  };
}

function cloneTrainingDocument(document: TrainingDocument): TrainingDocument {
  return {
    version: document.version,
    label_status: document.label_status,
    notes: document.notes,
    sections: document.sections.map(cloneTrainingSection),
  };
}

function cloneTrainingSection(section: TrainingSection): TrainingSection {
  return {
    title: section.title,
    section_type: section.section_type,
    questions: section.questions.map(cloneTrainingQuestion),
  };
}

function cloneTrainingQuestion(question: TrainingQuestion): TrainingQuestion {
  return {
    question_no: question.question_no,
    question_type: question.question_type,
    stem_text: question.stem_text,
    options: [...question.options],
    answer_text: question.answer_text,
    analysis_text: question.analysis_text,
  };
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" ? (value as Record<string, unknown>) : {};
}

function asEditableString(value: unknown, fallback = ""): string {
  return typeof value === "string" ? value : fallback;
}

function asFiniteNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function validateTrainingJsonText(text: string): string {
  if (!text.trim()) {
    return "gold.json 不能为空。";
  }
  try {
    const payload = JSON.parse(text);
    if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
      return "gold.json 顶层必须是 JSON 对象。";
    }
    return "";
  } catch (error) {
    return error instanceof Error ? `gold.json 不是合法 JSON：${error.message}` : "gold.json 不是合法 JSON。";
  }
}

function isPendingLabelStatus(status: string): boolean {
  const normalized = status.trim().toLowerCase();
  return !normalized || normalized === "draft" || normalized === "pending" || normalized === "todo";
}
