"use client";

import { FormEvent, ReactNode, useEffect, useMemo, useState } from "react";
import { CheckCircle2, KeyRound, Pencil, PlugZap, PlusCircle, RefreshCw, Save, Server, SlidersHorizontal, Trash2 } from "lucide-react";
import { apiFetch, AIFeatureEndpointConfig, LLMEndpointConfig, LLMModelConfig, PaperAICleanupConfig, SystemConfig } from "../../lib/api";

type ProviderId = LLMEndpointConfig["provider"];
type EndpointTarget = "generator" | "reviewer";
type FeatureTarget = EndpointTarget | "paper_ai_cleanup" | "question_ai_standardizer" | "question_auto_tagger";

type EditableModel = {
  id: string;
  name: string;
  provider: ProviderId;
  model: string;
  max_tokens: string;
  base_url: string;
  api_key: string;
  clear_api_key: boolean;
  has_api_key: boolean;
};

type EditableConfig = Record<EndpointTarget, { model_id: string }>;

type EditablePaperAICleanup = {
  model_id: string;
  enabled: boolean;
  disable_thinking: boolean;
  system_prompt: string;
};

type EditableAIFeatureEndpoint = {
  model_id: string;
  enabled: boolean;
  disable_thinking: boolean;
};

const providerOptions: Array<{ value: ProviderId; label: string }> = [
  { value: "local_template", label: "本地模板" },
  { value: "local_rules", label: "本地规则" },
  { value: "deepseek", label: "DeepSeek" },
  { value: "openai_compat", label: "OpenAI 兼容" },
  { value: "anthropic", label: "Anthropic" },
];

const featureLabels: Record<FeatureTarget, string> = {
  generator: "生成模型",
  reviewer: "审查模型",
  paper_ai_cleanup: "试卷 AI 切题（含清噪）",
  question_ai_standardizer: "题目补全与标准化",
  question_auto_tagger: "题目自动考点标注",
};

const featureUsageLabels: Record<FeatureTarget, string[]> = {
  generator: ["内容生成", "生成任务正文与发布包"],
  reviewer: ["内容审查", "生成结果的纯大模型/混合审查", "题目答案解析审核"],
  paper_ai_cleanup: ["PDF/OCR 文本清噪", "试卷 AI 切题", "结构化入库前处理"],
  question_ai_standardizer: ["审核工作台", "AI 补全答案与解析", "题干/选项/答案/解析标准化"],
  question_auto_tagger: ["审核工作台", "自动匹配知识点", "批量考点标注"],
};

const remoteOnlyTargets = new Set<FeatureTarget>(["paper_ai_cleanup", "question_ai_standardizer", "question_auto_tagger"]);

const localModelDefaults: Partial<Record<ProviderId, string>> = {
  local_template: "local-template",
  local_rules: "local-rules",
  deepseek: "deepseek-chat",
};

const providerBaseUrlDefaults: Partial<Record<ProviderId, string>> = {
  deepseek: "https://api.deepseek.com",
  openai_compat: "https://api.openai.com/v1",
};

function emptyModel(): EditableModel {
  return {
    id: "",
    name: "",
    provider: "local_template",
    model: "local-template",
    max_tokens: "8192",
    base_url: "",
    api_key: "",
    clear_api_key: false,
    has_api_key: false,
  };
}

function emptyPaperAICleanup(): EditablePaperAICleanup {
  return {
    model_id: "",
    enabled: true,
    disable_thinking: true,
    system_prompt:
      "你是严谨的中文试卷 OCR 清噪、切题与结构化助手，只返回 JSON。\n你的职责不是自由总结，而是把 OCR 文本整理成可直接入库的题目结构。\n你必须先清噪，再切题，再抽取并标准化题号、题型、题干、选项、答案、解析；若原文未提供答案或解析，可以留空，不要自行解题补全。\n不要漏题，不要合并多题，不要臆造不存在的信息；输出结果必须是最终切题结果，后续解题会单独处理。\n输出必须严格符合用户给定的 JSON 结构。",
  };
}

