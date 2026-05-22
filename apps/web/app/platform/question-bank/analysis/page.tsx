"use client";

import Link from "next/link";
import { BarChart3, BrainCircuit, CalendarRange, Filter, RefreshCw, Sparkles } from "lucide-react";
import { useEffect, useMemo, useState, type CSSProperties } from "react";

import { LoadState } from "../../../../components/shared/LoadState";
import {
  apiFetch,
  QuestionBankAnalysisChapterItemResponse,
  QuestionBankAnalysisPointItemResponse,
  QuestionBankKnowledgeAnalysisResponse,
  SubjectCategoryResponse,
  SubjectResponse,
} from "../../../../lib/pro-api";
import { toErrorMessage, useLatestRequestGate } from "../../../../lib/request-guard";

type FilterState = {
  subjectId: string;
  categoryId: string;
  startYear: string;
  endYear: string;
};

const defaultFilters: FilterState = {
  subjectId: "",
  categoryId: "",
  startYear: "",
  endYear: "",
};

export default function QuestionBankAnalysisPage() {
  const gate = useLatestRequestGate();
  const [subjects, setSubjects] = useState<SubjectResponse[]>([]);
  const [categories, setCategories] = useState<SubjectCategoryResponse[]>([]);
  const [filters, setFilters] = useState<FilterState>(defaultFilters);
  const [report, setReport] = useState<QuestionBankKnowledgeAnalysisResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    void loadPage(defaultFilters);
  }, []);

  const scopedCategories = useMemo(() => {
    if (!filters.subjectId) return categories;
    return categories.filter((category) => category.subject_id === Number(filters.subjectId));
  }, [categories, filters.subjectId]);

  async function loadPage(nextFilters: FilterState) {
    const requestId = gate.begin();
    setLoading(true);
    setError("");
    try {
      const [subjectPayload, categoryPayload, reportPayload] = await Promise.all([
        apiFetch<SubjectResponse[]>("/api/knowledge/subjects"),
        apiFetch<SubjectCategoryResponse[]>("/api/knowledge/categories"),
        apiFetch<QuestionBankKnowledgeAnalysisResponse>(`/api/question-bank/analysis/knowledge-report${buildReportQuery(nextFilters)}`),
      ]);
      if (!gate.isCurrent(requestId)) return;
      setSubjects(subjectPayload);
      setCategories(categoryPayload);
      setReport(reportPayload);
    } catch (err) {
      if (!gate.isCurrent(requestId)) return;
      setError(toErrorMessage(err, "加载考点分析失败"));
      setReport(null);
    } finally {
      if (gate.isCurrent(requestId)) setLoading(false);
    }
  }

  async function refresh() {
    await loadPage(filters);
  }

  function onApplyFilters() {
    void loadPage(filters);
  }

  function onResetFilters() {
    const next = defaultFilters;
    setFilters(next);
    void loadPage(next);
  }

  const topPoints = report?.point_distribution.slice(0, 8) || [];
  const topChapters = report?.chapter_distribution.slice(0, 8) || [];
  const heatYears = report?.years || [];

  return (
    <div className="analysisPageShell">
      <section className="analysisHero">
        <div className="analysisHeroIntro">
          <span className="analysisEyebrow">Question Bank Intelligence</span>
          <h2>正式题库考点分析</h2>
          <p>
            基于正式题库中的已上架题目，以及其回溯到的正式试卷真题来源，统计主考点与章节频次，输出年度趋势与下一年关注预测。
          </p>
        </div>
        <div className="analysisHeroMeta">
          <div className="analysisMetaPill">
            <BarChart3 size={18} aria-hidden />
            <span>{report ? `${report.data_scope} · ${report.summary.paper_count} 套真题` : "正式题库 + 真题试卷"}</span>
          </div>
          <div className="analysisMetaPill">
            <BrainCircuit size={18} aria-hidden />
            <span>{report?.prediction_year ? `预测目标：${report.prediction_year} 年` : "预测目标：下一年"}</span>
          </div>
          <div className="analysisMetaPill">
            <Sparkles size={18} aria-hidden />
            <span>客观统计 + 可解释预测，不输出必考式结论</span>
          </div>
        </div>
      </section>

      <article className="panel analysisFilterPanel">
        <div className="panelHeader analysisFilterHeader">
          <div>
            <h2>
              <Filter size={18} aria-hidden />
              筛选范围
            </h2>
            <p>支持按学科、类目和年份区间筛选，统计范围固定为正式试卷中的真题样本。</p>
          </div>
          <div className="buttonRow">
            <button className="button" type="button" onClick={() => void refresh()} disabled={loading}>
              <RefreshCw size={16} aria-hidden />
              <span>{loading ? "刷新中..." : "刷新"}</span>
            </button>
            <Link className="button" href="/question-bank">
              返回正式题库
            </Link>
          </div>
        </div>
        <div className="panelBody analysisFilterGrid">
          <select
            className="input"
            value={filters.subjectId}
            onChange={(event) => setFilters((current) => ({ ...current, subjectId: event.target.value, categoryId: "" }))}
          >
            <option value="">全部学科</option>
            {subjects.map((subject) => (
              <option key={subject.id} value={subject.id}>
                {subject.name}
              </option>
            ))}
          </select>
          <select
            className="input"
            value={filters.categoryId}
            onChange={(event) => setFilters((current) => ({ ...current, categoryId: event.target.value }))}
          >
            <option value="">全部类目</option>
            {scopedCategories.map((category) => (
              <option key={category.id} value={category.id}>
                {category.name}
              </option>
            ))}
          </select>
          <input
            className="input"
            type="number"
            placeholder="开始年份"
            value={filters.startYear}
            onChange={(event) => setFilters((current) => ({ ...current, startYear: event.target.value }))}
          />
          <input
            className="input"
            type="number"
            placeholder="结束年份"
            value={filters.endYear}
            onChange={(event) => setFilters((current) => ({ ...current, endYear: event.target.value }))}
          />
          <button className="button primary" type="button" onClick={onApplyFilters}>
            应用筛选
          </button>
          <button className="button" type="button" onClick={onResetFilters}>
            重置
          </button>
        </div>
      </article>

      <LoadState loading={loading} error={error} empty={!loading && !report} emptyLabel="暂无可分析数据。" />

      {!loading && !error && report ? (
        <>
          <section className="dashboardGrid analysisStatsGrid">
            <StatCard label="纳入真题试卷" value={`${report.summary.paper_count}`} hint="仅统计正式试卷中标记为真题的样本" />
            <StatCard label="正式题来源题数" value={`${report.summary.source_question_count}`} hint="来自正式题库回溯到的真题题目" />
            <StatCard label="主考点覆盖率" value={formatPercent(report.summary.primary_coverage_rate)} hint="具备主考点标注的题目占比" />
            <StatCard label="主考点总数" value={`${report.summary.point_count}`} hint="具备有效频次的主考点数量" />
            <StatCard label="章节总数" value={`${report.summary.chapter_count}`} hint="按主考点所属章节汇总" />
            <StatCard label="Top5 集中度" value={formatPercent(report.summary.top_point_concentration_rate)} hint="前 5 主考点累计占比" />
          </section>

          <section className="analysisBoard">
            <div className="analysisMain">
              <article className="panel analysisSurface">
                <div className="panelHeader">
                  <h2>主考点考察频次分布</h2>
                  <p>横向频次条叠加年度微趋势，体现总量、热度和近年走向。</p>
                </div>
                <div className="panelBody">
                  <PointDistributionChart items={topPoints} years={report.years} />
                </div>
              </article>

              <article className="panel analysisSurface">
                <div className="panelHeader">
                  <h2>章节考察频次分布</h2>
                  <p>章节 × 年份热力矩阵，右侧补充累计频次与预测值。</p>
                </div>
                <div className="panelBody">
                  <ChapterHeatMatrix items={topChapters} years={heatYears} predictionYear={report.prediction_year} />
                </div>
              </article>
            </div>

            <aside className="analysisSide">
              <article className="panel analysisSurface">
                <div className="panelHeader">
                  <h2>年度样本</h2>
                  <p>方便判断各年份样本完整度。</p>
                </div>
                <div className="panelBody">
                  <div className="analysisHeatTable">
                    <div className="analysisHeatHeader">
                      <span>年份</span>
                      <span>试卷</span>
                      <span>题目</span>
                      <span>已标注</span>
                    </div>
                    {report.yearly_overview.map((year) => (
                      <div key={year.year} className="analysisHeatRow">
                        <strong>{year.year}</strong>
                        <span>{year.paper_count}</span>
                        <span>{year.source_question_count}</span>
                        <span>{year.tagged_source_question_count}</span>
                      </div>
                    ))}
                  </div>
                </div>
              </article>

              <article className="panel analysisSurface">
                <div className="panelHeader">
                  <h2>下一年预测</h2>
                  <p>输出高关注对象与对应证据。</p>
                </div>
                <div className="panelBody analysisFocusCard">
                  <PredictionList title="高关注主考点" items={report.top_predicted_points} />
                  <PredictionList title="高关注章节" items={report.top_predicted_chapters} />
                </div>
              </article>
            </aside>
          </section>

          <section className="analysisBoard" style={{ gridTemplateColumns: "minmax(0, 1fr)" }}>
            <article className="panel analysisSurface">
              <div className="panelHeader">
                <h2>分析报告</h2>
                <p>自动依据样本、频次、趋势和预测结果生成的客观说明。</p>
              </div>
              <div className="panelBody" style={{ display: "grid", gap: 12 }}>
                <InsightCard title="样本说明" content={report.report.overview} />
                <InsightCard title="主考点分析" content={report.report.point_insight} />
                <InsightCard title="章节分析" content={report.report.chapter_insight} />
                <InsightCard title="下年预测" content={report.report.forecast} />
                <InsightCard title="风险提示" content={report.report.disclaimer} />
              </div>
            </article>
          </section>
        </>
      ) : null}
    </div>
  );
}

