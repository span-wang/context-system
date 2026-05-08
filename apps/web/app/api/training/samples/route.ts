import { NextResponse } from "next/server";

import { NextRequest } from "next/server";

import { listTrainingSamples, readTrainingSample, saveTrainingSampleGold } from "../../../../lib/training-dataset";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest) {
  try {
    const sampleId = request.nextUrl.searchParams.get("sample_id") || "";
    if (sampleId) {
      const detail = await readTrainingSample(sampleId);
      return NextResponse.json(detail);
    }
    const payload = await listTrainingSamples();
    return NextResponse.json(payload);
  } catch (error) {
    const message = error instanceof Error ? error.message : "读取训练样本失败";
    return NextResponse.json({ detail: message }, { status: 500 });
  }
}

export async function PUT(request: NextRequest) {
  try {
    const sampleId = request.nextUrl.searchParams.get("sample_id") || "";
    if (!sampleId) {
      return NextResponse.json({ detail: "sample_id 不能为空" }, { status: 422 });
    }
    const payload = (await request.json()) as { gold_text?: unknown };
    const goldText = typeof payload.gold_text === "string" ? payload.gold_text : "";
    if (!goldText.trim()) {
      return NextResponse.json({ detail: "gold_text 不能为空" }, { status: 422 });
    }
    const result = await saveTrainingSampleGold(sampleId, goldText);
    return NextResponse.json(result);
  } catch (error) {
    const message = error instanceof Error ? error.message : "保存训练样本失败";
    return NextResponse.json({ detail: message }, { status: 500 });
  }
}
