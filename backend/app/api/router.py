from fastapi import APIRouter

from app.api import admin, auth, chat, documents, health, knowledge_bases, tasks, wiki, workspaces

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(workspaces.router)
api_router.include_router(knowledge_bases.router)
api_router.include_router(documents.router)
api_router.include_router(wiki.router)
api_router.include_router(chat.router)
api_router.include_router(tasks.router)
api_router.include_router(admin.router)