function StatCard({ label, value, hint }: { label: string; value: string; hint: string }) {
  return (
    <article className="panel analysisStatCard">
      <div className="panelBody">
        <div className="questionMiniStat">
          <span>{label}</span>
          <strong>{value}</strong>
          <small className="muted">{hint}</small>
        </div>
      </div>
    </article>
  );
}

function InsightCard({ title, content }: { title: string; content: string }) {
  return (
    <div className="analysisInsightCard">
      <strong>{title}</strong>
      <p>{content}</p>
    </div>
  );
}

function PredictionList({
  title,
  items,
}: {
  title: string;
  items: QuestionBankKnowledgeAnalysisResponse["top_predicted_points"];
}) {
  return (
    <div className="analysisYearCard">
      <div className="analysisYearTop">
        <strong>{title}</strong>
        <CalendarRange size={16} aria-hidden />
      </div>
      {items.length ? (
        <div className="analysisBreakdownList">
          {items.map((item) => (
            <div key={item.key} className="analysisBreakdownRow">
              <span>{item.name}</span>
              <div className="analysisBreakdownTrack">
                <div className="analysisBreakdownFill" style={{ width: `${Math.max(10, item.confidence * 100)}%` }} />
              </div>
              <strong>{Math.round(item.confidence * 100)}%</strong>
            </div>
          ))}
        </div>
      ) : (
        <p className="muted">暂无可用预测结果。</p>
      )}
    </div>
  );
}

