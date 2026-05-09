from .auth import router as auth_router
from .knowledge import router as knowledge_router
from .paper_review import router as paper_review_router
from .papers import router as papers_router
from .system import router as system_router

__all__ = [
    "auth_router",
    "knowledge_router",
    "paper_review_router",
    "papers_router",
    "system_router",
]
