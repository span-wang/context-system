"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { BookOpen, CalendarDays, ClipboardList, FileText, History, Library, Settings, Wand2 } from "lucide-react";

const links = [
  { href: "/workflow", label: "工作流", icon: CalendarDays },
  { href: "/library", label: "素材库", icon: Library },
  { href: "/generate", label: "生成中心", icon: Wand2 },
  { href: "/analysis/papers", label: "试卷中心", icon: FileText },
  { href: "/analysis/questions", label: "题目解析", icon: ClipboardList },
  { href: "/knowledge", label: "学科中心", icon: BookOpen },
  { href: "/training", label: "模型训练", icon: ClipboardList },
  { href: "/history", label: "历史审查", icon: History },
  { href: "/settings", label: "模型配置", icon: Settings },
];

export function Nav() {
  const pathname = usePathname();
  return (
    <nav className="nav">
      <div className="brand">
        <span className="brandMark">X</span>
        <div>
          <strong>Exam Kit</strong>
          <span>小红书备考资料生产工具</span>
        </div>
      </div>
      <div className="navLinks">
        {links.map((link) => {
          const Icon = link.icon;
          const active = pathname.startsWith(link.href);
          return (
            <Link key={link.href} className={active ? "navLink active" : "navLink"} href={link.href}>
              <Icon size={17} />
              {link.label}
            </Link>
          );
        })}
      </div>
    </nav>
  );
}
