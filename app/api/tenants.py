"""API routes for tenants, plans, and subscriptions."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.database import get_db_session
from app.models import Tenant, Plan, Subscription, PlanType, SubscriptionStatus
from app.schemas import (
    TenantCreate,
    TenantResponse,
    PlanResponse,
    SubscriptionResponse,
)
from typing import List


router = APIRouter(prefix="/tenants", tags=["tenants"])


@router.post("", response_model=TenantResponse, status_code=status.HTTP_201_CREATED)
async def create_tenant(
    tenant_data: TenantCreate,
    session: AsyncSession = Depends(get_db_session),
) -> TenantResponse:
    """Create a new tenant with a free plan subscription."""
    # Create tenant
    tenant = Tenant(name=tenant_data.name)
    session.add(tenant)
    await session.flush()

    # Get free plan
    free_plan_stmt = select(Plan).where(Plan.name == "free")
    free_plan_result = await session.execute(free_plan_stmt)
    free_plan = free_plan_result.scalar_one_or_none()
    
    if not free_plan:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Free plan not configured",
        )

    # Create subscription
    subscription = Subscription(
        tenant_id=tenant.id,
        plan_id=free_plan.id,
        stripe_status=SubscriptionStatus.ACTIVE,
    )
    session.add(subscription)
    await session.commit()
    await session.refresh(tenant)

    return tenant


@router.get("", response_model=List[TenantResponse])
async def list_tenants(
    session: AsyncSession = Depends(get_db_session),
) -> List[TenantResponse]:
    """List all tenants."""
    stmt = select(Tenant).order_by(Tenant.created_at.desc())
    result = await session.execute(stmt)
    tenants = result.scalars().all()
    return tenants


@router.get("/{tenant_id}", response_model=TenantResponse)
async def get_tenant(
    tenant_id: int,
    session: AsyncSession = Depends(get_db_session),
) -> TenantResponse:
    """Get a tenant by ID."""
    stmt = select(Tenant).where(Tenant.id == tenant_id)
    result = await session.execute(stmt)
    tenant = result.scalar_one_or_none()
    
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found",
        )
    
    return tenant


# Plan routes
plan_router = APIRouter(prefix="/plans", tags=["plans"])


@plan_router.get("", response_model=List[PlanResponse])
async def list_plans(
    session: AsyncSession = Depends(get_db_session),
) -> List[PlanResponse]:
    """List all available plans."""
    stmt = select(Plan).order_by(Plan.id)
    result = await session.execute(stmt)
    plans = result.scalars().all()
    return plans


@plan_router.get("/{plan_name}", response_model=PlanResponse)
async def get_plan(
    plan_name: str,
    session: AsyncSession = Depends(get_db_session),
) -> PlanResponse:
    """Get a plan by name."""
    stmt = select(Plan).where(Plan.name == plan_name)
    result = await session.execute(stmt)
    plan = result.scalar_one_or_none()
    
    if not plan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Plan not found",
        )
    
    return plan


# Subscription routes
subscription_router = APIRouter(prefix="/subscriptions", tags=["subscriptions"])


@subscription_router.get("/tenant/{tenant_id}", response_model=SubscriptionResponse)
async def get_subscription(
    tenant_id: int,
    session: AsyncSession = Depends(get_db_session),
) -> SubscriptionResponse:
    """Get subscription for a tenant."""
    stmt = select(Subscription).where(Subscription.tenant_id == tenant_id)
    result = await session.execute(stmt)
    subscription = result.scalar_one_or_none()
    
    if not subscription:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Subscription not found",
        )
    
    return subscription