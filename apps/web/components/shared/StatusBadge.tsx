type StatusBadgeProps = {
  value: string | number | boolean | null | undefined;
  tone?: "default" | "good" | "warn" | "danger" | "info";
};

export function StatusBadge({ value, tone = "default" }: StatusBadgeProps) {
  const className =
    tone === "good"
      ? "badge done"
      : tone === "warn"
        ? "badge reviewing"
        : tone === "danger"
          ? "badge failed"
          : tone === "info"
            ? "badge medium"
            : "badge";

  return <span className={className}>{String(value ?? "-")}</span>;
}
