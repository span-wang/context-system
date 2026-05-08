"use client";

import { BarChart3, Filter, Flame, Layers3, TrendingUp } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { LoadState } from "../../../../components/shared/LoadState";
import { StatusBadge } from "../../../../components/shared/StatusBadge";
import { toErrorMessage, useLatestRequestGate } from "../../../../lib/request-guard";
import {
  AnalysisChapterRow,
  AnalysisMetric,
  AnalysisPointRow,
  AnalysisPointYearStat,
  apiFetch,
  KnowledgeAnalysisResponse,
  SubjectResponse,
} from "../../../../lib/pro-api";

type FilterState = {
  subjectId: string;
  yearFrom: string;
  yearTo: string;
  questionType: string;
  paperType: string;
  region: string;
};

const defaultFilters: FilterState = {
  subjectId: "",
  yearFrom: "",
  yearTo: "",
  questionType: "",
  paperType: "",
  region: "",
};

export default function KnowledgeAnalysisPage() {
  const [subjects, setSubjects] = useState<SubjectResponse[]>([]);
  const [analysis, setAnalysis] = useState<KnowledgeAnalysisResponse | null>(null);
  const [filters, setFilters] = useState<FilterState>(defaultFilters);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const requestGate = useLatestRequestGate();

  useEffect(() => {
    void loadInitialPage();
  }, []);

  async function loadInitialPage() {
    const requestId = requestGate.begin();
    setLoading(true);
    setError("");
    try {
      const subjectList = await apiFetch<SubjectResponse[]>("/api/knowledge/subjects");
      if (!requestGate.isCurrent(requestId)) return;
      const subjectId = subjectList[0] ? String(subjectList[0].id) : "";
      const initialFilters = { ...defaultFilters, subjectId };
      const overview = await apiFetch<KnowledgeAnalysisResponse>(buildOverviewPath(initialFilters));
      if (!requestGate.isCurrent(requestId)) return;
      setSubjects(subjectList);
      setAnalysis(overview);
      setFilters(initialFilters);
    } catch (err) {
      if (!requestGate.isCurrent(requestId)) return;
      setError(toErrorMessage(err, "加载考点分析失败"));
    } finally {
      if (requestGate.isCurrent(requestId)) setLoading(false);
    }
  }

  async function loadPage(nextFilters: FilterState) {
    const requestId = requestGate.begin();
    setLoading(true);
    setError("");
    try {
      const [subjectList, overview] = await Promise.all([
        apiFetch<SubjectResponse[]>("/api/knowledge/subjects"),
        apiFetch<KnowledgeAnalysisResponse>(buildOverviewPath(nextFilters)),
      ]);
      if (!requestGate.isCurrent(requestId)) return;
      setSubjects(subjectList);
      setAnalysis(overview);
      setFilters(nextFilters);
    } catch (err) {
      if (!requestGate.isCurrent(requestId)) return;
      setError(toErrorMessage(err, "加载考点分析失败"));
    } finally {
      if (requestGate.isCurrent(requestId)) setLoading(false);
    }
  }

  async function applyFilters(nextFilters = filters) {
    await loadPage(nextFilters);
  }

  const topPoints = useMemo(() => analysis?.points.slice(0, 8) || [], [analysis]);
  const focusPoint = topPoints[0] || null;
  const heatYears = analysis?.years || [];
  const chapterRows = analysis?.chapters.slice(0, 8) || [];

  return (
    <>
      <header className="pageHeader">
        <div>
          <h1>考点分析</h1>
          <p>按学科、年份、题型与试卷范围，查看考点频次、分值、章节权重和题型结构，支持从趋势回到原始教学重点。</p>
        </div>
      </header>

      <section className="analysisHero">
        <div className="analysisHeroIntro">
          <span className="analysisEyebrow">Knowledge Intelligence</span>
          <h2>让题目数据真正变成教研判断</h2>
          <p>这页不是简单排行榜，而是一套围绕“考点、年份、题型、章节”的分析驾驶舱，适合老师、教研和内容运营直接使用。</p>
        </div>
        <div className="analysisHeroMeta">
          <div className="analysisMetaPill">
            <Flame size={16} aria-hidden="true" />
            <span>高频考点 + 高分值考点双口径</span>
          </div>
          <div className="analysisMetaPill">
            <TrendingUp size={16} aria-hidden="true" />
            <span>年度趋势、连续出现、升温判断</span>
          </div>
          <div className="analysisMetaPill">
            <Layers3 size={16} aria-hidden="true" />
            <span>章节占比、题型占比、分值结构</span>
          </div>
        </div>
      </section>

      <section className="panel analysisFilterPanel">
        <div className="panelHeader">
          <div className="analysisFilterHeader">
            <div>
              <h2>
                <Filter size={18} aria-hidden="true" />
                分析范围
              </h2>
              <p>建议先按学科与年份范围收窄，再看高频考点和章节重心。</p>
            </div>
            <div className="buttonRow">
              <button className="button" type="button" onClick={() => void applyFilters(defaultFilters)}>
                重置筛选
              </button>
              <button className="button primary" type="button" onClick={() => void applyFilters()}>
                刷新分析
              </button>
            </div>
          </div>
        </div>
        <div className="panelBody">
          <div className="analysisFilterGrid">
            <label className="field">
              <span>学科</span>
              <select value={filters.subjectId} onChange={(event) => setFilters((current) => ({ ...current, subjectId: event.target.value }))}>
                <option value="">全部学科</option>
                {subjects.map((subject) => (
                  <option key={subject.id} value={subject.id}>
                    {subject.name}
                  </option>
                ))}
              </select>
            </label>
            <label className="field">
              <span>起始年份</span>
              <select value={filters.yearFrom} onChange={(event) => setFilters((current) => ({ ...current, yearFrom: event.target.value }))}>
                <option value="">不限</option>
                {analysis?.available_years.map((year) => (
                  <option key={`from-${year}`} value={year}>
                    {year}
                  </option>
                ))}
              </select>
            </label>
            <label className="field">
              <span>结束年份</span>
              <select value={filters.yearTo} onChange={(event) => setFilters((current) => ({ ...current, yearTo: event.target.value }))}>
                <option value="">不限</option>
                {analysis?.available_years.map((year) => (
                  <option key={`to-${year}`} value={year}>
                    {year}
                  </option>
                ))}
              </select>
            </label>
            <label className="field">
              <span>题型</span>
              <select value={filters.questionType} onChange={(event) => setFilters((current) => ({ ...current, questionType: event.target.value }))}>
                <option value="">全部题型</option>
                {analysis?.available_question_types.map((item) => (
                  <option key={item.value} value={item.value}>
                    {item.label}
                  </option>
                ))}
              </select>
            </label>
            <label className="field">
              <span>试卷类型</span>
              <select value={filters.paperType} onChange={(event) => setFilters((current) => ({ ...current, paperType: event.target.value }))}>
                <option value="">全部试卷</option>
                {analysis?.available_paper_types.map((item) => (
                  <option key={item} value={item}>
                    {item}
                  </option>
                ))}
              </select>
            </label>
            <label className="field">
              <span>地区</span>
              <select value={filters.region} onChange={(event) => setFilters((current) => ({ ...current, region: event.target.value }))}>
                <option value="">全部地区</option>
                {analysis?.available_regions.map((item) => (
                  <option key={item} value={item}>
                    {item}
                  </option>
                ))}
              </select>
            </label>
          </div>
        </div>
      </section>

      <LoadState loading={loading} error={error} empty={!analysis} emptyLabel="暂无考点分析数据" />

      {analysis && (
        <>
          <section className="statsGrid analysisStatsGrid">
            {analysis.summary_metrics.map((metric) => (
              <AnalysisStatCard key={metric.key} metric={metric} />
            ))}
          </section>

          <section className="analysisBoard">
            <div className="analysisMain">
              <div className="panel analysisSurface">
                <div className="panelHeader">
                  <h2>
                    <BarChart3 size={18} aria-hidden="true" />
                    年度考点热度矩阵
                  </h2>
                  <p>横向看年份，纵向看高频考点，颜色越深表示当年该考点分值占比越高。</p>
                </div>
                <div className="panelBody">
                  <div className="analysisHeatTable">
                    <div className="analysisHeatHeader">
                      <span>考点</span>
                      {heatYears.map((year) => (
                        <span key={year.label}>{year.label.replace(" 年", "")}</span>
                      ))}
                    </div>
                    {topPoints.map((point) => (
                      <div key={point.knowledge_point_id} className="analysisHeatRow">
                        <strong>{point.knowledge_point_name}</strong>
                        {heatYears.map((year) => {
                          const stat = point.yearly_stats.find((item) => item.year === year.year);
                          return (
                            <div key={`${point.knowledge_point_id}-${year.label}`} className="analysisHeatCellWrap">
                              <div
                                className="analysisHeatCell"
                                style={{ ["--heat" as string]: String(Math.max(0.12, stat?.score_share || 0)) }}
                                title={
                                  stat
                                    ? `${year.label}：${stat.frequency} 次，${stat.score.toFixed(1)} 分，占比 ${(stat.score_share * 100).toFixed(1)}%`
                                    : `${year.label}：未出现`
                                }
                              >
                                <span>{stat ? `${stat.frequency}/${stat.score.toFixed(0)}` : "-"}</span>
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    ))}
                  </div>
                </div>
              </div>

              <div className="dashboardGrid">
                <div className="panel analysisSurface">
                  <div className="panelHeader">
                    <h2>章节分值占比</h2>
                    <p>章节维度适合看复习和命题重心。</p>
                  </div>
                  <div className="panelBody analysisBars">
                    {chapterRows.map((chapter) => (
                      <ChapterBar key={chapter.chapter_id} chapter={chapter} />
                    ))}
                  </div>
                </div>

                <div className="panel analysisSurface">
                  <div className="panelHeader">
                    <h2>重点考点画像</h2>
                    <p>展示当前热点考点的题型结构、连续出现情况和分值表现。</p>
                  </div>
                  <div className="panelBody">
                    {focusPoint ? <FocusPointCard point={focusPoint} /> : <div className="empty compact">暂无热点考点</div>}
                  </div>
                </div>
              </div>

              <div className="panel analysisSurface">
                <div className="panelHeader">
                  <h2>考点矩阵</h2>
                  <p>同时看频次、分值、分值占比、主力题型、连续出现和重要度，适合作为精细化教研面板。</p>
                </div>
                <div className="panelBody">
                  <div className="analysisTable">
                    <div className="analysisTableHead">
                      <span>考点</span>
                      <span>章节</span>
                      <span>频次</span>
                      <span>分值</span>
                      <span>分值占比</span>
                      <span>题型结构</span>
                      <span>连续出现</span>
                      <span>评级</span>
                    </div>
                    {analysis.points.map((point) => (
                      <PointRow key={point.knowledge_point_id} point={point} />
                    ))}
                  </div>
                </div>
              </div>
            </div>

            <aside className="analysisSide">
              <div className="panel analysisSurface">
                <div className="panelHeader">
                  <h2>数据洞察</h2>
                  <p>把统计结果翻译成老师可直接理解的结论。</p>
                </div>
                <div className="panelBody stackList">
                  {analysis.insights.map((item) => (
                    <article key={item.title} className="analysisInsightCard">
                      <strong>{item.title}</strong>
                      <p>{item.description}</p>
                    </article>
                  ))}
                </div>
              </div>

              <div className="panel analysisSurface">
                <div className="panelHeader">
                  <h2>年度概览</h2>
                  <p>看每一年的题量、覆盖率和总分变化。</p>
                </div>
                <div className="panelBody stackList">
                  {analysis.years.map((year) => (
                    <article key={year.label} className="analysisYearCard">
                      <div className="analysisYearTop">
                        <strong>{year.label}</strong>
                        <StatusBadge value={`${year.total_score.toFixed(1)} 分`} tone="info" />
                      </div>
                      <div className="metaLine">
                        <span>{year.paper_count} 份试卷</span>
                        <span>{year.question_count} 道题</span>
                        <span>{year.mapped_question_count} 道已映射</span>
                      </div>
                    </article>
                  ))}
                </div>
              </div>
            </aside>
          </section>
        </>
      )}
    </>
  );
}

function AnalysisStatCard({ metric }: { metric: AnalysisMetric }) {
  return (
    <article className="statCard analysisStatCard">
      <span>{metric.label}</span>
      <strong>{metric.value}</strong>
      <small>{metric.helper || "当前分析范围"}</small>
    </article>
  );
}

function ChapterBar({ chapter }: { chapter: AnalysisChapterRow }) {
  return (
    <div className="analysisBarRow">
      <div>
        <strong>{chapter.chapter_name}</strong>
        <span className="muted">
          {chapter.frequency} 次 · {chapter.point_count} 个考点 · {chapter.paper_coverage} 份试卷
        </span>
      </div>
      <div className="analysisBarTrack">
        <div className="analysisBarFill" style={{ width: `${Math.max(6, chapter.score_share * 100)}%` }} />
      </div>
      <strong className="analysisBarValue">{(chapter.score_share * 100).toFixed(1)}%</strong>
    </div>
  );
}

function FocusPointCard({ point }: { point: AnalysisPointRow }) {
  return (
    <div className="analysisFocusCard">
      <div className="analysisFocusTop">
        <div>
          <strong>{point.knowledge_point_name}</strong>
          <span className="muted">{point.chapter_path || "未归属章节"}</span>
        </div>
        <StatusBadge value={point.importance_level} tone={badgeTone(point.importance_level)} />
      </div>
      <div className="analysisFocusMetrics">
        <div>
          <span>总频次</span>
          <strong>{point.frequency}</strong>
        </div>
        <div>
          <span>总分值</span>
          <strong>{point.total_score.toFixed(1)}</strong>
        </div>
        <div>
          <span>分值占比</span>
          <strong>{(point.score_share * 100).toFixed(1)}%</strong>
        </div>
      </div>
      <div className="analysisBreakdownList">
        {point.type_breakdown.map((item) => (
          <div key={item.question_type} className="analysisBreakdownRow">
            <span>{item.question_type_label}</span>
            <div className="analysisBreakdownTrack">
              <div className="analysisBreakdownFill" style={{ width: `${Math.max(5, item.count_share * 100)}%` }} />
            </div>
            <strong>{(item.count_share * 100).toFixed(0)}%</strong>
          </div>
        ))}
      </div>
      <div className="metaLine">
        <span>连续出现 {point.continuous_years} 年</span>
        <span>主力题型 {point.dominant_question_type_label || "-"}</span>
        <span>最近年份 {point.last_seen_year || "-"}</span>
      </div>
    </div>
  );
}

function PointRow({ point }: { point: AnalysisPointRow }) {
  return (
    <div className="analysisTableRow">
      <div className="analysisPointCell">
        <strong>{point.knowledge_point_name}</strong>
        <span className="muted">{point.category_name || "未分类"}</span>
      </div>
      <span>{point.chapter_name || "-"}</span>
      <span>{point.frequency}</span>
      <span>{point.total_score.toFixed(1)}</span>
      <span>{(point.score_share * 100).toFixed(1)}%</span>
      <span>{point.type_breakdown.map((item) => `${item.question_type_label} ${(item.count_share * 100).toFixed(0)}%`).join(" / ")}</span>
      <span>{point.continuous_years} 年</span>
      <StatusBadge value={point.importance_level} tone={badgeTone(point.importance_level)} />
    </div>
  );
}

function badgeTone(level: string): "good" | "warn" | "danger" | "info" {
  if (level === "S") return "danger";
  if (level === "A") return "warn";
  if (level === "B") return "good";
  return "info";
}

function buildOverviewPath(filters: FilterState): string {
  const params = new URLSearchParams();
  if (filters.subjectId) params.set("subject_id", filters.subjectId);
  if (filters.yearFrom) params.set("year_from", filters.yearFrom);
  if (filters.yearTo) params.set("year_to", filters.yearTo);
  if (filters.questionType) params.set("question_type", filters.questionType);
  if (filters.paperType) params.set("paper_type", filters.paperType);
  if (filters.region) params.set("region", filters.region);
  const query = params.toString();
  return `/api/analysis/knowledge-overview${query ? `?${query}` : ""}`;
}