function emptyAIFeatureEndpoint(): EditableAIFeatureEndpoint {
  return {
    model_id: "",
    enabled: true,
    disable_thinking: true,
  };
}

function fromModel(model: LLMModelConfig): EditableModel {
  return {
    id: model.id,
    name: model.name,
    provider: model.provider,
    model: model.model,
    max_tokens: String(model.max_tokens),
    base_url: model.base_url || "",
    api_key: "",
    clear_api_key: false,
    has_api_key: model.has_api_key,
  };
}

function fromSelection(endpoint: LLMEndpointConfig): { model_id: string } {
  return {
    model_id: endpoint.model_id || "",
  };
}

function fromPaperAICleanup(endpoint: PaperAICleanupConfig): EditablePaperAICleanup {
  return {
    model_id: endpoint.model_id || "",
    enabled: endpoint.enabled,
    disable_thinking: endpoint.disable_thinking,
    system_prompt: endpoint.system_prompt || "",
  };
}

function fromAIFeatureEndpoint(endpoint: AIFeatureEndpointConfig): EditableAIFeatureEndpoint {
  return {
    model_id: endpoint.model_id || "",
    enabled: endpoint.enabled,
    disable_thinking: endpoint.disable_thinking,
  };
}

function toModelPayload(model: EditableModel) {
  return {
    id: model.id.trim() || null,
    name: model.name.trim(),
    provider: model.provider,
    model: model.model.trim(),
    max_tokens: Number(model.max_tokens || 0),
    base_url: model.base_url.trim() || null,
    api_key: model.api_key.trim() || null,
    clear_api_key: model.clear_api_key,
  };
}

function providerLabel(provider: ProviderId): string {
  return providerOptions.find((item) => item.value === provider)?.label || provider;
}

function endpointNeedsApiKey(provider: ProviderId): boolean {
  return provider === "openai_compat" || provider === "deepseek" || provider === "anthropic";
}

function endpointUsesBaseUrl(provider: ProviderId): boolean {
  return provider === "openai_compat" || provider === "deepseek";
}

function modelBadgeText(model: LLMModelConfig | null): string {
  if (!model) return "未选择";
  if (model.provider === "local_template" || model.provider === "local_rules") return "本地模型";
  return model.has_api_key ? "Key 已配置" : "无 Key";
}

function modelBadgeClass(model: LLMModelConfig | null): string {
  if (!model) return "badge";
  if (model.provider === "local_template" || model.provider === "local_rules" || model.has_api_key) return "badge pass";
  return "badge";
}

