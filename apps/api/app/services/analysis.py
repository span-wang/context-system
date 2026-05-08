from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date
from statistics import mean

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models import AnalysisReport, Chapter, ExamPaper, ExamQuestion, KnowledgePoint, QuestionKnowledgeLink
from app.repositories.analysis import AnalysisRepository
from app.repositories.workflow import WorkflowRepository
from app.schemas.analysis import (
    AnalysisChapterRow,
    AnalysisChapterYearStat,
    AnalysisFilterOption,
    AnalysisInsight,
    AnalysisMetric,
    AnalysisPointRow,
    AnalysisPointYearStat,
    AnalysisTypeBreakdown,
    AnalysisYearSummary,
    KnowledgeAnalysisResponse,
    AnalysisJobResponse,
    DashboardFocusItem,
    DashboardMetric,
    DashboardResponse,
    FrequencyResponse,
    GenerateReportRequest,
    ReportResponse,
    TrendResponse,
)


class FrequencyAnalysisService:
    def __init__(self, session: Session) -> None:
        self.repository = AnalysisRepository(session)
        self.workflow_repository = WorkflowRepository(session)

    def get_dashboard(self) -> DashboardResponse:
        subjects = self.repository.list_subjects()
        papers = self.repository.list_papers()
        questions = self.repository.list_questions()
        reports = self.repository.list_reports()
        review_tasks = self.workflow_repository.list_review_tasks()
        focus_points = self.list_frequencies()[:5]
        metrics = [
            DashboardMetric(key="subjects", label="学科数", value=str(len(subjects)), trend="底座已预留多租户"),
            DashboardMetric(key="papers", label="试卷数", value=str(len(papers)), trend="已接入试卷中心"),
            DashboardMetric(key="questions", label="原始题数", value=str(len(questions)), trend="支持原始题/标准题分层"),
            DashboardMetric(key="reports", label="分析报告数", value=str(len(reports)), trend="报告中心已通路由"),
        ]
        return DashboardResponse(
            metrics=metrics,
            focus_points=[
                DashboardFocusItem(
                    knowledge_point_id=item.knowledge_point_id,
                    knowledge_point_name=item.knowledge_point_name,
                    frequency=item.question_count,
                    paper_coverage=item.paper_count,
                    hot_score=item.hot_score,
                )
                for item in focus_points
            ],
            pending_reviews=sum(1 for item in review_tasks if item.status != "completed"),
            latest_report_name=reports[0].report_name if reports else None,
        )

    def list_frequencies(self) -> list[FrequencyResponse]:
        questions = {question.id: question for question in self.repository.list_questions()}
        knowledge_points = {point.id: point for point in self.repository.list_knowledge_points()}
        link_groups: dict[int, set[int]] = defaultdict(set)
        counts: Counter[int] = Counter()
        for link in self.repository.list_question_knowledge_links():
            counts[link.knowledge_point_id] += 1
            question = questions.get(link.question_id)
            if question is not None:
                link_groups[link.knowledge_point_id].add(question.paper_id)

        rows: list[FrequencyResponse] = []
        for kp_id, question_count in counts.most_common():
            point = knowledge_points.get(kp_id)
            if point is None:
                continue
            paper_count = len(link_groups[kp_id])
            hot_score = round(question_count * 0.65 + paper_count * 0.35, 2)
            rows.append(
                FrequencyResponse(
                    knowledge_point_id=kp_id,
                    knowledge_point_name=point.name,
                    question_count=question_count,
                    paper_count=paper_count,
                    hot_score=hot_score,
                )
            )
        return rows

    def list_trends(self) -> list[TrendResponse]:
        papers = {paper.id: paper for paper in self.repository.list_papers()}
        by_year: Counter[int] = Counter()
        for question in self.repository.list_questions():
            paper = papers.get(question.paper_id)
            year = paper.exam_year if paper and paper.exam_year is not None else 0
            by_year[year] += 1
        rows = []
        for year, count in sorted(by_year.items()):
            rows.append(TrendResponse(label=f"{year} 年", year=year or None, question_count=count))
        return rows

    def get_knowledge_analysis(
        self,
        *,
        subject_id: int | None = None,
        year_from: int | None = None,
        year_to: int | None = None,
        question_type: str | None = None,
        paper_type: str | None = None,
        region: str | None = None,
    ) -> KnowledgeAnalysisResponse:
        papers = self.repository.list_papers()
        questions = self.repository.list_questions()
        knowledge_points = self.repository.list_knowledge_points()
        links = self.repository.list_question_knowledge_links()
        chapters = self.repository.list_chapters()
        categories = self.repository.list_categories()

        papers_by_id = {paper.id: paper for paper in papers}
        points_by_id = {point.id: point for point in knowledge_points}
        chapters_by_id = {chapter.id: chapter for chapter in chapters}
        category_by_id = {category.id: category for category in categories}
        subject_points = [point for point in knowledge_points if subject_id is None or point.subject_id == subject_id]
        approved_links = [link for link in links if link.review_status != "rejected"]
        links_by_question: dict[int, list[QuestionKnowledgeLink]] = defaultdict(list)
        for link in approved_links:
            point = points_by_id.get(link.knowledge_point_id)
            if point is None:
                continue
            if subject_id is not None and point.subject_id != subject_id:
                continue
            links_by_question[link.question_id].append(link)

        filtered_questions: list[ExamQuestion] = []
        for question in questions:
            if subject_id is not None and question.subject_id != subject_id:
                continue
            paper = papers_by_id.get(question.paper_id)
            if paper is None:
                continue
            if year_from is not None and (paper.exam_year or 0) < year_from:
                continue
            if year_to is not None and (paper.exam_year or 0) > year_to:
                continue
            if question_type and question.question_type != question_type:
                continue
            if paper_type and (paper.paper_type or "") != paper_type:
                continue
            if region and (paper.exam_region or "") != region:
                continue
            filtered_questions.append(question)

        available_years = sorted({paper.exam_year for paper in papers if paper.exam_year is not None and (subject_id is None or paper.subject_id == subject_id)})
        available_question_types = sorted({question.question_type for question in questions if subject_id is None or question.subject_id == subject_id})
        available_paper_types = sorted({paper.paper_type for paper in papers if paper.paper_type and (subject_id is None or paper.subject_id == subject_id)})
        available_regions = sorted({paper.exam_region for paper in papers if paper.exam_region and (subject_id is None or paper.subject_id == subject_id)})

        question_ids = {question.id for question in filtered_questions}
        selected_papers = {question.paper_id for question in filtered_questions}
        total_score = sum(float(question.score or 0) for question in filtered_questions)
        mapped_question_count = sum(1 for question in filtered_questions if links_by_question.get(question.id))
        coverage_rate = round(mapped_question_count / len(filtered_questions), 4) if filtered_questions else 0.0

        year_question_groups: dict[int | None, list[ExamQuestion]] = defaultdict(list)
        for question in filtered_questions:
            paper = papers_by_id.get(question.paper_id)
            year_question_groups[paper.exam_year if paper else None].append(question)

        year_rows: list[AnalysisYearSummary] = []
        for year in sorted(year_question_groups, key=lambda item: item or 0):
            year_questions = year_question_groups[year]
            year_papers = {question.paper_id for question in year_questions}
            year_rows.append(
                AnalysisYearSummary(
                    year=year,
                    label=f"{year} 年" if year else "未标注年份",
                    paper_count=len(year_papers),
                    question_count=len(year_questions),
                    mapped_question_count=sum(1 for question in year_questions if links_by_question.get(question.id)),
                    total_score=round(sum(float(question.score or 0) for question in year_questions), 2),
                )
            )

        point_stats: dict[int, dict[str, object]] = {}
        chapter_stats: dict[int, dict[str, object]] = {}
        year_total_score_map: dict[int | None, float] = {
            year: sum(float(question.score or 0) for question in year_questions)
            for year, year_questions in year_question_groups.items()
        }

        for question in filtered_questions:
            paper = papers_by_id.get(question.paper_id)
            year = paper.exam_year if paper else None
            score = float(question.score or 0)
            question_links = links_by_question.get(question.id, [])
            if not question_links:
                continue
            weight = 1 / len(question_links)
            for link in question_links:
                point = points_by_id.get(link.knowledge_point_id)
                if point is None:
                    continue
                chapter = chapters_by_id.get(point.chapter_id) if point.chapter_id else None
                category_name = category_by_id.get(point.category_id).name if point.category_id in category_by_id else None
                point_bucket = point_stats.setdefault(
                    point.id,
                    {
                        "point": point,
                        "chapter": chapter,
                        "category_name": category_name,
                        "frequency": 0,
                        "paper_ids": set(),
                        "score": 0.0,
                        "scores": [],
                        "question_type_counter": Counter(),
                        "year_counter": Counter(),
                        "year_papers": defaultdict(set),
                        "year_scores": defaultdict(float),
                        "years_seen": set(),
                    },
                )
                point_bucket["frequency"] += 1
                point_bucket["paper_ids"].add(question.paper_id)
                point_bucket["score"] += score * weight
                point_bucket["scores"].append(score * weight)
                point_bucket["question_type_counter"][question.question_type] += 1
                point_bucket["year_counter"][year] += 1
                point_bucket["year_papers"][year].add(question.paper_id)
                point_bucket["year_scores"][year] += score * weight
                if year is not None:
                    point_bucket["years_seen"].add(year)

                if chapter is None:
                    continue
                chapter_bucket = chapter_stats.setdefault(
                    chapter.id,
                    {
                        "chapter": chapter,
                        "point_ids": set(),
                        "frequency": 0,
                        "paper_ids": set(),
                        "score": 0.0,
                        "year_counter": Counter(),
                        "year_scores": defaultdict(float),
                    },
                )
                chapter_bucket["point_ids"].add(point.id)
                chapter_bucket["frequency"] += 1
                chapter_bucket["paper_ids"].add(question.paper_id)
                chapter_bucket["score"] += score * weight
                chapter_bucket["year_counter"][year] += 1
                chapter_bucket["year_scores"][year] += score * weight

        point_rows: list[AnalysisPointRow] = []
        for point_id, bucket in sorted(point_stats.items(), key=lambda item: (-float(item[1]["score"]), -int(item[1]["frequency"]), item[0])):
            point = bucket["point"]
            chapter = bucket["chapter"]
            frequency = int(bucket["frequency"])
            point_score = round(float(bucket["score"]), 2)
            years_seen = sorted(bucket["years_seen"])
            continuous_years = _continuous_year_span(years_seen)
            type_counter: Counter[str] = bucket["question_type_counter"]
            total_type_count = sum(type_counter.values()) or 1
            dominant_question_type, dominant_question_count = type_counter.most_common(1)[0] if type_counter else (None, 0)
            type_breakdown = [
                AnalysisTypeBreakdown(
                    question_type=type_name,
                    question_type_label=_question_type_label(type_name),
                    count=count,
                    score=round(
                        sum(
                            float(question.score or 0) / max(1, len(links_by_question.get(question.id, [])))
                            for question in filtered_questions
                            if question.question_type == type_name and any(link.knowledge_point_id == point_id for link in links_by_question.get(question.id, []))
                        ),
                        2,
                    ),
                    count_share=round(count / total_type_count, 4),
                    score_share=round(
                        (
                            sum(
                                float(question.score or 0) / max(1, len(links_by_question.get(question.id, [])))
                                for question in filtered_questions
                                if question.question_type == type_name and any(link.knowledge_point_id == point_id for link in links_by_question.get(question.id, []))
                            )
                            / point_score
                        ),
                        4,
                    )
                    if point_score
                    else 0.0,
                )
                for type_name, count in type_counter.most_common()
            ]
            yearly_stats = [
                AnalysisPointYearStat(
                    year=year,
                    label=f"{year} 年" if year else "未标注年份",
                    frequency=count,
                    paper_count=len(bucket["year_papers"][year]),
                    score=round(float(bucket["year_scores"][year]), 2),
                    score_share=round(float(bucket["year_scores"][year]) / year_total_score_map.get(year, 0), 4)
                    if year_total_score_map.get(year, 0)
                    else 0.0,
                )
                for year, count in sorted(bucket["year_counter"].items(), key=lambda item: item[0] or 0)
            ]
            hot_score = round(point_score * 0.4 + frequency * 0.3 + len(bucket["paper_ids"]) * 0.2 + continuous_years * 0.1, 2)
            point_rows.append(
                AnalysisPointRow(
                    knowledge_point_id=point.id,
                    knowledge_point_name=point.name,
                    chapter_id=chapter.id if chapter else None,
                    chapter_name=chapter.name if chapter else None,
                    chapter_path=chapter.path if chapter else None,
                    category_name=bucket["category_name"],
                    frequency=frequency,
                    paper_coverage=len(bucket["paper_ids"]),
                    total_score=point_score,
                    score_share=round(point_score / total_score, 4) if total_score else 0.0,
                    avg_score=round(mean(bucket["scores"]), 2) if bucket["scores"] else 0.0,
                    continuous_years=continuous_years,
                    last_seen_year=max(years_seen) if years_seen else None,
                    dominant_question_type=dominant_question_type,
                    dominant_question_type_label=_question_type_label(dominant_question_type) if dominant_question_type else None,
                    dominant_question_type_share=round(dominant_question_count / total_type_count, 4) if total_type_count else 0.0,
                    hot_score=hot_score,
                    importance_level=_importance_level(hot_score),
                    type_breakdown=type_breakdown,
                    yearly_stats=yearly_stats,
                )
            )

        chapter_rows: list[AnalysisChapterRow] = []
        for chapter_id, bucket in sorted(chapter_stats.items(), key=lambda item: (-float(item[1]["score"]), -int(item[1]["frequency"]), item[0])):
            chapter: Chapter = bucket["chapter"]
            chapter_score = round(float(bucket["score"]), 2)
            yearly_stats = [
                AnalysisChapterYearStat(
                    year=year,
                    label=f"{year} 年" if year else "未标注年份",
                    frequency=count,
                    score=round(float(bucket["year_scores"][year]), 2),
                    score_share=round(float(bucket["year_scores"][year]) / year_total_score_map.get(year, 0), 4)
                    if year_total_score_map.get(year, 0)
                    else 0.0,
                )
                for year, count in sorted(bucket["year_counter"].items(), key=lambda item: item[0] or 0)
            ]
            chapter_rows.append(
                AnalysisChapterRow(
                    chapter_id=chapter.id,
                    chapter_name=chapter.name,
                    chapter_path=chapter.path,
                    point_count=len(bucket["point_ids"]),
                    frequency=int(bucket["frequency"]),
                    paper_coverage=len(bucket["paper_ids"]),
                    total_score=chapter_score,
                    score_share=round(chapter_score / total_score, 4) if total_score else 0.0,
                    yearly_stats=yearly_stats,
                )
            )

        summary_metrics = [
            AnalysisMetric(key="papers", label="试卷数", value=str(len(selected_papers)), helper="当前筛选范围内"),
            AnalysisMetric(key="questions", label="原始题数", value=str(len(filtered_questions)), helper="按小题统计"),
            AnalysisMetric(key="coverage", label="考点覆盖率", value=f"{coverage_rate * 100:.1f}%", helper="已映射原始题占比"),
            AnalysisMetric(key="total_score", label="总分值", value=f"{total_score:.1f}", helper="当前筛选范围累计"),
            AnalysisMetric(key="points", label="覆盖考点", value=str(len(point_rows)), helper="当前筛选范围命中的考点"),
            AnalysisMetric(key="chapters", label="覆盖章节", value=str(len(chapter_rows)), helper="当前筛选范围命中的章节"),
        ]

        top_points = point_rows[:3]
        insights = _build_insights(point_rows, chapter_rows, top_points, filtered_questions, coverage_rate)
        return KnowledgeAnalysisResponse(
            data_as_of=date.today(),
            coverage_rate=coverage_rate,
            summary_metrics=summary_metrics,
            available_years=available_years,
            available_question_types=[
                AnalysisFilterOption(value=item, label=_question_type_label(item)) for item in available_question_types
            ],
            available_paper_types=available_paper_types,
            available_regions=available_regions,
            years=year_rows,
            points=point_rows,
            chapters=chapter_rows,
            insights=insights,
        )

    def list_reports(self) -> list[ReportResponse]:
        return [ReportResponse.model_validate(item) for item in self.repository.list_reports()]

    def get_job(self, job_id: int) -> AnalysisJobResponse:
        job = self.repository.get_job(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="任务不存在")
        return AnalysisJobResponse.model_validate(job)

    def generate_report(self, payload: GenerateReportRequest) -> ReportResponse:
        frequencies = self.list_frequencies()
        trends = self.list_trends()
        papers = self.repository.list_papers()
        target_papers = [paper for paper in papers if payload.subject_id is None or paper.subject_id == payload.subject_id]
        report = self.repository.create_report(
            AnalysisReport(
                tenant_id=target_papers[0].tenant_id if target_papers else 1,
                subject_id=payload.subject_id,
                report_type=payload.report_type,
                report_name=payload.report_name or f"{date.today().isoformat()} 高频考点报告",
                scope_config_json={"subject_id": payload.subject_id, "paper_count": len(target_papers)},
                filters_json={"source": "current_questions"},
                snapshot_date=date.today(),
                version_no=1,
                status="ready",
                report_json={
                    "summary": _build_report_summary(frequencies, trends),
                    "top_points": [item.model_dump() for item in frequencies[:10]],
                    "trends": [item.model_dump() for item in trends],
                },
                created_by=None,
                updated_by=None,
            )
        )
        self.repository.session.commit()
        return ReportResponse.model_validate(report)

    def export_report_markdown(self, report_id: int) -> str:
        report = self.repository.get_report(report_id)
        if report is None:
            raise HTTPException(status_code=404, detail="报告不存在")
        data = report.report_json or {}
        lines = [
            f"# {report.report_name}",
            "",
            f"- 类型：{report.report_type}",
            f"- 日期：{report.snapshot_date or '-'}",
            f"- 版本：v{report.version_no}",
            "",
            "## 摘要",
            "",
            str(data.get("summary") or "暂无摘要"),
            "",
            "## 高频考点",
            "",
        ]
        for item in data.get("top_points", []) or []:
            lines.append(
                f"- {item.get('knowledge_point_name', '未知考点')}：{item.get('question_count', 0)} 题，覆盖 {item.get('paper_count', 0)} 份试卷"
            )
        lines.extend(["", "## 年度趋势", ""])
        for item in data.get("trends", []) or []:
            lines.append(f"- {item.get('label', '-')}: {item.get('question_count', 0)} 题")
        return "\n".join(lines).strip() + "\n"


