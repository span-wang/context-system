"use client";

import { useEffect, useState } from "react";
import {
  apiFetch,
  AuditLogResponse,
  clearPlatformTokens,
  CurrentUserResponse,
  getPlatformRefreshToken,
  getPlatformToken,
  LoginResponse,
  moduleLabelMap,
  RuntimePortsResponse,
  setPlatformTokens,
  SystemStatusResponse,
} from "../../../lib/pro-api";
import { LoadState } from "../../../components/shared/LoadState";
import { StatusBadge } from "../../../components/shared/StatusBadge";
import {
  allRejected,
  firstRejectedReason,
  summarizeRejectedRequests,
  toErrorMessage,
  useLatestRequestGate,
} from "../../../lib/request-guard";

export default function SettingsPage() {
  const [status, setStatus] = useState<SystemStatusResponse | null>(null);
  const [runtimePorts, setRuntimePorts] = useState<RuntimePortsResponse | null>(null);
  const [user, setUser] = useState<CurrentUserResponse | null>(null);
  const [auditLogs, setAuditLogs] = useState<AuditLogResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [loginLoading, setLoginLoading] = useState(false);
  const [loginMessage, setLoginMessage] = useState("");
  const [error, setError] = useState("");
  const [loadWarning, setLoadWarning] = useState("");
  const [auditLogsSkipped, setAuditLogsSkipped] = useState(false);
  const requestGate = useLatestRequestGate();

  async function loadData() {
    const requestId = requestGate.begin();
    const shouldLoadAuditLogs = Boolean(getPlatformToken());
    setLoading(true);
    setError("");
    setLoadWarning("");
    try {
      const nextRuntimePorts = await fetch("/api/runtime/ports", { cache: "no-store" }).then((response) => {
        if (!response.ok) {
          throw new Error("读取运行时端口信息失败");
        }
        return response.json() as Promise<RuntimePortsResponse>;
      });

      if (!requestGate.isCurrent(requestId)) return;
      setRuntimePorts(nextRuntimePorts);

      if (nextRuntimePorts.probes?.api.configured && !nextRuntimePorts.probes.api.online) {
        setStatus(null);
        setUser(null);
        setAuditLogs([]);
        setAuditLogsSkipped(true);
        setLoadWarning("平台 API 当前不在线，已跳过平台状态、当前用户和审计日志请求。");
        return;
      }

      const [nextStatus, nextUser, nextAuditLogs] = await Promise.allSettled([
        apiFetch<SystemStatusResponse>("/api/system/status"),
        apiFetch<CurrentUserResponse>("/api/auth/me"),
        shouldLoadAuditLogs
          ? apiFetch<AuditLogResponse[]>("/api/system/audit-logs?limit=20")
          : Promise.resolve<AuditLogResponse[]>([]),
      ]);

      if (!requestGate.isCurrent(requestId)) return;
      const results = [nextStatus, nextUser, nextAuditLogs];
      if (allRejected(results)) {
        throw firstRejectedReason(results) || new Error("No settings requests succeeded.");
      }

      setStatus(nextStatus.status === "fulfilled" ? nextStatus.value : null);
      setUser(nextUser.status === "fulfilled" ? nextUser.value : null);
      setAuditLogs(nextAuditLogs.status === "fulfilled" ? nextAuditLogs.value : []);
      setAuditLogsSkipped(!shouldLoadAuditLogs);
      setLoadWarning(
        summarizeRejectedRequests([
          { label: "平台状态", result: nextStatus },
          { label: "当前用户", result: nextUser },
          ...(shouldLoadAuditLogs ? [{ label: "审计日志", result: nextAuditLogs }] : []),
        ]),
      );
    } catch (err) {
      if (!requestGate.isCurrent(requestId)) return;
      setError(toErrorMessage(err, "加载系统状态失败"));
    } finally {
      if (requestGate.isCurrent(requestId)) setLoading(false);
    }
  }

  useEffect(() => {
    loadData();
  }, []);

  async function login(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const formData = new FormData(form);
    const username = String(formData.get("username") || "").trim();
    const password = String(formData.get("password") || "");
    setLoginLoading(true);
    setLoginMessage("");
    setError("");
    try {
      const result = await apiFetch<LoginResponse>("/api/auth/login", {
        method: "POST",
        body: JSON.stringify({ username, password }),
      });
      setPlatformTokens(result.access_token, result.refresh_token);
      setUser(result.user);
      setLoginMessage(`已登录：${result.user.display_name}`);
      await loadData();
    } catch (err) {
      setError(toErrorMessage(err, "登录失败"));
    } finally {
      setLoginLoading(false);
    }
  }

  async function logout() {
    const refreshToken = getPlatformRefreshToken();
    try {
      await apiFetch("/api/auth/logout", {
        method: "POST",
        body: JSON.stringify({ refresh_token: refreshToken || null }),
      });
    } catch {
      // Local token cleanup still matters if the server-side session is already gone.
    }
    clearPlatformTokens();
    setLoginMessage("已清除本地登录令牌");
    await loadData();
  }

  const databaseType = status ? getDatabaseType(status.summary.database_url) : "-";
  const runtimeSource = getRuntimeSource(databaseType, runtimePorts);
  const runtimeMatch = getRuntimeMatch(status, runtimePorts);
  const runtimeAvailability = getRuntimeAvailability(runtimePorts);

  return (
    <>
      <header className="pageHeader">
        <div>
          <h1>系统设置</h1>
          <p>这里展示当前系统状态、账号信息、运行端口和最近审计日志。</p>
        </div>
      </header>

      {loadWarning && <div className="calloutBox">{loadWarning}</div>}

      <LoadState
        loading={loading}
        error={error}
        empty={!status && !user && !runtimePorts && !auditLogs.length}
        emptyLabel="系统状态暂不可用"
      />

      {!loading && !error && (status || user || runtimePorts || auditLogs.length) && (
        <section className="dashboardGrid twoCol">
          {(status || runtimePorts) && (
            <div className="panel">
              <div className="panelHeader">
                <h2>平台状态</h2>
                <p>{status?.summary.current_phase || "平台状态接口暂不可用"}</p>
              </div>
              <div className="panelBody stackList">
                <div className="detailRow">
                  <span>服务名</span>
                  <strong>{status?.health.name || "-"}</strong>
                </div>
                <div className="detailRow">
                  <span>版本</span>
                  <strong>{status?.health.version || "-"}</strong>
                </div>
                <div className="detailRow">
                  <span>环境</span>
                  <strong>{status?.health.environment || "-"}</strong>
                </div>
                <div className="detailRow">
                  <span>数据库类型</span>
                  <strong>{databaseType}</strong>
                </div>
                <div className="detailRow">
                  <span>数据库来源</span>
                  <strong>{runtimeSource}</strong>
                </div>
                <div className="detailRow">
                  <span>API 当前配置</span>
                  <strong>{status?.summary.database_url || "-"}</strong>
                </div>
                <div className="detailRow">
                  <span>ports.json 记录</span>
                  <strong>{runtimePorts?.mysql_db_url || "-"}</strong>
                </div>
                <div className="detailRow">
                  <span>MySQL 端口</span>
                  <strong>{runtimePorts?.mysql_port || "-"}</strong>
                </div>
                <div className="detailRow">
                  <span>API 地址</span>
                  <strong>{runtimePorts?.api_base || "/platform/api -> rewrite"}</strong>
                </div>
                <div className="detailRow">
                  <span>Web 地址</span>
                  <strong>{runtimePorts?.web_url || "-"}</strong>
                </div>
                <div className="detailRow">
                  <span>端口状态文件</span>
                  <StatusBadge value={runtimePorts?.found ? "found" : "missing"} tone={runtimePorts?.found ? "good" : "warn"} />
                </div>
                <div className="detailRow">
                  <span>API 在线探测</span>
                  <StatusBadge value={runtimeAvailability.api.label} tone={runtimeAvailability.api.tone} />
                </div>
                <div className="detailRow">
                  <span>Web 在线探测</span>
                  <StatusBadge value={runtimeAvailability.web.label} tone={runtimeAvailability.web.tone} />
                </div>
                <div className="detailRow">
                  <span>MySQL 在线探测</span>
                  <StatusBadge value={runtimeAvailability.mysql.label} tone={runtimeAvailability.mysql.tone} />
                </div>
                <div className="detailRow">
                  <span>对象存储</span>
                  <strong>{status?.summary.storage_type || "-"}</strong>
                </div>
                <div className="detailRow">
                  <span>MySQL 预留</span>
                  <StatusBadge
                    value={status ? (status.summary.mysql_ready ? "ready" : "pending") : "-"}
                    tone={status?.summary.mysql_ready ? "good" : "warn"}
                  />
                </div>
                <div className="detailRow">
                  <span>状态对齐</span>
                  <StatusBadge value={runtimeMatch.label} tone={runtimeMatch.tone} />
                </div>
                <div className="calloutBox">{runtimeMatch.message}</div>
                <div className="calloutBox">{runtimeAvailability.message}</div>
              </div>
            </div>
          )}

          <div className="panel">
            <div className="panelHeader">
              <h2>登录与当前用户</h2>
              <p>默认管理员账号为 `admin / admin123456`。</p>
            </div>
            <div className="panelBody stackList">
              <form className="formGrid" onSubmit={login}>
                <div className="row">
                  <label className="field">
                    <span>用户名</span>
                    <input name="username" defaultValue="admin" disabled={loginLoading} />
                  </label>
                  <label className="field">
                    <span>密码</span>
                    <input name="password" type="password" defaultValue="admin123456" disabled={loginLoading} />
                  </label>
                </div>
                <div className="buttonRow">
                  <button className="button primary" type="submit" disabled={loginLoading}>
                    {loginLoading ? "登录中..." : "登录"}
                  </button>
                  <button className="button" type="button" onClick={logout}>
                    退出
                  </button>
                  {loginMessage && <span className="muted">{loginMessage}</span>}
                </div>
              </form>
              <div className="detailRow">
                <span>用户名</span>
                <strong>{user?.username || "-"}</strong>
              </div>
              <div className="detailRow">
                <span>显示名</span>
                <strong>{user?.display_name || "-"}</strong>
              </div>
              <div className="detailRow">
                <span>用户类型</span>
                <strong>{user?.user_type || "-"}</strong>
              </div>
              <div className="detailRow">
                <span>角色</span>
                <strong>{user?.roles.map((role) => role.role_name).join(" / ") || "-"}</strong>
              </div>
            </div>
          </div>

          {status && (
            <div className="panel sectionSpan2">
              <div className="panelHeader">
                <h2>模块成熟度</h2>
                <p>当前各模块的可用程度。</p>
              </div>
              <div className="panelBody">
                <div className="metricTable">
                  {Object.entries(status.summary.module_status).map(([key, value]) => (
                    <div key={key} className="metricRow">
                      <span>{moduleLabelMap[key] || key}</span>
                      <StatusBadge value={value} tone={value.includes("ready") ? "good" : "warn"} />
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}

          <div className="panel sectionSpan2">
            <div className="panelHeader">
              <h2>最近操作日志</h2>
              <p>这里显示关键写操作的最近记录。</p>
            </div>
            <div className="panelBody">
              {auditLogsSkipped ? (
                <div className="calloutBox">登录后可查看最近操作日志。</div>
              ) : !auditLogs.length ? (
                <div className="calloutBox">暂无可查看的操作日志，执行上传、解析、生成报告等写操作后即可看到记录。</div>
              ) : (
                <div className="metricTable">
                  {auditLogs.map((item) => (
                    <div key={item.id} className="metricRow">
                      <div>
                        <strong>
                          {item.module} / {item.action}
                        </strong>
                        <span className="muted">
                          {item.username || `用户 #${item.user_id || "-"}`} / {item.target_type || "-"} #{item.target_id || "-"} /{" "}
                          {new Date(item.created_at).toLocaleString()}
                        </span>
                      </div>
                      <StatusBadge value={`#${item.id}`} tone="info" />
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </section>
      )}
    </>
  );
}

function getDatabaseType(databaseUrl: string): string {
  if (databaseUrl.startsWith("mysql")) {
    return "MySQL";
  }
  if (databaseUrl.startsWith("sqlite")) {
    return "SQLite";
  }
  return "Other";
}

function getRuntimeSource(databaseType: string, runtimePorts: RuntimePortsResponse | null): string {
  if (!runtimePorts?.found) {
    return databaseType === "SQLite" ? "当前仅看到 API 自报状态" : "未读取到 ports.json";
  }
  if (runtimePorts.use_local_mysql) {
    return "项目自管 MySQL";
  }
  if (databaseType === "MySQL") {
    return "外部 MySQL / 环境变量覆盖";
  }
  if (databaseType === "SQLite") {
    return "本地 SQLite";
  }
  return "未识别";
}

function getRuntimeMatch(status: SystemStatusResponse | null, runtimePorts: RuntimePortsResponse | null): {
  label: string;
  tone: "good" | "warn" | "info";
  message: string;
} {
  if (!status) {
    return {
      label: "unknown",
      tone: "info",
      message: "尚未加载到 API 状态。",
    };
  }

  if (!runtimePorts?.found) {
    return {
      label: "ports-missing",
      tone: "warn",
      message: "未找到 data/run/ports.json，当前页面只能显示 API 自报的数据库配置。",
    };
  }

  if (!runtimePorts.mysql_db_url) {
    return {
      label: "ports-partial",
      tone: "warn",
      message: "ports.json 已存在，但没有记录 mysql_db_url；如果当前链路使用 MySQL，请重新检查启动脚本落盘结果。",
    };
  }

  if (runtimePorts.mysql_db_url === status.summary.database_url) {
    return {
      label: "aligned",
      tone: "good",
      message: "ports.json 与 API 当前返回的数据库配置一致，可以视作同一份来源说明。",
    };
  }

  return {
    label: "stale",
    tone: "warn",
    message: "ports.json 与 API 当前返回的数据库配置不一致，通常表示端口信息沿用了旧结果，需要先核对实际 API 和 MySQL 链路。",
  };
}

function getRuntimeAvailability(runtimePorts: RuntimePortsResponse | null): {
  api: { label: string; tone: "good" | "warn" | "info" };
  web: { label: string; tone: "good" | "warn" | "info" };
  mysql: { label: string; tone: "good" | "warn" | "info" };
  message: string;
} {
  if (!runtimePorts?.found || !runtimePorts.probes) {
    return {
      api: { label: "not-probed", tone: "info" },
      web: { label: "not-probed", tone: "info" },
      mysql: { label: "not-probed", tone: "info" },
      message: "当前没有可用的在线探测结果，页面只能依据 ports.json 是否存在来提示链路来源。",
    };
  }

  const api = runtimePorts.probes.api;
  const web = runtimePorts.probes.web;
  const mysql = runtimePorts.probes.mysql;

  const apiLabel = !api.configured ? "not-configured" : api.online ? `online${api.status_code ? `:${api.status_code}` : ""}` : "offline";
  const webLabel = !web.configured ? "not-configured" : web.online ? `online${web.status_code ? `:${web.status_code}` : ""}` : "offline";
  const mysqlLabel = !mysql.configured ? "not-configured" : mysql.online ? `online:${mysql.port ?? "-"}` : `offline:${mysql.port ?? "-"}`;

  const offlineParts: string[] = [];
  if (api.configured && !api.online) offlineParts.push("API 不在线");
  if (web.configured && !web.online) offlineParts.push("Web 不在线");
  if (mysql.configured && !mysql.online) offlineParts.push("MySQL 不在线");

  let message = "ports.json 与在线探测结果需要一起看：前者说明配置来源，后者说明实例是否真的还在运行。";
  if (offlineParts.length) {
    message = `${offlineParts.join("，")}。如果配置仍显示存在，但实例已离线，优先检查 ports.json 是否沿用了旧结果，以及对应进程或端口是否已经退出。`;
  }

  return {
    api: { label: apiLabel, tone: !api.configured ? "info" : api.online ? "good" : "warn" },
    web: { label: webLabel, tone: !web.configured ? "info" : web.online ? "good" : "warn" },
    mysql: { label: mysqlLabel, tone: !mysql.configured ? "info" : mysql.online ? "good" : "warn" },
    message,
  };
}
