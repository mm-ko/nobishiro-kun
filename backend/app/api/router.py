from fastapi import APIRouter

from app.features.auth.router import router as auth_router
from app.features.health.router import router as health_router
from app.features.learning_history.router import router as learning_history_router
from app.features.payment.router import router as payment_router
from app.features.test_analysis.router import router as test_analysis_router
from app.features.usage.router import router as usage_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(auth_router)
api_router.include_router(test_analysis_router)
api_router.include_router(learning_history_router)
api_router.include_router(usage_router)
api_router.include_router(payment_router)