def _build_report_summary(frequencies: list[FrequencyResponse], trends: list[TrendResponse]) -> str:
    if not frequencies:
        return "当前还没有足够的考点映射数据，建议先完成题目解析和考点标注。"
    top = "、".join(item.knowledge_point_name for item in frequencies[:3])
    total_questions = sum(item.question_count for item in trends)
    return f"当前已统计 {total_questions} 道原始题，高频考点集中在：{top}。"


def _question_type_label(question_type: str | None) -> str:
    mapping = {
        "single_choice": "单选题",
        "multiple_choice": "多选题",
        "judge": "判断题",
        "fill_blank": "填空题",
        "short_answer": "简答题",
        "calculation": "计算题",
        "case_analysis": "案例分析题",
        "material_analysis": "材料分析题",
        "composite": "综合题",
    }
    if not question_type:
        return "-"
    return mapping.get(question_type, question_type)


def _continuous_year_span(years: list[int]) -> int:
    if not years:
        return 0
    longest = 1
    current = 1
    for previous, current_year in zip(years, years[1:], strict=False):
        if current_year == previous + 1:
            current += 1
        else:
            current = 1
        longest = max(longest, current)
    return longest


def _importance_level(hot_score: float) -> str:
    if hot_score >= 8:
        return "S"
    if hot_score >= 5.5:
        return "A"
    if hot_score >= 3.5:
        return "B"
    if hot_score >= 2:
        return "C"
    return "D"


