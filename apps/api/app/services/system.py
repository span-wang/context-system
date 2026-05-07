from __future__ import annotations

import re
import subprocess

from app.core.config import get_settings
from app.db.bootstrap import get_migration_status
from app.schemas.common import HealthResponse
from app.schemas.system import OCRCapabilityResponse, PlatformSummary, SystemStatusResponse
from library.pdf_ocr_pipeline import _get_paddle_ocr_settings


class SystemService:
    def get_status(self) -> SystemStatusResponse:
        settings = get_settings()
        migration = get_migration_status()
        database_url = settings.db.url
        return SystemStatusResponse(
            health=HealthResponse(
                ok=True,
                name=settings.app.name,
                version=settings.app.version,
                environment=settings.app.environment,
            ),
            summary=PlatformSummary(
                current_phase="第一期：底座重构 + 专业版后台骨架",
                database_url=database_url,
                storage_type=settings.storage.type,
                mysql_ready=database_url.startswith("mysql"),
                database_type=str(migration["database_type"]),
                migration_target=str(migration["migration_target"]),
                auto_migrate=bool(migration["auto_migrate"]),
                seed_on_startup=bool(migration["seed_on_startup"]),
                alembic_current_revision=migration["current_revision"],
                alembic_head_revision=migration["head_revision"],
                migration_status=str(migration["status"]),
                migration_ready=bool(migration["migration_ready"]),
                database_ping_ok=bool(migration["database_ping_ok"]),
                module_status={
                    "auth": "skeleton-ready",
                    "papers": "seed-data-ready",
                    "questions": "seed-data-ready",
                    "knowledge": "seed-data-ready",
                    "analysis": "dashboard-ready",
                    "question_bank": "seed-data-ready",
                    "learning": "seed-data-ready",
                    "workflow": "report-link-ready",
                },
            ),
        )

    def get_ocr_capability(self) -> OCRCapabilityResponse:
        current_settings = _get_paddle_ocr_settings()
        gpu_info = _detect_nvidia_gpu()
        paddle_info = _detect_paddle()
        warnings: list[str] = []

        total_mb = gpu_info.get("memory_total_mb")
        free_mb = gpu_info.get("memory_free_mb")
        cuda_available = bool(paddle_info.get("cuda_available"))
        device_name = gpu_info.get("device_name")

        if not device_name:
            warnings.append("未检测到 NVIDIA GPU，当前高精度 OCR 会退化为 CPU 或初始化失败。")
        if total_mb is not None and total_mb < 12000:
            warnings.append("显存低于 12GB，不建议跑 PP-StructureV3 / 高 DPI server OCR。")
        if free_mb is not None and free_mb < 6000:
            warnings.append("当前空闲显存低于 6GB，建议关闭其他占用 GPU 的程序后再批量解析。")
        if not cuda_available:
            warnings.append("Paddle 当前未检测到 CUDA，可运行但速度和稳定性会明显受影响。")

        if not device_name or (total_mb is not None and total_mb < 8000) or not cuda_available:
            status = "fail"
            summary = "当前环境不适合稳定运行高精度扫描试卷 OCR。"
        elif warnings:
            status = "warn"
            summary = "当前环境可运行高精度 OCR，但建议按提示释放显存或降低并发。"
        else:
            status = "ok"
            summary = "4070 Ti SUPER 16GB 级别显存适合本项目的 PP-OCRv5 server 高精度试卷 OCR。"

        current_models = [
            str(current_settings.get("text_detection_model_name") or ""),
            str(current_settings.get("text_recognition_model_name") or ""),
        ]
        structure_ready = all("server" in model for model in current_models)
        vl_available = _detect_paddleocr_vl()
        return OCRCapabilityResponse(
            status=status,
            summary=summary,
            device_name=device_name,
            gpu_memory_total_mb=total_mb,
            gpu_memory_free_mb=free_mb,
            cuda_available=cuda_available,
            paddle_version=paddle_info.get("paddle_version"),
            paddle_cuda_device_count=paddle_info.get("cuda_device_count"),
            recommended_pipeline="PP-OCRv5 server + PP-StructureV3 layout; PaddleOCR-VL 仅用于低置信复杂页兜底",
            current_settings=current_settings,
            warnings=warnings,
            checks={
                "nvidia_smi_ok": bool(gpu_info.get("ok")),
                "paddle_import_ok": bool(paddle_info.get("ok")),
                "recommended_min_vram_mb": 12000,
                "recommended_free_vram_mb": 6000,
                "pp_structure_v3_ready": structure_ready,
                "paddleocr_vl_available": vl_available,
                "paddleocr_vl_mode": "available_fallback" if vl_available else "reserved_fallback",
            },
        )


def _detect_nvidia_gpu() -> dict[str, object]:
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,memory.total,memory.free",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            check=False,
            text=True,
            timeout=5,
        )
    except Exception as exc:
        return {"ok": False, "error": str(exc)}

    if result.returncode != 0 or not result.stdout.strip():
        return {"ok": False, "error": (result.stderr or result.stdout).strip()}

    line = result.stdout.strip().splitlines()[0]
    parts = [part.strip() for part in line.split(",")]
    if len(parts) < 3:
        return {"ok": False, "error": f"无法解析 nvidia-smi 输出：{line}"}
    return {
        "ok": True,
        "device_name": parts[0],
        "memory_total_mb": _safe_int(parts[1]),
        "memory_free_mb": _safe_int(parts[2]),
    }


def _detect_paddle() -> dict[str, object]:
    try:
        import paddle
    except Exception as exc:
        return {"ok": False, "cuda_available": False, "error": str(exc)}

    cuda_available = False
    cuda_device_count: int | None = None
    try:
        cuda_available = bool(paddle.device.is_compiled_with_cuda())
        if cuda_available:
            cuda_device_count = int(paddle.device.cuda.device_count())
    except Exception:
        cuda_device_count = None
    return {
        "ok": True,
        "cuda_available": cuda_available,
        "cuda_device_count": cuda_device_count,
        "paddle_version": getattr(paddle, "__version__", None),
    }


def _detect_paddleocr_vl() -> bool:
    try:
        from paddleocr import PaddleOCRVL  # noqa: F401
    except Exception:
        return False
    return True


def _safe_int(value: object) -> int | None:
    match = re.search(r"\d+", str(value))
    if not match:
        return None
    return int(match.group(0))
