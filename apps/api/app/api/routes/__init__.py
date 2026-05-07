from .analysis import router as analysis_router
from .auth import router as auth_router
from .knowledge import router as knowledge_router
from .learning import router as learning_router
from .papers import router as papers_router
from .question_bank import router as question_bank_router
from .questions import router as questions_router
from .system import router as system_router
from .workflow import router as workflow_router

__all__ = [
    "analysis_router",
    "auth_router",
    "knowledge_router",
    "learning_router",
    "papers_router",
    "question_bank_router",
    "questions_router",
    "system_router",
    "workflow_router",
]