def _build_insights(
    point_rows: list[AnalysisPointRow],
    chapter_rows: list[AnalysisChapterRow],
    top_points: list[AnalysisPointRow],
    filtered_questions: list[ExamQuestion],
    coverage_rate: float,
) -> list[AnalysisInsight]:
    insights: list[AnalysisInsight] = []
    if top_points:
        point_names = "、".join(point.knowledge_point_name for point in top_points)
        insights.append(
            AnalysisInsight(
                title="高频核心考点",
                description=f"当前范围内最值得优先关注的考点集中在 {point_names}，兼具频次和分值优势。",
            )
        )
    if chapter_rows:
        top_chapter = chapter_rows[0]
        insights.append(
            AnalysisInsight(
                title="章节重心",
                description=f"{top_chapter.chapter_name} 章节当前贡献 {top_chapter.score_share * 100:.1f}% 分值，占比最高。",
            )
        )
    if filtered_questions:
        insights.append(
            AnalysisInsight(
                title="映射覆盖情况",
                description=f"当前筛选范围共 {len(filtered_questions)} 道题，考点映射覆盖率 {coverage_rate * 100:.1f}%。",
            )
        )
    if point_rows:
        stable_points = [point.knowledge_point_name for point in point_rows if point.continuous_years >= 2][:3]
        if stable_points:
            insights.append(
                AnalysisInsight(
                    title="连续出现考点",
                    description=f"连续年份保持出现的考点包括 { '、'.join(stable_points) }，适合作为重点复习主线。",
                )
            )
    return insights[:4]
