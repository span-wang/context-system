"use client";

import { useEffect, useState } from "react";
import { API_BASE, apiFetch, FrequencyResponse, ReportResponse, TrendResponse } from "../../../../lib/pro-api";
import { LoadState } from "../../../../components/shared/LoadState";
import { StatusBadge } from "../../../../components/shared/StatusBadge";
import {
  allRejected,
  firstRejectedReason,
  summarizeRejectedRequests,
  toErrorMessage,
  useLatestRequestGate,
} from "../../../../lib/request-guard";

export default function ReportsPage() {
  const [reports, setReports] = useState<ReportResponse[]>([]);
  const [frequencies, setFrequencies] = useState<FrequencyResponse[]>([]);
  const [trends, setTrends] = useState<TrendResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [loadWarning, setLoadWarning] = useState("");
  const requestGate = useLatestRequestGate();

  async function loadData() {
    const requestId = requestGate.begin();
    setLoading(true);
    setError("");
    setLoadWarning("");
    try {
      const [nextReports, nextFrequencies, nextTrends] = await Promise.allSettled([
        apiFetch<ReportResponse[]>("/api/analysis/reports"),
        apiFetch<FrequencyResponse[]>("/api/analysis/frequencies"),
        apiFetch<TrendResponse[]>("/api/analysis/trends"),
      ]);

      if (!requestGate.isCurrent(requestId)) return;

      const results = [nextReports, nextFrequencies, nextTrends];
      if (allRejected(results)) {
        throw firstRejectedReason(results) || new Error("No report requests succeeded.");
      }

      setReports(nextReports.status === "fulfilled" ? nextReports.value : []);
      setFrequencies(nextFrequencies.status === "fulfilled" ? nextFrequencies.value : []);
      setTrends(nextTrends.status === "fulfilled" ? nextTrends.value : []);
      setLoadWarning(
        summarizeRejectedRequests([
          { label: "分析报告", result: nextReports },
          { label: "高频考点", result: nextFrequencies },
          { label: "年度趋势", result: nextTrends },
        ]),
      );
    } catch (err) {
      if (!requestGate.isCurrent(requestId)) return;
      setError(toErrorMessage(err, "加载报告失败"));
    } finally {
      if (requestGate.isCurrent(requestId)) setLoading(false);
    }
  }

  useEffect(() => {
    loadData();
  }, []);

  async function generateReport() {
    setGenerating(true);
    setMessage("");
    setError("");
    try {
      const report = await apiFetch<ReportResponse>("/api/analysis/reports/generate", {
        method: "POST",
        body: JSON.stringify({ report_type: "hot_knowledge" }),
      });
      setMessage(`已生成报告：${report.report_name}`);
      await loadData();
    } catch (err) {
      setError(toErrorMessage(err, "生成报告失败"));
    } finally {
      setGenerating(false);
    }
  }

  return (
    <>
      <header className="pageHeader">
        <div>
          <h1>报告中心</h1>
          <p>报告列表、高频考点和趋势图分别加载，避免单个接口抖动时整页看起来像数据缺失。</p>
        </div>
        <button className="button primary" type="button" disabled={generating} onClick={generateReport}>
          {generating ? "生成中..." : "生成当前报告"}
        </button>
      </header>

      {message && <div className="calloutBox">{message}</div>}
      {loadWarning && <div className="calloutBox">{loadWarning}</div>}

      <LoadState
        loading={loading}
        error={error}
        empty={!reports.length && !frequencies.length && !trends.length}
        emptyLabel="暂无报告数据"
      />

      {!loading && !error && (
        <section className="dashboardGrid">
          <div className="panel">
            <div className="panelHeader">
              <h2>分析报告</h2>
              <p>当前已生成的报告快照。</p>
            </div>
            <div className="panelBody">
              <div className="stackList">
                {reports.map((report) => (
                  <article key={report.id} className="infoCard">
                    <div className="infoCardTop">
                      <strong>{report.report_name}</strong>
                      <StatusBadge value={report.status} tone={report.status === "ready" ? "good" : "warn"} />
                    </div>
                    <p>{String(report.report_json?.summary || "已生成报告结构，待补充导出能力。")}</p>
                    <div className="metaLine">
                      <span>{report.report_type}</span>
                      <span>v{report.version_no}</span>
                      <span>{report.snapshot_date || "未记录日期"}</span>
                      <span>
                        <a href={`${API_BASE}/api/analysis/reports/${report.id}/export.md`}>导出 Markdown</a>
                      </span>
                    </div>
                  </article>
                ))}
              </div>
            </div>
          </div>

          <div className="panel">
            <div className="panelHeader">
              <h2>高频考点榜</h2>
              <p>按频次统计的热点考点。</p>
            </div>
            <div className="panelBody">
              <div className="metricTable">
                {frequencies.map((item) => (
                  <div key={item.knowledge_point_id} className="metricRow">
                    <div>
                      <strong>{item.knowledge_point_name}</strong>
                      <span className="muted">出现 {item.question_count} 次，覆盖 {item.paper_count} 份试卷</span>
                    </div>
                    <StatusBadge value={`Hot ${item.hot_score}`} tone="good" />
                  </div>
                ))}
              </div>
            </div>
          </div>

          <div className="panel sectionSpan2">
            <div className="panelHeader">
              <h2>年度趋势</h2>
              <p>当前演示数据的年份分布。</p>
            </div>
            <div className="panelBody">
              <div className="metricTable">
                {trends.map((item, index) => (
                  <div key={`${item.label}-${index}`} className="metricRow">
                    <div>
                      <strong>{item.label}</strong>
                      <span className="muted">原始题抽取数量</span>
                    </div>
                    <StatusBadge value={item.question_count} tone="info" />
                  </div>
                ))}
              </div>
            </div>
          </div>
        </section>
      )}
    </>
  );
}
