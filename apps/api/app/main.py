from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import get_settings
from app.db.bootstrap import initialize_database
from app.middleware.audit import FailedRequestAuditMiddleware


settings = get_settings()

app = FastAPI(
    title=settings.app.name,
    version=settings.app.version,
    summary="Professional education analysis platform backend",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.app.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(FailedRequestAuditMiddleware)

app.include_router(api_router)


@app.on_event("startup")
def on_startup() -> None:
    initialize_database()
