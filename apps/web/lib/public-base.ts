const LOCAL_HOSTNAMES = new Set(["localhost", "127.0.0.1", "::1"]);

function isPrivateIpv4(hostname: string): boolean {
  if (!/^\d{1,3}(\.\d{1,3}){3}$/.test(hostname)) return false;
  const parts = hostname.split(".").map((part) => Number(part));
  if (parts.some((part) => Number.isNaN(part) || part < 0 || part > 255)) return false;
  return (
    parts[0] === 10 ||
    parts[0] === 127 ||
    (parts[0] === 169 && parts[1] === 254) ||
    (parts[0] === 172 && parts[1] >= 16 && parts[1] <= 31) ||
    (parts[0] === 192 && parts[1] === 168)
  );
}

function isUnsafeBrowserBase(hostname: string): boolean {
  const normalized = hostname.trim().toLowerCase();
  return LOCAL_HOSTNAMES.has(normalized) || isPrivateIpv4(normalized);
}

export function resolvePublicBase(rawBase: string | undefined, fallback: string): string {
  const trimmed = rawBase?.trim() || "";
  if (!trimmed) return fallback;

  if (typeof window === "undefined") return trimmed;
  if (!window.location.hostname || isUnsafeBrowserBase(window.location.hostname)) return trimmed;

  try {
    const resolved = new URL(trimmed, window.location.origin);
    if (isUnsafeBrowserBase(resolved.hostname)) {
      return fallback;
    }
  } catch {
    return fallback;
  }

  return trimmed;
}
