"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import { CheckCircle2, KeyRound, Plus, PlugZap, RefreshCw, Save, Server, SlidersHorizontal, Trash2 } from "lucide-react";
import { apiFetch, LLMEndpointConfig, LLMPresetConfig, SystemConfig } from "../../lib/api";

type ProviderId = LLMEndpointConfig["provider"];
type EndpointTarget = "generator" | "reviewer";

type EditableEndpoint = {
  provider: ProviderId;
  model: string;
  max_tokens: string;
  base_url: string;
  api_key: string;
  clear_api_key: boolean;
  has_api_key: boolean;
};

type EditableConfig = Record<EndpointTarget, EditableEndpoint>;

const providerOptions: Array<{ value: ProviderId; label: string }> = [
  { value: "local_template", label: "本地模板" },
  { value: "local_rules", label: "本地规则" },
  { value: "deepseek", label: "DeepSeek" },
  { value: "openai_compat", label: "OpenAI 兼容" },
  { value: "anthropic", label: "Anthropic" },
];

const targetLabels: Record<EndpointTarget, string> = {
  generator: "生成模型",
  reviewer: "审查模型",
};

const localModelDefaults: Partial<Record<ProviderId, string>> = {
  local_template: "local-template",
  local_rules: "local-rules",
  deepseek: "deepseek-chat",
};

const providerBaseUrlDefaults: Partial<Record<ProviderId, string>> = {
  deepseek: "https://api.deepseek.com",
  openai_compat: "https://api.openai.com/v1",
};

function emptyEndpoint(provider: ProviderId, model: string, maxTokens: string): EditableEndpoint {
  return {
    provider,
    model,
    max_tokens: maxTokens,
    base_url: "",
    api_key: "",
    clear_api_key: false,
    has_api_key: false,
  };
}

function fromEndpoint(endpoint: LLMEndpointConfig): EditableEndpoint {
  return {
    provider: endpoint.provider,
    model: endpoint.model,
    max_tokens: String(endpoint.max_tokens),
    base_url: endpoint.base_url || "",
    api_key: "",
    clear_api_key: false,
    has_api_key: endpoint.has_api_key,
  };
}

function toPayload(endpoint: EditableEndpoint) {
  return {
    provider: endpoint.provider,
    model: endpoint.model.trim(),
    max_tokens: Number(endpoint.max_tokens || 0),
    base_url: endpoint.base_url.trim() || null,
    api_key: endpoint.api_key.trim() || null,
    clear_api_key: endpoint.clear_api_key,
  };
}

