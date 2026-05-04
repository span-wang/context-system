import type { Metadata } from "next";
import { Nav } from "../components/Nav";
import "./globals.css";

export const metadata: Metadata = {
  title: "Exam Kit",
  description: "小红书备考资料生产工具",
  icons: {
    icon: "/icon.svg",
  },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN">
      <body>
        <Nav />
        <main className="pageShell">{children}</main>
      </body>
    </html>
  );
}
