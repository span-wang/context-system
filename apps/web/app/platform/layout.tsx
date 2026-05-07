import { PlatformNav } from "../../components/PlatformNav";

export default function PlatformLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="platformShell">
      <PlatformNav />
      {children}
    </div>
  );
}
