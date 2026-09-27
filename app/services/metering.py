"""Idempotent usage metering service."""
from dataclasses import dataclass
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
from app.models import Tenant, UsageEvent, UsageType, Plan, Subscription
from app.schemas import UsageRecordRequest, UsageRecordResponse, TokenBreakdown
from app.services.pricing import pricing_calculator, TokenCostBreakdown
from app.db.database import db

@dataclass
class MeteringResult:
    """Result of a metering operation."""
    usage_event: UsageEvent
    is_duplicate: bool
    cost_cents: int


class MeteringService:
    """
    Service for recording usage events with idempotency guarantees.
    
    The idempotency key ensures that retried requests create exactly one usage event.
    The unique constraint on (tenant_id, idempotency_key) enforces this at the database level.
    """

    def __init__(self, session: AsyncSession):
        self.session = session

    async def record_usage(
        self,
        tenant_id: int,
        request: UsageRecordRequest,
    ) -> MeteringResult:
        """
        Record a usage event with idempotency.
        
        If a record with the same tenant_id and idempotency_key already exists,
        return the existing record (no new event created).
        """
        # Calculate cost based on usage type
        cost_cents = await self._calculate_cost(request)

        # Try to create the usage event
        usage_event = UsageEvent(
            tenant_id=tenant_id,
            usage_type=UsageType(request.usage_type),
            quantity=request.quantity,
            input_tokens=request.token_breakdown.input_tokens if request.token_breakdown else 0,
            cached_input_tokens=request.token_breakdown.cached_input_tokens if request.token_breakdown else 0,
            output_tokens=request.token_breakdown.output_tokens if request.token_breakdown else 0,
            reasoning_tokens=request.token_breakdown.reasoning_tokens if request.token_breakdown else 0,
            idempotency_key=request.idempotency_key,
            cost_cents=cost_cents,
            request_metadata=request.metadata,
        )

        self.session.add(usage_event)

        try:
            await self.session.flush()
            # Success - new event created
            return MeteringResult(
                usage_event=usage_event,
                is_duplicate=False,
                cost_cents=cost_cents,
            )
        except IntegrityError as e:
            # Duplicate idempotency key - rollback and fetch existing
            await self.session.rollback()
            
            # Fetch the existing event
            stmt = select(UsageEvent).where(
                UsageEvent.tenant_id == tenant_id,
                UsageEvent.idempotency_key == request.idempotency_key,
            )
            result = await self.session.execute(stmt)
            existing_event = result.scalar_one_or_none()
            
            if existing_event is None:
                # This shouldn't happen, but handle gracefully
                raise RuntimeError("IntegrityError but no existing event found") from e
            
            return MeteringResult(
                usage_event=existing_event,
                is_duplicate=True,
                cost_cents=existing_event.cost_cents,
            )

    async def _calculate_cost(self, request: UsageRecordRequest) -> int:
        """Calculate cost for a usage request."""
        if request.usage_type == "api_call":
            return pricing_calculator.calculate_api_call_cost(request.quantity)
        
        elif request.usage_type == "ai_tokens":
            if request.token_breakdown is None:
                # If no breakdown provided, treat all as input tokens (conservative)
                breakdown = pricing_calculator.calculate_token_cost(
                    input_tokens=request.quantity,
                )
            else:
                tb = request.token_breakdown
                breakdown = pricing_calculator.calculate_token_cost(
                    input_tokens=tb.input_tokens,
                    cached_input_tokens=tb.cached_input_tokens,
                    output_tokens=tb.output_tokens,
                    reasoning_tokens=tb.reasoning_tokens,
                )
            return breakdown.total_cost_cents
        
        else:
            raise ValueError(f"Unknown usage type: {request.usage_type}")

    async def get_monthly_usage(
        self,
        tenant_id: int,
        period_start: str,  # ISO format date string
        period_end: str,
    ) -> dict:
        """Get monthly usage rollup for a tenant."""
        # Get tenant's plan for limits (eagerly loaded to avoid MissingGreenlet)
        from sqlalchemy.orm import selectinload
        from datetime import datetime
        tenant_stmt = select(Tenant).where(Tenant.id == tenant_id).options(
            selectinload(Tenant.subscription).selectinload(Subscription.plan)
        )
        tenant_result = await self.session.execute(tenant_stmt)
        tenant = tenant_result.scalar_one_or_none()
        
        if not tenant or not tenant.subscription or not tenant.subscription.plan:
            raise ValueError("Tenant or subscription not found")
        
        plan = tenant.subscription.plan

        # Parse ISO format strings to datetime objects
        period_start_dt = datetime.fromisoformat(period_start.replace('Z', '+00:00'))
        period_end_dt = datetime.fromisoformat(period_end.replace('Z', '+00:00'))

        # Query usage events for the period
        stmt = select(
            UsageEvent.usage_type,
            func.sum(UsageEvent.quantity).label("total_quantity"),
            func.sum(UsageEvent.cost_cents).label("total_cost"),
        ).where(
            UsageEvent.tenant_id == tenant_id,
            UsageEvent.created_at >= period_start_dt,
            UsageEvent.created_at < period_end_dt,
        ).group_by(UsageEvent.usage_type)

        result = await self.session.execute(stmt)
        rows = result.all()

        usage_by_type = {row.usage_type: {"quantity": row.total_quantity, "cost": row.total_cost} for row in rows}

        api_calls_used = usage_by_type.get(UsageType.API_CALL, {}).get("quantity", 0) or 0
        api_calls_cost = usage_by_type.get(UsageType.API_CALL, {}).get("cost", 0) or 0
        ai_tokens_used = usage_by_type.get(UsageType.AI_TOKENS, {}).get("quantity", 0) or 0
        ai_tokens_cost = usage_by_type.get(UsageType.AI_TOKENS, {}).get("cost", 0) or 0

        return {
            "tenant_id": tenant_id,
            "period_start": period_start,
            "period_end": period_end,
            "plan_name": plan.name,
            "api_calls_used": api_calls_used,
            "api_calls_limit": plan.api_calls_limit,
            "ai_tokens_used": ai_tokens_used,
            "ai_tokens_limit": plan.ai_tokens_limit,
            "api_calls_cost_cents": api_calls_cost,
            "ai_tokens_cost_cents": ai_tokens_cost,
            "total_cost_cents": api_calls_cost + ai_tokens_cost,
        }


async def get_metering_service() -> MeteringService:
    """FastAPI dependency for metering service."""
    async with db.session() as session:
        yield MeteringService(session)