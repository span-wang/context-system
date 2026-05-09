import { NextResponse } from "next/server";
import { promises as fs } from "fs";
import path from "path";

import { NextRequest } from "next/server";

import {
  deleteTrainingSample,
  listTrainingSamples,
  readTrainingSample,
  saveTrainingSampleGold,
} from "../../../../lib/training-dataset";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest) {
  try {
    const sampleId = request.nextUrl.searchParams.get("sample_id") || "";
    const imagePath = request.nextUrl.searchParams.get("image_path") || "";
    if (sampleId && imagePath) {
      const root = path.resolve(process.cwd(), "..", "..", "data", "paper_parser_dataset");
      const samplePath = path.resolve(root, sampleId);
      const relative = path.relative(root, samplePath);
      if (relative.startsWith("..") || path.isAbsolute(relative)) {
        return NextResponse.json({ detail: "invalid sample id" }, { status: 400 });
      }
      const normalizedImagePath = imagePath.replace(/\\/g, "/").replace(/^\/+/, "");
      const filePath = path.resolve(samplePath, normalizedImagePath);
      const imageRelative = path.relative(samplePath, filePath);
      if (imageRelative.startsWith("..") || path.isAbsolute(imageRelative)) {
        return NextResponse.json({ detail: "invalid image path" }, { status: 400 });
      }
      const raw = await fs.readFile(filePath);
      const contentType = imageMimeType(filePath);
      return new NextResponse(raw, {
        headers: {
          "Content-Type": contentType,
          "Cache-Control": "public, max-age=3600",
        },
      });
    }
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

export async function DELETE(request: NextRequest) {
  try {
    const sampleId = request.nextUrl.searchParams.get("sample_id") || "";
    if (!sampleId) {
      return NextResponse.json({ detail: "sample_id 不能为空" }, { status: 422 });
    }
    const result = await deleteTrainingSample(sampleId);
    return NextResponse.json(result);
  } catch (error) {
    const message = error instanceof Error ? error.message : "删除训练样本失败";
    return NextResponse.json({ detail: message }, { status: 500 });
  }
}

function imageMimeType(filePath: string): string {
  const suffix = path.extname(filePath).toLowerCase();
  if (suffix === ".png") return "image/png";
  if (suffix === ".webp") return "image/webp";
  if (suffix === ".gif") return "image/gif";
  if (suffix === ".bmp") return "image/bmp";
  if (suffix === ".svg") return "image/svg+xml";
  return "image/jpeg";
}
