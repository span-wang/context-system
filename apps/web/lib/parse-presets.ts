export type SharedParsePreset = "vl15" | "v3";
export type SharedParseOutputFormat = "markdown" | "text";

export type ParsePresetOption = {
  value: SharedParsePreset;
  label: string;
  short_label: string;
  engine: string;
  description: string;
  dpi_hint: string;
  primary: boolean;
  defaults: {
    render_dpi: number;
    trim_margins: boolean;
    remove_repeated_lines: boolean;
    watermark_detection: boolean;
    enable_formula_recognition: boolean;
  };
};

export type ParseOutputFormatOption = {
  value: SharedParseOutputFormat;
  label: string;
};

export type ParseCapabilityResponse = {
  default_preset: SharedParsePreset;
  default_output_format: SharedParseOutputFormat;
  force_ocr_locked: boolean;
  default_page_chunk_size: number;
  presets: ParsePresetOption[];
  output_formats: ParseOutputFormatOption[];
};

export type ParsePresetDefaults = {
  renderDpi: string;
  trimMargins: boolean;
  removeRepeatedLines: boolean;
  watermarkDetection: boolean;
  enableFormulaRecognition: boolean;
};

export type ParseRequestState = {
  preset: SharedParsePreset;
  outputFormat: SharedParseOutputFormat;
  rawOcrMode: boolean;
  preservePdfImageContent: boolean;
  renderDpi: string;
  pageChunkSize: string;
  cropHeaderRatio: string;
  cropFooterRatio: string;
  trimMargins: boolean;
  removeRepeatedLines: boolean;
  watermarkDetection: boolean;
};

export const FALLBACK_PARSE_CAPABILITY: ParseCapabilityResponse = {
  default_preset: "vl15",
  default_output_format: "markdown",
  force_ocr_locked: true,
  default_page_chunk_size: 4,
  presets: [
    {
      value: "vl15",
      label: "VL1.5",
      short_label: "VL1.5",
      engine: "PaddleOCR-VL1.5",
      description: "多模态整卷解析，适合复杂图文混排 PDF 和整卷重组输出。",
      dpi_hint: "240",
      primary: true,
      defaults: {
        render_dpi: 240,
        trim_margins: true,
        remove_repeated_lines: false,
        watermark_detection: false,
        enable_formula_recognition: false,
      },
    },
    {
      value: "v3",
      label: "V3",
      short_label: "V3",
      engine: "PP-StructureV3",
      description: "结构化版面解析，适合表格、题号分区和复杂布局页。",
      dpi_hint: "320",
      primary: true,
      defaults: {
        render_dpi: 320,
        trim_margins: true,
        remove_repeated_lines: true,
        watermark_detection: true,
        enable_formula_recognition: false,
      },
    },
  ],
  output_formats: [
    { value: "markdown", label: "Markdown" },
    { value: "text", label: "TXT" },
  ],
};

export const FULL_PARSE_PRESET_OPTIONS: ParsePresetOption[] = FALLBACK_PARSE_CAPABILITY.presets;
export const PRIMARY_PARSE_PRESET_OPTIONS: ParsePresetOption[] = FALLBACK_PARSE_CAPABILITY.presets.filter(
  (option) => option.primary
);
export const PARSE_OUTPUT_FORMAT_OPTIONS: ParseOutputFormatOption[] = FALLBACK_PARSE_CAPABILITY.output_formats;

export function normalizeParseCapability(capability?: ParseCapabilityResponse | null): ParseCapabilityResponse {
  if (!capability) return FALLBACK_PARSE_CAPABILITY;
  if (!Array.isArray(capability.presets) || !capability.presets.length) return FALLBACK_PARSE_CAPABILITY;
  if (!Array.isArray(capability.output_formats) || !capability.output_formats.length) return FALLBACK_PARSE_CAPABILITY;
  return capability;
}

