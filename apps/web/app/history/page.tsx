"use client";

import { useEffect, useRef, useState } from "react";
import { Clipboard, Download, RefreshCw, ShieldCheck, Trash2 } from "lucide-react";
import PublishPackagePreview, { formatPublishBody } from "../../components/PublishPackagePreview";
import ReviewActionList from "../../components/ReviewActionList";
import ReviewFloatingPanel from "../../components/ReviewFloatingPanel";
import {
  API_BASE,
  apiFetch,
  contentTypeLabels,
  GenerationJob,
  ReviewMode,
  reviewModeLabels,
} from "../../lib/api";

const reviewModeKey = "context-for-xhs:review-mode";
const reviewModes = Object.keys(reviewModeLabels) as ReviewMode[];

export default function HistoryPage() {
  const [jobs, setJobs] = useState<GenerationJob[]>([]);
  const [selected, setSelected] = useState<GenerationJob | null>(null);
  const [message, setMessage] = useState("");
  const [reviewingId, setReviewingId] = useState<string | null>(null);
  const [reviewMode, setReviewMode] = useState<ReviewMode>("hybrid");
  const [reviewPanelOpen, setReviewPanelOpen] = useState(false);
  const [highlightText, setHighlightText] = useState("");
  const markdownRef = useRef<HTMLPreElement | null>(null);

  async function loadJobs() {
    const data = await apiFetch<GenerationJob[]>("/api/history");
    setJobs(data);
    setSelected((current) => current || data[0] || null);
  }

  useEffect(() => {
    loadJobs().catch((error) => setMessage(error.message));
    try {
      const saved = window.localStorage.getItem(reviewModeKey) as ReviewMode | null;
      if (saved && saved in reviewModeLabels) setReviewMode(saved);
    } catch {
      // localStorage can be unavailable in strict privacy modes.
    }
  }, []);

  useEffect(() => {
    try {
      window.localStorage.setItem(reviewModeKey, reviewMode);
    } catch {
      // localStorage can be unavailable in strict privacy modes.
    }
  }, [reviewMode]);

  async function deleteJob(id: string) {
    await apiFetch(`/api/history/${id}`, { method: "DELETE" });
    setSelected(null);
    await loadJobs();
  }

  function updateJob(updated: GenerationJob) {
    setJobs((current) => current.map((job) => job.id === updated.id ? updated : job));
    setSelected((current) => current?.id === updated.id ? updated : current);
  }

  async function runContentReview(job: GenerationJob) {
    if (!job.result) return;
    setReviewingId(job.id);
    setHighlightText("");
    setReviewPanelOpen(true);
    setMessage("正在内容审查...");
    updateJob({ ...job, status: "reviewing" });
    try {
      const updated = await apiFetch<GenerationJob>(`/api/generate/${job.id}/review`, {
        method: "POST",
        body: JSON.stringify({ mode: reviewMode }),
      });
      updateJob(updated);
      setMessage("内容审查完成。");
      setSelected(updated);
      setReviewPanelOpen(true);
    } catch (error) {
      const fallback = await apiFetch<GenerationJob>(`/api/generate/${job.id}`).catch(() => null);
      if (fallback) updateJob(fallback);
      setMessage(error instanceof Error ? error.message : "内容审查失败");
    } finally {
      setReviewingId(null);
    }
  }

  function openReviewPanel() {
    if (!selected?.review) return;
    setReviewPanelOpen(true);
  }

  async function copyResult(job: GenerationJob) {
    if (!job.result) return;
    await navigator.clipboard.writeText(
      formatPublishBody(job.result.publish_package, job.result.raw_markdown)
    );
    setMessage("正文已复制。");
  }

  return (
    <>
      <header className="pageHeader">
        <div>
          <h1>历史 & 审查</h1>
          <p>回看所有生成任务，定位未核验结果、审查问题和发布包导出。</p>
        </div>
        <button className="button" type="button" onClick={loadJobs}>
          <RefreshCw size={17} />
          刷新
        </button>
      </header>

      <section className="splitResult">
        <div className="panel">
          <div className="panelHeader">
            <h2>任务列表</h2>
            <p>{jobs.length} 条记录</p>
          </div>
          <div className="panelBody">
            <div className="tableWrap">
              <table>
                <thead>
                  <tr>
                    <th>标题</th>
                    <th>模式</th>
                    <th>类型</th>
                    <th>审查</th>
                    <th>操作</th>
                  </tr>
                </thead>
                <tbody>
                  {jobs.map((job) => (
                    <tr key={job.id} onClick={() => setSelected(job)} style={{ cursor: "pointer" }}>
                      <td>
                        <strong>{job.result?.title || `${job.context.subject} 生成任务`}</strong>
                        <div className="muted">{new Date(job.created_at).toLocaleString()}</div>
                      </td>
                      <td>{job.context.mode}</td>
                      <td>{contentTypeLabels[job.context.content_type]}</td>
                      <td>
                        <span className={`badge ${job.status}`}>{job.status}</span>
                        {job.result?.unverified && <span className="badge unverified" style={{ marginLeft: 6 }}>未核验</span>}
                        {job.review ? (
                          <span className={job.review.pass_overall ? "badge pass" : "badge low"} style={{ marginLeft: 6 }}>
                            {job.review.pass_overall ? "通过" : "需复核"}
                          </span>
                        ) : job.result && job.status !== "reviewing" ? (
                          <span className="badge unverified" style={{ marginLeft: 6 }}>未审查</span>
                        ) : null}
                      </td>
                      <td>
                        <div className="buttonRow">
                          {job.result && (
                            <button
                              aria-label="复制正文"
                              className="button"
                              title="复制正文"
                              type="button"
                              onClick={(event) => {
                                event.stopPropagation();
                                copyResult(job).catch((error) => setMessage(error.message));
                              }}
                            >
                              <Clipboard size={16} />
                            </button>
                          )}
                          {job.result && (
                            <a className="button" href={`${API_BASE}/api/generate/${job.id}/export?format=md`}>
                              <Download size={16} />
                            </a>
                          )}
                          <button
                            className="button danger"
                            type="button"
                            onClick={(event) => {
                              event.stopPropagation();
                              deleteJob(job.id).catch((error) => setMessage(error.message));
                            }}
                          >
                            <Trash2 size={16} />
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {!jobs.length && <div className="empty">还没有历史记录。</div>}
            {message && <p className="muted">{message}</p>}
          </div>
        </div>

        <aside className="panel">
          <div className="panelHeader">
            <h2>审查报告</h2>
            <p>{selected ? selected.id : "选择一条任务查看详情"}</p>
          </div>
          <div className="panelBody formGrid">
            {!selected && <div className="empty">未选择任务。</div>}
            {selected && (
              <>
                <div className="buttonRow">
                  <span className={`badge ${selected.status}`}>{selected.status}</span>
                  {selected.review && (
                    <span className={selected.review.pass_overall ? "badge pass" : "badge low"}>
                      {selected.review.pass_overall ? "通过" : "需复核"}
                    </span>
                  )}
                  {selected.review?.strict_mode ? <span className="badge high">严格</span> : null}
                  {selected.review && !selected.review.strict_mode ? <span className="badge unverified">非严格</span> : null}
                  {selected.review && <span className="badge">{reviewModeLabels[selected.review.mode || "hybrid"]}</span>}
                  {selected.result && (
                    <button className="button" type="button" onClick={() => copyResult(selected)}>
                      <Clipboard size={16} />
                      复制正文
                    </button>
                  )}
                  {selected.result && (
                    <button
                      className="button"
                      disabled={reviewingId === selected.id || selected.status === "reviewing"}
                      type="button"
                      onClick={() => (selected.review ? openReviewPanel() : runContentReview(selected))}
                    >
                      <ShieldCheck size={16} />
                      内容审查
                    </button>
                  )}
                </div>
                {selected.result && (
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
                {selected.review?.unverified_warning && <p className="muted">{selected.review.unverified_warning}</p>}
              </>
            )}
          </div>
        </aside>
      </section>

      {selected?.result && (
        <section className="panel" style={{ marginTop: 18 }}>
          <div className="panelHeader">
            <div className="panelHeaderActions">
              <div>
                <h2>{selected.result.title}</h2>
                <p>小红书发布包预览</p>
              </div>
              <button className="button" type="button" onClick={() => copyResult(selected)}>
                <Clipboard size={16} />
                复制正文
              </button>
            </div>
          </div>
          <div className="panelBody">
            <PublishPackagePreview
              fallbackMarkdown={selected.result.raw_markdown}
              fallbackTitle={selected.result.title}
              packageData={selected.result.publish_package}
              refEl={markdownRef}
              highlightText={highlightText}
            />
          </div>
        </section>
      )}
      <ReviewFloatingPanel
        open={reviewPanelOpen}
        title="内容审查"
        subtitle={
          selected?.status === "reviewing"
            ? "正在内容审查..."
            : selected?.result?.title || selected?.id || "当前任务"
        }
        onClose={() => {
          setReviewPanelOpen(false);
        }}
      >
        {!selected ? (
          <div className="empty compact">未选择任务。</div>
        ) : selected.status === "reviewing" && !selected.review ? (
          <div className="empty compact">正在内容审查...</div>
        ) : selected.review ? (
          <div className="formGrid">
            <div className="buttonRow">
              <span className={selected.review.pass_overall ? "badge pass" : "badge low"}>
                {selected.review.pass_overall ? "审查通过" : "需复核"}
              </span>
              <span className="badge">{reviewModeLabels[selected.review.mode || "hybrid"]}</span>
              {selected.review.strict_mode ? <span className="badge high">严格</span> : <span className="badge unverified">非严格</span>}
              <button
                className="button"
                disabled={reviewingId === selected.id || selected.status === "reviewing"}
                type="button"
                onClick={() => runContentReview(selected)}
              >
                <RefreshCw size={16} />
                重新审查
              </button>
            </div>
            <ReviewActionList
              job={selected}
              markdownRef={markdownRef}
              onJobChange={updateJob}
              onLocate={setHighlightText}
              onMessage={setMessage}
            />
            <h3>建议</h3>
            <ul className="issueList">
              {(selected.review.suggestions.length ? selected.review.suggestions : ["无需额外建议。"]).map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
            <div className="reviewMeta">
              <span>审查模型：{selected.review.llm_used ? "已使用" : "未使用"}</span>
              <span>依据文档：{selected.review.evidence_source_count} 份</span>
            </div>
          </div>
        ) : (
          <div className="empty compact">尚未内容审查。</div>
        )}
      </ReviewFloatingPanel>
    </>
  );
}
