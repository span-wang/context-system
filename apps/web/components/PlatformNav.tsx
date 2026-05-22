"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const links = [
  { href: "/analysis/papers", label: "试卷中心" },
  { href: "/question-bank", label: "正式题库" },
  { href: "/question-bank/analysis", label: "考点分析" },
  { href: "/practice", label: "刷题练习" },
  { href: "/knowledge", label: "学科中心" },
  { href: "/training", label: "模型训练" },
  { href: "/settings", label: "模型配置" },
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
