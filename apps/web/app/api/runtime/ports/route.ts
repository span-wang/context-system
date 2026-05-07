import { promises as fs } from "fs";
import path from "path";

import { NextResponse } from "next/server";

type RawPortsPayload = {
  api_base?: unknown;
  api_port?: unknown;
  web_url?: unknown;
  web_port?: unknown;
  use_local_mysql?: unknown;
  mysql_port?: unknown;
  mysql_db_url?: unknown;
  started_at?: unknown;
};

function asNullableString(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value : null;
}

function asNullableNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function asNullableBoolean(value: unknown): boolean | null {
  if (typeof value === "boolean") {
    return value;
  }
  if (value && typeof value === "object" && "IsPresent" in value) {
    const present = (value as { IsPresent?: unknown }).IsPresent;
    return typeof present === "boolean" ? present : null;
  }
  return null;
}

async function probeHttp(url: string | null): Promise<{ online: boolean; status_code: number | null }> {
  if (!url) {
    return { online: false, status_code: null };
  }

  try {
    const response = await fetch(url, {
      method: "GET",
      cache: "no-store",
    });
    return {
      online: response.ok,
      status_code: response.status,
    };
  } catch {
    return { online: false, status_code: null };
  }
}

type PortProbeResult = {
  port: number | null;
  configured: boolean;
  online: boolean;
};

async function probeTcpPort(port: number | null): Promise<PortProbeResult> {
  if (!port) {
    return {
      port,
      configured: false,
      online: false,
    };
  }

  try {
    const net = await import("net");
    const online = await new Promise<boolean>((resolve) => {
      const socket = new net.Socket();
      let settled = false;

      const finish = (value: boolean) => {
        if (settled) {
          return;
        }
        settled = true;
        socket.destroy();
        resolve(value);
      };

      socket.setTimeout(1200);
      socket.once("connect", () => finish(true));
      socket.once("timeout", () => finish(false));
      socket.once("error", () => finish(false));
      socket.connect(port, "127.0.0.1");
    });

    return {
      port,
      configured: true,
      online,
    };
  } catch {
    return {
      port,
      configured: true,
      online: false,
    };
  }
}

export async function GET() {
  const portsPath = path.resolve(process.cwd(), "..", "..", "data", "run", "ports.json");

  try {
    const raw = await fs.readFile(portsPath, "utf8");
    const normalized = raw.replace(/^\uFEFF/, "");
    const payload = JSON.parse(normalized) as RawPortsPayload;
    const apiBase = asNullableString(payload.api_base);
    const webUrl = asNullableString(payload.web_url);
    const apiPort = asNullableNumber(payload.api_port);
    const webPort = asNullableNumber(payload.web_port);
    const mysqlPort = asNullableNumber(payload.mysql_port);
    const [apiProbe, webProbe, mysqlProbe] = await Promise.all([
      probeHttp(apiBase ? `${apiBase}/api/system/healthz` : null),
      probeHttp(webUrl ? `${webUrl}/generate` : null),
      probeTcpPort(mysqlPort),
    ]);

    return NextResponse.json({
      found: true,
      source_path: portsPath,
      api_base: apiBase,
      api_port: apiPort,
      web_url: webUrl,
      web_port: webPort,
      use_local_mysql: asNullableBoolean(payload.use_local_mysql),
      mysql_port: mysqlPort,
      mysql_db_url: asNullableString(payload.mysql_db_url),
      started_at: asNullableString(payload.started_at),
      probes: {
        api: {
          configured: Boolean(apiBase || apiPort),
          online: apiProbe.online,
          status_code: apiProbe.status_code,
        },
        web: {
          configured: Boolean(webUrl || webPort),
          online: webProbe.online,
          status_code: webProbe.status_code,
        },
        mysql: mysqlProbe,
      },
    });
  } catch {
    return NextResponse.json({
      found: false,
      source_path: portsPath,
      api_base: null,
      api_port: null,
      web_url: null,
      web_port: null,
      use_local_mysql: null,
      mysql_port: null,
      mysql_db_url: null,
      started_at: null,
      probes: {
        api: {
          configured: false,
          online: false,
          status_code: null,
        },
        web: {
          configured: false,
          online: false,
          status_code: null,
        },
        mysql: {
          port: null,
          configured: false,
          online: false,
        },
      },
    });
  }
}
