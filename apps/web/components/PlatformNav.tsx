"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const links = [
  { href: "/platform/analysis/dashboard", label: "分析看板" },
  { href: "/platform/analysis/knowledge", label: "考点分析" },
  { href: "/platform/analysis/papers", label: "试卷中心" },
  { href: "/platform/analysis/questions", label: "原始题" },
  { href: "/platform/analysis/reports", label: "分析报告" },
  { href: "/platform/subject-center", label: "学科中心" },
  { href: "/platform/question-bank", label: "题库中心" },
  { href: "/platform/question-bank/practice-sets", label: "练习题包" },
  { href: "/platform/question-bank/mock-exams", label: "模考试卷" },
  { href: "/platform/learners", label: "学员学习" },
  { href: "/platform/training", label: "模型训练" },
  { href: "/platform/workflow", label: "工作流" },
  { href: "/platform/settings", label: "平台设置" },
];

export function PlatformNav() {
  const pathname = usePathname();

  return (
    <div className="platformNav" aria-label="平台导航">
      {links.map((link) => {
        const active = pathname === link.href || pathname.startsWith(`${link.href}/`);
        return (
          <Link key={link.href} className={active ? "platformNavLink active" : "platformNavLink"} href={link.href}>
            {link.label}
          </Link>
        );
      })}
    </div>
  );
}
