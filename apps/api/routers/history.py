from fastapi import APIRouter, HTTPException

from deps import get_db
from schemas.generation import GenerationJob


router = APIRouter(prefix="/api/history", tags=["history"])


@router.get("", response_model=list[GenerationJob])
def list_history() -> list[GenerationJob]:
    return get_db().list_jobs()


@router.delete("/{job_id}")
def delete_history(job_id: str) -> dict:
    if not get_db().delete_job(job_id):
        raise HTTPException(status_code=404, detail="generation job not found")
    return {"ok": True}

