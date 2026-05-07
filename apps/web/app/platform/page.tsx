import Link from "next/link";

const cards = [
  {
    href: "/platform/analysis/dashboard",
    title: "分析看板",
    description: "查看学科、试卷、原始题和高频考点的整体情况。",
  },
  {
    href: "/platform/analysis/papers",
    title: "试卷中心",
    description: "上传试卷、执行解析切题，并查看试卷分区和状态。",
  },
  {
    href: "/platform/analysis/questions",
    title: "原始题",
    description: "查看解析出的原始题、答案、解析和考点关联。",
  },
  {
    href: "/platform/analysis/reports",
    title: "分析报告",
    description: "生成考点频次与趋势报告，并导出 Markdown。",
  },
  {
    href: "/platform/subject-center",
    title: "学科中心",
    description: "统一维护学科、类目、教材、章节和知识点，支撑原始题考点映射。",
  },
  {
    href: "/platform/question-bank",
    title: "题库中心",
    description: "把原始题同步成标准题，并生成题包和模考。",
  },
  {
    href: "/platform/learners",
    title: "学员学习",
    description: "查看练习记录、错题本和掌握度快照的演示链路。",
  },
  {
    href: "/platform/workflow",
    title: "工作流",
    description: "把分析结果转成审核任务和内容生产任务。",
  },
  {
    href: "/platform/settings",
    title: "平台设置",
    description: "登录平台账号，查看运行状态、数据库和操作日志。",
  },
];

export default function PlatformHomePage() {
  return (
    <>
      <header className="pageHeader">
        <div>
          <h1>专业题库平台</h1>
          <p>这里是题库、试卷解析、分析报告和学习闭环的统一入口，进入后可以直接点击各个模块，不需要再手动输入地址。</p>
        </div>
      </header>

      <section className="statsGrid">
        <article className="statCard">
          <span>试卷解析</span>
          <strong>已接入</strong>
          <small>支持上传试卷、解析切题和候选考点标注。</small>
        </article>
        <article className="statCard">
          <span>题库标准化</span>
          <strong>已接入</strong>
          <small>支持原始题同步标准题、练习题包和模考生成。</small>
        </article>
        <article className="statCard">
          <span>分析报告</span>
          <strong>已接入</strong>
          <small>支持频次、趋势和 Markdown 导出。</small>
        </article>
        <article className="statCard">
          <span>学习闭环</span>
          <strong>演示版</strong>
          <small>已预留练习、错题本、收藏和掌握度快照。</small>
        </article>
      </section>

      <section className="platformEntryGrid">
        {cards.map((card) => (
          <Link key={card.href} className="platformEntryCard" href={card.href}>
            <strong>{card.title}</strong>
            <p>{card.description}</p>
            <span>进入模块</span>
          </Link>
        ))}
      </section>
    </>
  );
}
