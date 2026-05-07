"use client";

import { useEffect, useState } from "react";
import { apiFetch, DashboardResponse } from "../../../../lib/pro-api";
import { LoadState } from "../../../../components/shared/LoadState";
import { StatusBadge } from "../../../../components/shared/StatusBadge";
import { toErrorMessage, useLatestRequestGate } from "../../../../lib/request-guard";

export default function AnalysisDashboardPage() {
  const [data, setData] = useState<DashboardResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const requestGate = useLatestRequestGate();

  useEffect(() => {
    async function load() {
      const requestId = requestGate.begin();
      setLoading(true);
      setError("");
      try {
        const next = await apiFetch<DashboardResponse>("/api/analysis/dashboard");
        if (!requestGate.isCurrent(requestId)) return;
        setData(next);
      } catch (err) {
        if (!requestGate.isCurrent(requestId)) return;
        setError(toErrorMessage(err, "加载分析看板失败"));
      } finally {
        if (requestGate.isCurrent(requestId)) setLoading(false);
      }
    }
    load();
  }, []);

  return (
    <>
      <header className="pageHeader">
        <div>
          <h1>分析看板</h1>
          <p>看板请求只认最后一次返回，避免旧请求在切页或重载后覆盖新状态。</p>
        </div>
      </header>

      <LoadState loading={loading} error={error} empty={!data} emptyLabel="暂无分析看板数据" />

      {data && (
        <>
          <section className="statsGrid">
            {data.metrics.map((metric) => (
              <article key={metric.key} className="statCard">
                <span>{metric.label}</span>
                <strong>{metric.value}</strong>
                <small>{metric.trend || "已接入骨架"}</small>
              </article>
            ))}
          </section>

          <section className="dashboardGrid">
            <div className="panel">
              <div className="panelHeader">
                <h2>高频考点</h2>
                <p>根据题目与考点映射统计出来的热点分布。</p>
              </div>
              <div className="panelBody">
                <div className="metricTable">
                  {data.focus_points.map((item) => (
                    <div key={item.knowledge_point_id} className="metricRow">
                      <div>
                        <strong>{item.knowledge_point_name}</strong>
                        <span className="muted">出现 {item.frequency} 次，覆盖 {item.paper_coverage} 份试卷</span>
                      </div>
                      <StatusBadge value={`Hot ${item.hot_score}`} tone="good" />
                    </div>
                  ))}
                </div>
              </div>
            </div>

            <div className="panel">
              <div className="panelHeader">
                <h2>任务提示</h2>
                <p>当前阶段最关键的待处理事项。</p>
              </div>
              <div className="panelBody stackList">
                <div className="detailRow">
                  <span>待复核任务</span>
                  <StatusBadge value={data.pending_reviews} tone={data.pending_reviews > 0 ? "warn" : "good"} />
                </div>
                <div className="detailRow">
                  <span>最新报告</span>
                  <strong>{data.latest_report_name || "暂无报告"}</strong>
                </div>
              </div>
            </div>
          </section>
        </>
      )}
    </>
  );
}