function PointDistributionChart({
  items,
  years,
}: {
  items: QuestionBankAnalysisPointItemResponse[];
  years: number[];
}) {
  if (!items.length) {
    return <div className="empty compact">暂无主考点频次数据。</div>;
  }
  const maxFrequency = Math.max(...items.map((item) => item.total_frequency), 1);
  return (
    <div className="analysisBars">
      {items.map((item, index) => (
        <div key={item.key} className="analysisBarRow">
          <div className="analysisPointCell">
            <strong>{item.name}</strong>
            <span className="muted">
              {item.chapter_name || "未绑定章节"} · {trendLabel(item.trend_label)}
            </span>
          </div>
          <div style={{ display: "grid", gap: 8 }}>
            <div className="analysisBarTrack">
              <div
                className="analysisBarFill"
                style={{
                  width: `${Math.max(8, (item.total_frequency / maxFrequency) * 100)}%`,
                  background: index < 3
                    ? "linear-gradient(90deg, #0f766e, #2563eb)"
                    : "linear-gradient(90deg, #1d8f7a, #5b8def)",
                }}
              />
            </div>
            <SparkLine values={item.yearly_frequency} years={years} />
          </div>
          <div className="analysisBarValue">
            <strong>{item.total_frequency}</strong>
            <div className="muted">{formatPercent(item.share)}</div>
          </div>
        </div>
      ))}
    </div>
  );
}

