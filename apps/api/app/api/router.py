from fastapi import APIRouter

from app.api.routes.auth import router as auth_router
from app.api.routes.knowledge import router as knowledge_router
from app.api.routes.learning import router as learning_router
from app.api.routes.paper_review import router as paper_review_router
from app.api.routes.papers import router as papers_router
from app.api.routes.question_bank import router as question_bank_router
from app.api.routes.system import router as system_router


api_router = APIRouter()
api_router.include_router(system_router)
api_router.include_router(auth_router)
api_router.include_router(knowledge_router)
api_router.include_router(papers_router)
api_router.include_router(paper_review_router)
api_router.include_router(question_bank_router)
api_router.include_router(learning_router)
