from fastapi import APIRouter

from app.api.v1 import chat, conversations, documents, health, whatsapp, workspaces

api_router = APIRouter()

# Mount v1 router hub (/api/v1/...)
v1_router = APIRouter(prefix="/v1")
v1_router.include_router(health.router, tags=["health"])
v1_router.include_router(workspaces.router)
v1_router.include_router(documents.router)
v1_router.include_router(conversations.router)
v1_router.include_router(chat.router)
v1_router.include_router(whatsapp.router)

api_router.include_router(v1_router)
api_router.include_router(health.router, tags=["health"])
