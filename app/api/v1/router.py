from fastapi import APIRouter
from app.api.v1.auth import router as auth_router
from app.api.v1.caregiver import router as caregiver_router
from app.api.v1.elder import router as elder_router
from app.api.v1.medications import router as medications_router
from app.api.v1.adherence import router as adherence_router
from app.api.v1.routines import router as routines_router
from app.api.v1.directory import router as directory_router
from app.api.v1.sos import router as sos_router
from app.api.v1.welfare import router as welfare_router
from app.api.v1.websocket import router as ws_router
from app.api.v1.vitals import router as vitals_router
from app.api.v1.workouts import router as workouts_router

api_router = APIRouter()

api_router.include_router(auth_router)
api_router.include_router(caregiver_router)
api_router.include_router(elder_router)
api_router.include_router(medications_router)
api_router.include_router(adherence_router)
api_router.include_router(routines_router)
api_router.include_router(directory_router)
api_router.include_router(sos_router)
api_router.include_router(welfare_router)
api_router.include_router(ws_router)
api_router.include_router(vitals_router)
api_router.include_router(workouts_router)
