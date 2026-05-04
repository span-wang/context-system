"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { History, Library, Settings, Wand2 } from "lucide-react";

const links = [
  { href: "/library", label: "素材库", icon: Library },
  { href: "/generate", label: "生成中心", icon: Wand2 },
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
