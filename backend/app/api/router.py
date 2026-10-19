from fastapi import APIRouter

from backend.app.api.health import router as health_router
from backend.app.domains.auth.router import router as auth_router
from backend.app.domains.characters.router import router as characters_router
from backend.app.domains.conversation.router import router as conversation_router
from backend.app.domains.documents.router import router as documents_router
from backend.app.domains.memory.router import router as memory_router
from backend.app.domains.retrieval.router import router as retrieval_router
from backend.app.domains.settings.router import router as settings_router
from backend.app.domains.workflow.router import router as workflow_router
from backend.app.domains.knowledge.router import router as knowledge_router

# Flat `/api/v1` namespace preserved for the existing frontend client.
router = APIRouter(prefix="/api/v1")
router.include_router(health_router, tags=["health"])
router.include_router(auth_router, prefix="/auth", tags=["auth"])
router.include_router(settings_router, prefix="/settings", tags=["settings"])
router.include_router(documents_router, tags=["documents"])
router.include_router(workflow_router, tags=["workflow"])
router.include_router(characters_router, tags=["characters"])
router.include_router(conversation_router, tags=["conversation"])
router.include_router(memory_router, tags=["memory"])
router.include_router(retrieval_router, tags=["retrieval"])
router.include_router(knowledge_router, tags=["knowledge"])