export default function SettingsPage() {
  const [config, setConfig] = useState<SystemConfig | null>(null);
  const [form, setForm] = useState<EditableConfig>({
    generator: { model_id: "" },
    reviewer: { model_id: "" },
  });
  const [paperAICleanup, setPaperAICleanup] = useState<EditablePaperAICleanup>(emptyPaperAICleanup());
  const [questionAIStandardizer, setQuestionAIStandardizer] = useState<EditableAIFeatureEndpoint>(emptyAIFeatureEndpoint());
  const [questionAutoTagger, setQuestionAutoTagger] = useState<EditableAIFeatureEndpoint>(emptyAIFeatureEndpoint());
  const [modelEditor, setModelEditor] = useState<EditableModel>(emptyModel());
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [modelSaving, setModelSaving] = useState(false);
  const [modelDeleting, setModelDeleting] = useState<string | null>(null);
  const [testing, setTesting] = useState<FeatureTarget | null>(null);

  const models = useMemo(() => config?.llm.models || config?.llm.presets || [], [config]);
  const modelsById = useMemo(() => new Map(models.map((item) => [item.id, item])), [models]);
  const modelUsage = useMemo(() => {
    const usage = new Map<string, string[]>();
    const addUsage = (modelId: string, label: string) => {
      if (!modelId) return;
      const current = usage.get(modelId) || [];
      current.push(label);
      usage.set(modelId, current);
    };
    addUsage(form.generator.model_id, featureLabels.generator);
    addUsage(form.reviewer.model_id, featureLabels.reviewer);
    addUsage(paperAICleanup.model_id, featureLabels.paper_ai_cleanup);
    addUsage(questionAIStandardizer.model_id, featureLabels.question_ai_standardizer);
    addUsage(questionAutoTagger.model_id, featureLabels.question_auto_tagger);
    return usage;
  }, [form, paperAICleanup.model_id, questionAIStandardizer.model_id, questionAutoTagger.model_id]);

  function applyConfig(data: SystemConfig) {
    setConfig(data);
    setForm({
      generator: fromSelection(data.llm.generator),
      reviewer: fromSelection(data.llm.reviewer),
    });
    setPaperAICleanup(fromPaperAICleanup(data.paper_ai_cleanup));
    setQuestionAIStandardizer(fromAIFeatureEndpoint(data.question_ai_standardizer));
    setQuestionAutoTagger(fromAIFeatureEndpoint(data.question_auto_tagger));
  }

  async function loadConfig() {
    setLoading(true);
    setMessage("");
    try {
      const data = await apiFetch<SystemConfig>("/api/system/config");
      applyConfig(data);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "读取配置失败");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadConfig();
  }, []);

  function changeModelProvider(provider: ProviderId) {
    setModelEditor((current) => {
      const nextModel = localModelDefaults[provider] || current.model;
      const nextBaseUrl =
        provider === "deepseek"
          ? providerBaseUrlDefaults.deepseek || ""
          : provider === "openai_compat"
            ? current.base_url || providerBaseUrlDefaults.openai_compat || ""
            : "";
      const usesLocalProvider = provider === "local_template" || provider === "local_rules";
      return {
        ...current,
        provider,
        model: nextModel,
        base_url: nextBaseUrl || (provider === "openai_compat" ? current.base_url : ""),
        api_key: usesLocalProvider ? "" : current.api_key,
        clear_api_key: usesLocalProvider ? true : current.clear_api_key,
      };
    });
  }

  function updateEndpoint(target: EndpointTarget, modelId: string) {
    setForm((current) => ({
      ...current,
      [target]: { model_id: modelId },
    }));
  }

  function selectedModel(target: FeatureTarget): LLMModelConfig | null {
    const modelId =
      target === "generator"
        ? form.generator.model_id
        : target === "reviewer"
          ? form.reviewer.model_id
          : target === "paper_ai_cleanup"
            ? paperAICleanup.model_id
            : target === "question_ai_standardizer"
              ? questionAIStandardizer.model_id
              : questionAutoTagger.model_id;
    return modelsById.get(modelId) || null;
  }

  function availableModels(target: FeatureTarget): LLMModelConfig[] {
    if (!remoteOnlyTargets.has(target)) return models;
    return models.filter((model) => model.provider !== "local_template" && model.provider !== "local_rules");
  }

  async function saveFeatureConfig(event: FormEvent) {
    event.preventDefault();
    if (!form.generator.model_id || !form.reviewer.model_id || !paperAICleanup.model_id || !questionAIStandardizer.model_id || !questionAutoTagger.model_id) {
      setMessage("请先为每个功能选择模型。");
      return;
    }

    setSaving(true);
    setMessage("");
    try {
      const data = await apiFetch<SystemConfig>("/api/system/config", {
        method: "POST",
        body: JSON.stringify({
          llm: {
            generator: { model_id: form.generator.model_id },
            reviewer: { model_id: form.reviewer.model_id },
          },
          paper_ai_cleanup: {
            model_id: paperAICleanup.model_id,
            enabled: paperAICleanup.enabled,
            disable_thinking: paperAICleanup.disable_thinking,
            system_prompt: paperAICleanup.system_prompt.trim(),
          },
          question_ai_standardizer: {
            model_id: questionAIStandardizer.model_id,
            enabled: questionAIStandardizer.enabled,
            disable_thinking: questionAIStandardizer.disable_thinking,
          },
          question_auto_tagger: {
            model_id: questionAutoTagger.model_id,
            enabled: questionAutoTagger.enabled,
            disable_thinking: questionAutoTagger.disable_thinking,
          },
        }),
      });
      applyConfig(data);
      setMessage("功能模型配置已保存。");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "保存配置失败");
    } finally {
      setSaving(false);
    }
  }

  async function saveModel(event: FormEvent) {
    event.preventDefault();
    const name = modelEditor.name.trim();
    if (!name) {
      setMessage("先填写模型名称。");
      return;
    }

    setModelSaving(true);
    setMessage("");
    try {
      const data = await apiFetch<SystemConfig>("/api/system/llm-models", {
        method: "POST",
        body: JSON.stringify(toModelPayload(modelEditor)),
      });
      applyConfig(data);
      setModelEditor(emptyModel());
      setMessage(`${modelEditor.id ? "模型已更新" : "模型已新增"}：${name}`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "保存模型失败");
    } finally {
      setModelSaving(false);
    }
  }

  async function deleteModel(model: LLMModelConfig) {
    setModelDeleting(model.id);
    setMessage("");
    try {
      const data = await apiFetch<SystemConfig>(`/api/system/llm-models/${encodeURIComponent(model.id)}`, {
        method: "DELETE",
      });
      applyConfig(data);
      if (modelEditor.id === model.id) {
        setModelEditor(emptyModel());
      }
      setMessage(`已删除模型：${model.name}`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "删除模型失败");
    } finally {
      setModelDeleting(null);
    }
  }

  async function testLLM(target: FeatureTarget) {
    const model = selectedModel(target);
    if (!model) {
      setMessage("请先为该功能选择模型。");
      return;
    }
    setTesting(target);
    setMessage("");
    try {
      const data = await apiFetch<{ ok: boolean; provider: string; model: string; message: string }>("/api/system/test-llm", {
        method: "POST",
        body: JSON.stringify({ target, live: true }),
      });
      setMessage(`${featureLabels[target]}：${data.ok ? "可用" : "需处理"}，${data.message}`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "测试失败");
    } finally {
      setTesting(null);
    }
  }

  function editModel(model: LLMModelConfig) {
    setModelEditor(fromModel(model));
    setMessage("");
  }

  function renderFeatureBlock(
    target: FeatureTarget,
    value: string,
    onChange: (modelId: string) => void,
    extras?: ReactNode,
    description?: string,
  ) {
    const currentModel = selectedModel(target);
    const targetModels = availableModels(target);
    return (
      <section className="endpointBlock" key={target}>
        <div className="endpointTitle">
          <div>
            <h3>{featureLabels[target]}</h3>
            <span>{currentModel ? `${providerLabel(currentModel.provider)} / ${currentModel.model}` : "未选择模型"}</span>
          </div>
          <span className={modelBadgeClass(currentModel)}>
            <KeyRound size={13} />
            {modelBadgeText(currentModel)}
          </span>
        </div>
        <div className="usageList">
          {featureUsageLabels[target].map((usage) => (
            <span key={usage}>{usage}</span>
          ))}
        </div>
        {description ? <p className="muted">{description}</p> : null}

        <div className="formGrid">
          <div className="row">
            <div className="field">
              <label>选择模型</label>
              <select value={value} onChange={(event) => onChange(event.target.value)}>
                <option value="">请选择模型</option>
                {targetModels.map((model) => (
                  <option key={model.id} value={model.id}>
                    {model.name} · {providerLabel(model.provider)} / {model.model}
                  </option>
                ))}
              </select>
            </div>
            <div className="field">
              <label>当前绑定</label>
              <div className="configCheck">{currentModel ? `${currentModel.name} · ${Number(currentModel.max_tokens).toLocaleString()} tokens` : "未选择模型"}</div>
            </div>
          </div>

          {extras}

          <button className="button" disabled={testing === target || !value} type="button" onClick={() => testLLM(target)}>
            <PlugZap size={17} />
            {testing === target ? "测试中" : "测试配置"}
          </button>
        </div>
      </section>
    );
  }

  return (
    <>
      <header className="pageHeader">
        <div>
          <h1>模型配置</h1>
          <p>先维护统一模型库，再为生成、审查、试卷处理和题目标注等功能选择要使用的模型。</p>
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
          <section className="panel">
            <div className="panelHeader">
              <h2>
                <Server size={18} />
                模型库
              </h2>
              <p>新增、编辑和复用模型连接配置。下面各功能只需要从这里选择模型。</p>
            </div>
            <form className="panelBody formGrid" onSubmit={saveModel}>
              <div className="row">
                <div className="field">
                  <label>模型名称</label>
                  <input
                    placeholder="例如：DeepSeek-写稿 / Claude-审查 / 本地-Ollama"
                    value={modelEditor.name}
                    onChange={(event) => setModelEditor((current) => ({ ...current, name: event.target.value }))}
                  />
                </div>
                <div className="field">
                  <label>供应商</label>
                  <select value={modelEditor.provider} onChange={(event) => changeModelProvider(event.target.value as ProviderId)}>
                    {providerOptions.map((provider) => (
                      <option key={provider.value} value={provider.value}>
                        {provider.label}
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              <div className="row">
                <div className="field">
                  <label>模型名</label>
                  <input value={modelEditor.model} onChange={(event) => setModelEditor((current) => ({ ...current, model: event.target.value }))} />
                </div>
                <div className="field">
                  <label>最大输出 Token</label>
                  <input
                    min={1}
                    type="number"
                    value={modelEditor.max_tokens}
                    onChange={(event) => setModelEditor((current) => ({ ...current, max_tokens: event.target.value }))}
                  />
                </div>
              </div>

              <div className="row">
                <div className="field">
                  <label>Base URL</label>
                  <input
                    disabled={!endpointUsesBaseUrl(modelEditor.provider)}
                    placeholder="https://api.example.com/v1"
                    value={modelEditor.base_url}
                    onChange={(event) => setModelEditor((current) => ({ ...current, base_url: event.target.value }))}
                  />
                </div>
                <div className="field">
                  <label>API Key</label>
                  <input
                    autoComplete="off"
                    disabled={!endpointNeedsApiKey(modelEditor.provider)}
                    placeholder={modelEditor.has_api_key ? "已配置，输入新 Key 覆盖" : "未配置"}
                    type="password"
                    value={modelEditor.api_key}
                    onChange={(event) => setModelEditor((current) => ({ ...current, api_key: event.target.value, clear_api_key: false }))}
                  />
                </div>
              </div>

              <div className="row">
                <div className="field">
                  <label>Key 状态</label>
                  <label className="configCheck">
                    <input
                      checked={modelEditor.clear_api_key}
                      disabled={!endpointNeedsApiKey(modelEditor.provider) && !modelEditor.has_api_key}
                      type="checkbox"
                      onChange={(event) => setModelEditor((current) => ({ ...current, clear_api_key: event.target.checked, api_key: "" }))}
                    />
                    清空已保存 Key
                  </label>
                </div>
                <div className="field">
                  <label>当前状态</label>
                  <div className="configCheck">{modelEditor.id ? `正在编辑：${modelEditor.name || "未命名模型"}` : "正在新增模型"}</div>
                </div>
              </div>

              <div className="buttonRow">
                <button className="button primary" disabled={modelSaving} type="submit">
                  <Save size={17} />
                  {modelSaving ? "保存中" : modelEditor.id ? "保存修改" : "新增模型"}
                </button>
                <button className="button" type="button" onClick={() => setModelEditor(emptyModel())}>
                  <PlusCircle size={17} />
                  新建空白模型
                </button>
                {message ? <span className="muted">{message}</span> : null}
              </div>

              <div className="presetList">
                <div className="presetHeader">
                  <strong>已保存模型</strong>
                  <span>{models.length} 个</span>
                </div>
                {models.length ? (
                  models.map((model) => (
                    <div className="presetRow" key={model.id}>
                      <div className="presetInfo">
                        <strong>{model.name}</strong>
                        <span>
                          {providerLabel(model.provider)} / {model.model} / {Number(model.max_tokens).toLocaleString()} tokens
                        </span>
                        <span>{modelUsage.get(model.id)?.join("、") || "当前未被功能使用"}</span>
                      </div>
                      <div className="presetActions">
                        <button className="button" type="button" onClick={() => editModel(model)}>
                          <Pencil size={16} />
                          编辑
                        </button>
                        <button className="button danger" disabled={modelDeleting === model.id} type="button" onClick={() => deleteModel(model)}>
                          <Trash2 size={16} />
                        </button>
                      </div>
                    </div>
                  ))
                ) : (
                  <div className="empty">还没有模型，请先新增一个模型。</div>
                )}
              </div>
            </form>
          </section>

          <form className="panel" onSubmit={saveFeatureConfig}>
            <div className="panelHeader">
              <h2>
                <SlidersHorizontal size={18} />
                功能绑定
              </h2>
              <p>各功能只保存自己选择的模型和少量行为开关，真正的连接信息统一从模型库读取。</p>
            </div>
            <div className="panelBody formGrid">
              {renderFeatureBlock("generator", form.generator.model_id, (modelId) => updateEndpoint("generator", modelId))}
              {renderFeatureBlock("reviewer", form.reviewer.model_id, (modelId) => updateEndpoint("reviewer", modelId))}
              {renderFeatureBlock(
                "paper_ai_cleanup",
                paperAICleanup.model_id,
                (modelId) => setPaperAICleanup((current) => ({ ...current, model_id: modelId })),
                <>
                  <div className="row">
                    <div className="field">
                      <label>启用状态</label>
                      <label className="configCheck">
                        <input
                          checked={paperAICleanup.enabled}
                          type="checkbox"
                          onChange={(event) => setPaperAICleanup((current) => ({ ...current, enabled: event.target.checked }))}
                        />
                        启用 AI 切题与清噪
                      </label>
                    </div>
                    <div className="field">
                      <label>思考模式</label>
                      <label className="configCheck">
                        <input
                          checked={paperAICleanup.disable_thinking}
                          type="checkbox"
                          onChange={(event) => setPaperAICleanup((current) => ({ ...current, disable_thinking: event.target.checked }))}
                        />
                        关闭模型思考模式
                      </label>
                    </div>
                  </div>
                  <div className="field">
                    <label>System Prompt</label>
                    <textarea
                      className="settingsTextarea"
                      rows={10}
                      value={paperAICleanup.system_prompt}
                      onChange={(event) => setPaperAICleanup((current) => ({ ...current, system_prompt: event.target.value }))}
                    />
                  </div>
                </>,
                "当前上传试卷后的 AI 解析链路，读取的就是这里选择的模型；它负责清噪和切题，缺失答案/解析的补全会改由后续独立解题任务异步处理。",
              )}
              {renderFeatureBlock(
                "question_ai_standardizer",
                questionAIStandardizer.model_id,
                (modelId) => setQuestionAIStandardizer((current) => ({ ...current, model_id: modelId })),
                <div className="row">
                  <div className="field">
                    <label>启用状态</label>
                    <label className="configCheck">
                      <input
                        checked={questionAIStandardizer.enabled}
                        type="checkbox"
                        onChange={(event) => setQuestionAIStandardizer((current) => ({ ...current, enabled: event.target.checked }))}
                      />
                      启用该功能模型
                    </label>
                  </div>
                  <div className="field">
                    <label>思考模式</label>
                    <label className="configCheck">
                      <input
                        checked={questionAIStandardizer.disable_thinking}
                        type="checkbox"
                        onChange={(event) => setQuestionAIStandardizer((current) => ({ ...current, disable_thinking: event.target.checked }))}
                      />
                      关闭模型思考模式
                    </label>
                  </div>
                </div>,
              )}
              {renderFeatureBlock(
                "question_auto_tagger",
                questionAutoTagger.model_id,
                (modelId) => setQuestionAutoTagger((current) => ({ ...current, model_id: modelId })),
                <div className="row">
                  <div className="field">
                    <label>启用状态</label>
                    <label className="configCheck">
                      <input
                        checked={questionAutoTagger.enabled}
                        type="checkbox"
                        onChange={(event) => setQuestionAutoTagger((current) => ({ ...current, enabled: event.target.checked }))}
                      />
                      启用该功能模型
                    </label>
                  </div>
                  <div className="field">
                    <label>思考模式</label>
                    <label className="configCheck">
                      <input
                        checked={questionAutoTagger.disable_thinking}
                        type="checkbox"
                        onChange={(event) => setQuestionAutoTagger((current) => ({ ...current, disable_thinking: event.target.checked }))}
                      />
                      关闭模型思考模式
                    </label>
                  </div>
                </div>,
              )}
              <div className="buttonRow">
                <button className="button primary" disabled={saving} type="submit">
                  <Save size={17} />
                  {saving ? "保存中" : "保存功能配置"}
                </button>
                {message ? <span className="muted">{message}</span> : null}
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
              {(["generator", "reviewer", "paper_ai_cleanup", "question_ai_standardizer", "question_auto_tagger"] as FeatureTarget[]).map((target) => {
                const model = selectedModel(target);
                const isEnabled =
                  target === "paper_ai_cleanup"
                    ? paperAICleanup.enabled
                    : target === "question_ai_standardizer"
                      ? questionAIStandardizer.enabled
                      : target === "question_auto_tagger"
                        ? questionAutoTagger.enabled
                        : true;
                const thinkingState =
                  target === "paper_ai_cleanup"
                    ? paperAICleanup.disable_thinking
                    : target === "question_ai_standardizer"
                      ? questionAIStandardizer.disable_thinking
                      : target === "question_auto_tagger"
                        ? questionAutoTagger.disable_thinking
                        : null;

                return (
                  <div className="configSummaryRow" key={target}>
                    <div>
                      <strong>{featureLabels[target]}</strong>
                      <span>
                        {model ? providerLabel(model.provider) : "未选择模型"}
                        {thinkingState === null ? "" : thinkingState ? " / 已关闭思考" : " / 允许思考"}
                      </span>
                    </div>
                    <div>
                      <strong>{model?.name || "未绑定模型"}</strong>
                      <span>{model ? `${model.model} / ${Number(model.max_tokens).toLocaleString()} tokens` : "保存后生效"}</span>
                    </div>
                    <span className={isEnabled ? "badge pass" : "badge"}>
                      {isEnabled ? <CheckCircle2 size={13} /> : null}
                      {isEnabled ? "已启用" : "已关闭"}
                    </span>
                  </div>
                );
              })}
            </div>
            <div className="configMeta">
              <span>模型库</span>
              <strong>{models.length} 个</strong>
              <span>Storage</span>
              <strong>{config?.storage.type || "-"}</strong>
              <span>RAGFlow</span>
              <strong>{config?.ragflow.enabled ? "enabled" : "disabled"}</strong>
            </div>
            <div className="calloutBox">
              <strong>配置方式已调整</strong>
              <p className="muted">现在先维护模型库，再为每个功能选择模型。后续切换模型时，不需要重复填写 provider、Base URL 和 Key。</p>
            </div>
          </div>
        </aside>
      </section>
    </>
  );
}
