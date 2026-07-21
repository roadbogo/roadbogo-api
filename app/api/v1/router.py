from fastapi import APIRouter

from app.api.v1 import auth, cctvs, dispatches, health, incidents, responders

api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(auth.router)
api_router.include_router(incidents.router)
api_router.include_router(cctvs.router)
api_router.include_router(responders.router)
api_router.include_router(dispatches.router)