export default function SettingsPage() {
  const [config, setConfig] = useState<SystemConfig | null>(null);
  const [form, setForm] = useState<EditableConfig>({
    generator: emptyEndpoint("local_template", "local-template", "8192"),
    reviewer: emptyEndpoint("local_rules", "local-rules", "4096"),
  });
  const [message, setMessage] = useState("");
  const [presetName, setPresetName] = useState("");
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState<EndpointTarget | null>(null);
  const [presetSaving, setPresetSaving] = useState<EndpointTarget | null>(null);
  const [presetApplying, setPresetApplying] = useState<string | null>(null);
  const [presetDeleting, setPresetDeleting] = useState<string | null>(null);
  const [subjectName, setSubjectName] = useState("");
  const [subjectCategories, setSubjectCategories] = useState("");
  const [subjectSaving, setSubjectSaving] = useState(false);

  async function loadConfig() {
    setLoading(true);
    setMessage("");
    try {
      const data = await apiFetch<SystemConfig>("/api/system/config");
      setConfig(data);
      setForm({
        generator: fromEndpoint(data.llm.generator),
        reviewer: fromEndpoint(data.llm.reviewer),
      });
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "读取配置失败");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadConfig();
  }, []);

  const llmSummary = useMemo(
    () => [
      { label: "生成", endpoint: form.generator },
      { label: "审查", endpoint: form.reviewer },
    ],
    [form]
  );

  function updateEndpoint(target: EndpointTarget, patch: Partial<EditableEndpoint>) {
    setForm((current) => ({
      ...current,
      [target]: {
        ...current[target],
        ...patch,
      },
    }));
  }

  function presetPayloadFromTarget(target: EndpointTarget) {
    return {
      name: presetName.trim(),
      ...toPayload(form[target]),
    };
  }

  function changeProvider(target: EndpointTarget, provider: ProviderId) {
    const model = localModelDefaults[provider] || form[target].model;
    const baseUrl =
      provider === "deepseek"
        ? providerBaseUrlDefaults.deepseek || ""
        : provider === "openai_compat"
          ? form[target].base_url || providerBaseUrlDefaults.openai_compat || ""
          : "";
    const usesLocalProvider = provider === "local_template" || provider === "local_rules";
    updateEndpoint(target, {
      provider,
      model,
      base_url: baseUrl || (provider === "openai_compat" ? form[target].base_url : ""),
      api_key: usesLocalProvider ? "" : form[target].api_key,
      clear_api_key: usesLocalProvider ? true : form[target].clear_api_key,
    });
  }

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setSaving(true);
    setMessage("");
    try {
      const data = await apiFetch<SystemConfig>("/api/system/config", {
        method: "POST",
        body: JSON.stringify({
          llm: {
            generator: toPayload(form.generator),
            reviewer: toPayload(form.reviewer),
          },
        }),
      });
      setConfig(data);
      setForm({
        generator: fromEndpoint(data.llm.generator),
        reviewer: fromEndpoint(data.llm.reviewer),
      });
      setMessage("模型配置已保存。");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "保存配置失败");
    } finally {
      setSaving(false);
    }
  }

  async function testLLM(target: EndpointTarget) {
    setTesting(target);
    setMessage("");
    try {
      const data = await apiFetch<{ ok: boolean; provider: string; model: string; message: string }>("/api/system/test-llm", {
        method: "POST",
        body: JSON.stringify({ target, live: true }),
      });
      setMessage(`${targetLabels[target]}：${data.ok ? "可用" : "需处理"}，${data.message}`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "测试失败");
    } finally {
      setTesting(null);
    }
  }

  async function savePreset(target: EndpointTarget) {
    const name = presetName.trim();
    if (!name) {
      setMessage("先填写预设名称。");
      return;
    }
    setPresetSaving(target);
    setMessage("");
    try {
      const data = await apiFetch<SystemConfig>("/api/system/llm-presets", {
        method: "POST",
        body: JSON.stringify(presetPayloadFromTarget(target)),
      });
      setConfig(data);
      setForm({
        generator: fromEndpoint(data.llm.generator),
        reviewer: fromEndpoint(data.llm.reviewer),
      });
      setMessage(`已保存预设：${name}`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "保存预设失败");
    } finally {
      setPresetSaving(null);
    }
  }

  async function applyPreset(name: string, target: EndpointTarget) {
    setPresetApplying(`${name}:${target}`);
    setMessage("");
    try {
      const data = await apiFetch<SystemConfig>(`/api/system/llm-presets/${encodeURIComponent(name)}/apply`, {
        method: "POST",
        body: JSON.stringify({ target }),
      });
      setConfig(data);
      setForm({
        generator: fromEndpoint(data.llm.generator),
        reviewer: fromEndpoint(data.llm.reviewer),
      });
      setMessage(`已将预设 ${name} 应用到${targetLabels[target]}。`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "应用预设失败");
    } finally {
      setPresetApplying(null);
    }
  }

  async function deletePreset(name: string) {
    setPresetDeleting(name);
    setMessage("");
    try {
      const data = await apiFetch<SystemConfig>(`/api/system/llm-presets/${encodeURIComponent(name)}`, {
        method: "DELETE",
      });
      setConfig(data);
      setMessage(`已删除预设：${name}`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "删除预设失败");
    } finally {
      setPresetDeleting(null);
    }
  }

  async function saveSubject(event: FormEvent) {
    event.preventDefault();
    const name = subjectName.trim();
    if (!name) {
      setMessage("先填写学科名称。");
      return;
    }
    setSubjectSaving(true);
    setMessage("");
    try {
      const data = await apiFetch<SystemConfig>("/api/system/subjects", {
        method: "POST",
        body: JSON.stringify({
          name,
          categories: subjectCategories.split(/[,，\s]+/).filter(Boolean),
        }),
      });
      setConfig(data);
      setSubjectName("");
      setSubjectCategories("");
      setMessage(`已保存学科：${name}`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "保存学科失败");
    } finally {
      setSubjectSaving(false);
    }
  }

  function renderEndpoint(target: EndpointTarget) {
    const endpoint = form[target];
    const usesApiKey = endpoint.provider === "openai_compat" || endpoint.provider === "deepseek" || endpoint.provider === "anthropic";
    const usesBaseUrl = endpoint.provider === "openai_compat" || endpoint.provider === "deepseek";

    return (
      <section className="endpointBlock" key={target}>
        <div className="endpointTitle">
          <div>
            <h3>{targetLabels[target]}</h3>
            <span>{endpoint.provider}</span>
          </div>
          <span className={endpoint.has_api_key ? "badge high" : "badge"}>
            <KeyRound size={13} />
            {endpoint.has_api_key ? "Key 已配置" : "无 Key"}
          </span>
        </div>

        <div className="formGrid">
          <div className="row">
            <div className="field">
              <label>供应商</label>
              <select value={endpoint.provider} onChange={(event) => changeProvider(target, event.target.value as ProviderId)}>
                {providerOptions.map((provider) => (
                  <option key={provider.value} value={provider.value}>
                    {provider.label}
                  </option>
                ))}
              </select>
            </div>
            <div className="field">
              <label>模型名</label>
              <input value={endpoint.model} onChange={(event) => updateEndpoint(target, { model: event.target.value })} />
            </div>
          </div>

          <div className="row">
            <div className="field">
              <label>最大输出 Token</label>
              <input
                min={1}
                type="number"
                value={endpoint.max_tokens}
                onChange={(event) => updateEndpoint(target, { max_tokens: event.target.value })}
              />
            </div>
            <div className="field">
              <label>Base URL</label>
              <input
                disabled={!usesBaseUrl}
                placeholder="https://api.example.com/v1"
                value={endpoint.base_url}
                onChange={(event) => updateEndpoint(target, { base_url: event.target.value })}
              />
            </div>
          </div>

          <div className="row">
            <div className="field">
              <label>API Key</label>
              <input
                autoComplete="off"
                disabled={!usesApiKey}
                placeholder={endpoint.has_api_key ? "已配置，输入新 Key 覆盖" : "未配置"}
                type="password"
                value={endpoint.api_key}
                onChange={(event) => updateEndpoint(target, { api_key: event.target.value, clear_api_key: false })}
              />
            </div>
            <div className="field">
              <label>Key 状态</label>
              <label className="configCheck">
                <input
                  checked={endpoint.clear_api_key}
                  disabled={!usesApiKey && !endpoint.has_api_key}
                  type="checkbox"
                  onChange={(event) => updateEndpoint(target, { clear_api_key: event.target.checked, api_key: "" })}
                />
                清空已保存 Key
              </label>
            </div>
          </div>

          <button className="button" disabled={testing === target} type="button" onClick={() => testLLM(target)}>
            <PlugZap size={17} />
            {testing === target ? "测试中" : "测试配置"}
          </button>
          <button className="button" disabled={presetSaving === target} type="button" onClick={() => savePreset(target)}>
            <Save size={17} />
            {presetSaving === target ? "保存预设中" : "保存为预设"}
          </button>
        </div>
      </section>
    );
  }

  function renderPreset(preset: LLMPresetConfig) {
    return (
      <div className="presetRow" key={preset.name}>
        <div className="presetInfo">
          <strong>{preset.name}</strong>
          <span>
            {providerOptions.find((provider) => provider.value === preset.provider)?.label || preset.provider} / {preset.model}
          </span>
        </div>
        <div className="presetActions">
          <button
            className="button"
            disabled={presetApplying === `${preset.name}:generator`}
            type="button"
            onClick={() => applyPreset(preset.name, "generator")}
          >
            用于生成
          </button>
          <button
            className="button"
            disabled={presetApplying === `${preset.name}:reviewer`}
            type="button"
            onClick={() => applyPreset(preset.name, "reviewer")}
          >
            用于审查
          </button>
          <button className="button danger" disabled={presetDeleting === preset.name} type="button" onClick={() => deletePreset(preset.name)}>
            <Trash2 size={16} />
          </button>
        </div>
      </div>
    );
  }

  return (
    <>
      <header className="pageHeader">
        <div>
          <h1>模型配置</h1>
          <p>配置生成与审查链路使用的大模型供应商、模型名、Token 上限和访问凭据。</p>
        </div>
        <div className="buttonRow">
          <button className="button" disabled={loading} type="button" onClick={loadConfig}>
            <RefreshCw size={17} />
            重新读取
          </button>
        </div>
      </header>

      <section className="settingsGrid">
        <div className="settingsMain">
          <form className="panel" onSubmit={onSubmit}>
          <div className="panelHeader">
            <h2>
              <SlidersHorizontal size={18} />
              LLM Endpoint
            </h2>
            <p>保存后立即写入本地 config.yaml，供后端模型链路读取。</p>
          </div>
          <div className="panelBody formGrid">
            <div className="field">
              <label>预设名称</label>
              <input
                placeholder="例如：DeepSeek-写稿 / Claude-审查"
                value={presetName}
                onChange={(event) => setPresetName(event.target.value)}
              />
            </div>
            {renderEndpoint("generator")}
            {renderEndpoint("reviewer")}
            <div className="buttonRow">
              <button className="button primary" disabled={saving} type="submit">
                <Save size={17} />
                {saving ? "保存中" : "保存配置"}
              </button>
              {message && <span className="muted">{message}</span>}
            </div>
          </div>
          </form>

          <form className="panel" onSubmit={saveSubject}>
            <div className="panelHeader">
              <h2>
                <Plus size={18} />
                学科管理
              </h2>
              <p>这里是唯一的学科新增入口，生成和素材库都会使用这份列表。</p>
            </div>
            <div className="panelBody formGrid">
              <div className="row">
                <div className="field">
                  <label>学科名称</label>
                  <input
                    placeholder="例如：初级会计"
                    value={subjectName}
                    onChange={(event) => setSubjectName(event.target.value)}
                  />
                </div>
                <div className="field">
                  <label>类目</label>
                  <input
                    placeholder="用逗号或空格分隔"
                    value={subjectCategories}
                    onChange={(event) => setSubjectCategories(event.target.value)}
                  />
                </div>
              </div>
              <button className="button primary" disabled={subjectSaving} type="submit">
                <Plus size={17} />
                {subjectSaving ? "保存中" : "添加学科"}
              </button>
              <div className="subjectList">
                {config?.subjects.length ? (
                  config.subjects.map((subject) => (
                    <div className="subjectRow" key={subject.id}>
                      <div>
                        <strong>{subject.name}</strong>
                        <span>{subject.categories.length ? subject.categories.join(" / ") : "未设置类目"}</span>
                      </div>
                    </div>
                  ))
                ) : (
                  <div className="empty">还没有学科。</div>
                )}
              </div>
            </div>
          </form>
        </div>

        <aside className="panel">
          <div className="panelHeader">
            <h2>
              <Server size={18} />
              当前配置
            </h2>
            <p>{config ? config.app.name : "未读取"}</p>
          </div>
          <div className="panelBody">
            <div className="configSummary">
              {llmSummary.map((item) => (
                <div className="configSummaryRow" key={item.label}>
                  <div>
                    <strong>{item.label}</strong>
                    <span>{providerOptions.find((provider) => provider.value === item.endpoint.provider)?.label}</span>
                  </div>
                  <div>
                    <strong>{item.endpoint.model || "未填写"}</strong>
                    <span>{Number(item.endpoint.max_tokens || 0).toLocaleString()} tokens</span>
                  </div>
                  <span className={item.endpoint.has_api_key ? "badge pass" : "badge"}>
                    {item.endpoint.has_api_key ? <CheckCircle2 size={13} /> : null}
                    {item.endpoint.has_api_key ? "已授权" : "本地/未授权"}
                  </span>
                </div>
              ))}
            </div>
            <div className="configMeta">
              <span>RAGFlow</span>
              <strong>{config?.ragflow.enabled ? "enabled" : "disabled"}</strong>
              <span>Storage</span>
              <strong>{config?.storage.type || "-"}</strong>
            </div>
            <div className="presetList">
              <div className="presetHeader">
                <strong>已保存预设</strong>
                <span>{config?.llm.presets.length || 0} 个</span>
              </div>
              {config?.llm.presets.length ? config.llm.presets.map(renderPreset) : <div className="empty">还没有 LLM 预设。</div>}
            </div>
          </div>
        </aside>
      </section>
    </>
  );
}