export function getParsePresetOptions(capability?: ParseCapabilityResponse | null): ParsePresetOption[] {
  return normalizeParseCapability(capability).presets;
}

export function getPrimaryParsePresetOptions(capability?: ParseCapabilityResponse | null): ParsePresetOption[] {
  return getParsePresetOptions(capability).filter((option) => option.primary);
}

export function getParseOutputFormatOptions(capability?: ParseCapabilityResponse | null): ParseOutputFormatOption[] {
  return normalizeParseCapability(capability).output_formats;
}

export function getParsePresetOption(
  preset: SharedParsePreset,
  capability?: ParseCapabilityResponse | null
): ParsePresetOption {
  const normalized = normalizeParseCapability(capability);
  return normalized.presets.find((option) => option.value === preset) || normalized.presets[0];
}

export function getParsePresetDefaults(
  preset: SharedParsePreset,
  capability?: ParseCapabilityResponse | null
): ParsePresetDefaults {
  const defaults = getParsePresetOption(preset, capability).defaults;
  return {
    renderDpi: String(defaults.render_dpi),
    trimMargins: defaults.trim_margins,
    removeRepeatedLines: defaults.remove_repeated_lines,
    watermarkDetection: defaults.watermark_detection,
    enableFormulaRecognition: defaults.enable_formula_recognition,
  };
}

export function getParsePresetSummary(
  preset: SharedParsePreset,
  capability?: ParseCapabilityResponse | null
): string {
  return getParsePresetOption(preset, capability).description;
}

export function isFormulaPreset(
  preset: SharedParsePreset,
  capability?: ParseCapabilityResponse | null
): boolean {
  return getParsePresetOption(preset, capability).defaults.enable_formula_recognition;
}

export function buildParseQueryParams(
  state: ParseRequestState,
  capability?: ParseCapabilityResponse | null,
  seed?: Record<string, string>
): URLSearchParams {
  const params = new URLSearchParams(seed);
  applyParseRequestParams(params, state, capability);
  return params;
}

export function appendParseFormFields(
  form: FormData,
  state: ParseRequestState,
  capability?: ParseCapabilityResponse | null,
  extra?: Record<string, string>
): void {
  if (extra) {
    for (const [key, value] of Object.entries(extra)) {
      form.append(key, value);
    }
  }
  applyParseRequestParams(
    {
      set(key: string, value: string) {
        form.append(key, value);
      },
    },
    state,
    capability
  );
}

type ParamSink = {
  set(key: string, value: string): void;
};

function applyParseRequestParams(
  sink: ParamSink,
  state: ParseRequestState,
  capability?: ParseCapabilityResponse | null
): void {
  sink.set("preset", state.preset);
  sink.set("output_format", state.outputFormat);
  sink.set("force_ocr", "true");
  sink.set("trim_margins", String(state.trimMargins));
  sink.set("remove_repeated_lines", String(state.removeRepeatedLines));
  sink.set("watermark_detection", String(state.watermarkDetection));
  sink.set("enable_formula_recognition", String(isFormulaPreset(state.preset, capability)));

  if (state.rawOcrMode) {
    sink.set("raw_ocr_mode", "true");
  }
  if (!state.preservePdfImageContent) {
    sink.set("preserve_pdf_image_content", "false");
  }

  if (Number(state.renderDpi) > 0) {
    sink.set("render_dpi", String(Number(state.renderDpi)));
  }
  if (Number(state.pageChunkSize) > 0) {
    sink.set("pdf_page_chunk_size", String(Number(state.pageChunkSize)));
  }
  if (Number(state.cropHeaderRatio) > 0 && Number(state.cropHeaderRatio) <= 0.2) {
    sink.set("crop_header_ratio", String(Number(state.cropHeaderRatio)));
  }
  if (Number(state.cropFooterRatio) > 0 && Number(state.cropFooterRatio) <= 0.2) {
    sink.set("crop_footer_ratio", String(Number(state.cropFooterRatio)));
  }
}
