from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from deps import get_db, get_storage
from routers import generate_router, history_router, library_router, system_router
from settings import get_settings


settings = get_settings()
app = FastAPI(title=settings.app.name, version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3001",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(library_router)
app.include_router(generate_router)
app.include_router(history_router)
app.include_router(system_router)


@app.on_event("startup")
async def startup() -> None:
    get_db()
    get_storage()
