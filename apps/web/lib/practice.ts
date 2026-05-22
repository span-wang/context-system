import { PracticeQuestionSnapshotResponse } from "./pro-api";

export function questionTypeLabel(value: string) {
  const map: Record<string, string> = {
    single_choice: "单选题",
    multiple_choice: "多选题",
    judge: "判断题",
    fill_blank: "填空题",
    short_answer: "简答题",
    calculation: "计算题",
    case_analysis: "案例分析题",
    material_analysis: "材料分析题",
    mixed: "混合题型",
  };
  return map[value] || value;
}

export function sessionLabel(value: string) {
  const map: Record<string, string> = {
    chapter: "章节刷题",
    random: "乱序刷题",
    paper: "套卷刷题",
    wrong_book: "错题模式",
  };
  return map[value] || value;
}

export function modeLabel(value: string) {
  return value === "memorize" ? "背记模式" : value === "exam" ? "模拟模式" : value;
}

export function formatDuration(value: number | null | undefined) {
  if (!value) return "0 分钟";
  const minutes = Math.floor(value / 60);
  const seconds = value % 60;
  return `${minutes} 分 ${seconds} 秒`;
}

export function formatShortDuration(value: number | null | undefined) {
  if (!value) return "0 秒";
  if (value < 60) return `${value} 秒`;
  const minutes = Math.floor(value / 60);
  const seconds = value % 60;
  return seconds ? `${minutes} 分 ${seconds} 秒` : `${minutes} 分钟`;
}

export function formatPracticeAnswer(question: PracticeQuestionSnapshotResponse, answer: string | null | undefined) {
  const normalized = (answer || "").trim();
  if (!normalized) return "未作答";
  if (!isChoiceQuestion(question.question_type) || !question.options_json?.length) {
    return normalized;
  }
  const selectedKeys = extractChoiceKeys(normalized);
  if (!selectedKeys.length) {
    return normalized;
  }
  const optionMap = new Map(question.options_json.map((option, index) => [optionKey(option, index), option]));
  const lines = selectedKeys.map((key) => optionMap.get(key) || key);
  return lines.join("\n");
}

export function optionKey(option: string, index: number) {
  const match = option.trim().match(/^([A-Za-z])/);
  return match ? match[1].toUpperCase() : String(index + 1);
}

function isChoiceQuestion(questionType: string) {
  return questionType === "single_choice" || questionType === "multiple_choice" || questionType === "judge";
}

function extractChoiceKeys(value: string) {
  const tokens = value.toUpperCase().match(/[A-Z]/g) || [];
  return Array.from(new Set(tokens));
}
