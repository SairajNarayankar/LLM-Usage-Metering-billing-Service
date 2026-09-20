"""API router aggregation."""
from fastapi import APIRouter
from app.api import tenants, usage

api_router = APIRouter()

# Include all routers
api_router.include_router(tenants.router)
api_router.include_router(tenants.plan_router)
api_router.include_router(tenants.subscription_router)
api_router.include_router(usage.router)
api_router.include_router(usage.generate_router)
api_router.include_router(usage.billing_router)