function SparkLine({ values, years }: { values: number[]; years: number[] }) {
  const width = 180;
  const height = 44;
  const padding = 4;
  const maxValue = Math.max(...values, 1);
  const points = values.map((value, index) => {
    const x = values.length <= 1 ? width / 2 : padding + ((width - padding * 2) * index) / (values.length - 1);
    const y = height - padding - ((height - padding * 2) * value) / maxValue;
    return `${x},${y}`;
  }).join(" ");
  return (
    <svg width="100%" height={height} viewBox={`0 0 ${width} ${height}`} role="img" aria-label={years.length ? `年度趋势：${years.join("、")}` : "年度趋势"}>
      <defs>
        <linearGradient id="spark-gradient" x1="0%" y1="0%" x2="100%" y2="0%">
          <stop offset="0%" stopColor="#f97316" />
          <stop offset="100%" stopColor="#0ea5e9" />
        </linearGradient>
      </defs>
      <path d={`M ${points.replace(/ /g, " L ")}`} fill="none" stroke="url(#spark-gradient)" strokeWidth="2.5" strokeLinecap="round" />
      {values.map((value, index) => {
        const x = values.length <= 1 ? width / 2 : padding + ((width - padding * 2) * index) / (values.length - 1);
        const y = height - padding - ((height - padding * 2) * value) / maxValue;
        return <circle key={`${index}-${value}`} cx={x} cy={y} r="2.6" fill="#0f766e" />;
      })}
    </svg>
  );
}

function ChapterHeatMatrix({
  items,
  years,
  predictionYear,
}: {
  items: QuestionBankAnalysisChapterItemResponse[];
  years: number[];
  predictionYear?: number | null;
}) {
  if (!items.length) {
    return <div className="empty compact">暂无章节频次数据。</div>;
  }
  const maxValue = Math.max(...items.flatMap((item) => [...item.yearly_frequency, item.prediction_frequency]), 1);
  return (
    <div className="analysisHeatTable">
      <div className="analysisHeatHeader" style={{ gridTemplateColumns: `minmax(220px, 1.4fr) repeat(${years.length + 2}, minmax(72px, 1fr))` }}>
        <span>章节</span>
        {years.map((year) => (
          <span key={year}>{year}</span>
        ))}
        <span>累计</span>
        <span>{predictionYear || "预测"}</span>
      </div>
      {items.map((item) => (
        <div key={item.key} className="analysisHeatRow" style={{ gridTemplateColumns: `minmax(220px, 1.4fr) repeat(${years.length + 2}, minmax(72px, 1fr))` }}>
          <strong>{item.name}</strong>
          {item.yearly_frequency.map((value, index) => (
            <HeatCell key={`${item.key}-${years[index]}`} value={value} intensity={value / maxValue} />
          ))}
          <HeatCell value={item.total_frequency} intensity={item.total_frequency / maxValue} accent="sum" />
          <HeatCell value={item.prediction_frequency} intensity={item.prediction_frequency / maxValue} accent="forecast" />
        </div>
      ))}
    </div>
  );
}

function HeatCell({
  value,
  intensity,
  accent = "normal",
}: {
  value: number;
  intensity: number;
  accent?: "normal" | "sum" | "forecast";
}) {
  const style = {
    ["--heat" as string]: `${Math.max(0.08, Math.min(0.78, intensity))}`,
    background:
      accent === "forecast"
        ? "linear-gradient(135deg, rgba(250, 204, 21, 0.22), rgba(56, 189, 248, 0.28)), repeating-linear-gradient(135deg, rgba(255,255,255,0.55) 0, rgba(255,255,255,0.55) 8px, rgba(255,255,255,0.2) 8px, rgba(255,255,255,0.2) 16px)"
        : accent === "sum"
          ? "linear-gradient(180deg, rgba(255,255,255,0.96), rgba(248,250,253,0.94)), linear-gradient(135deg, rgba(249,115,22,0.28), rgba(37,99,235,0.28))"
          : undefined,
  } as CSSProperties;
  return (
    <div className="analysisHeatCellWrap">
      <div className="analysisHeatCell" style={style}>
        <span>{value}</span>
      </div>
    </div>
  );
}

function buildReportQuery(filters: FilterState) {
  const params = new URLSearchParams();
  if (filters.subjectId) params.set("subject_id", filters.subjectId);
  if (filters.categoryId) params.set("category_id", filters.categoryId);
  if (filters.startYear) params.set("start_year", filters.startYear);
  if (filters.endYear) params.set("end_year", filters.endYear);
  const suffix = params.toString();
  return suffix ? `?${suffix}` : "";
}

function formatPercent(value: number) {
  return `${Math.round(value * 100)}%`;
}

function trendLabel(value: string) {
  if (value === "rising") return "升温";
  if (value === "falling") return "回落";
  if (value === "sporadic") return "波动";
  return "稳定";
}
