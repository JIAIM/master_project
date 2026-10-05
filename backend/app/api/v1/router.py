from fastapi import APIRouter

from app.api.v1 import auth, materials, play, questions, sessions, tests

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router)
api_router.include_router(materials.router)
api_router.include_router(tests.router)
api_router.include_router(questions.router)
api_router.include_router(sessions.router)
api_router.include_router(play.router)
