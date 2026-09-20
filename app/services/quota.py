"""Quota enforcement service."""
from dataclasses import dataclass
from datetime import datetime, timezone
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import Tenant, UsageEvent, UsageType, Plan, Subscription
from app.schemas import QuotaCheckResponse


@dataclass
class QuotaCheckResult:
    """Result of a quota check."""
    allowed: bool
    current_usage: int
    limit: int
    remaining: int
    usage_type: UsageType
    retry_after_seconds: int | None
    message: str | None
    status_code: int  # 200, 429, or 402


class QuotaService:
    """
    Service for enforcing usage quotas.
    
    Checks current usage against plan limits before allowing billable actions.
    Returns appropriate status codes:
    - 200: Allowed
    - 429: Usage quota exceeded (rate limit style)
    - 402: Payment required (plan doesn't allow this feature, upgrade needed)
    """

    def __init__(self, session: AsyncSession):
        self.session = session

    async def check_quota(
        self,
        tenant_id: int,
        usage_type: UsageType,
        requested_quantity: int = 1,
    ) -> QuotaCheckResult:
        """
        Check if tenant has quota for the requested usage.
        
        Args:
            tenant_id: The tenant to check
            usage_type: Type of usage (API_CALL or AI_TOKENS)
            requested_quantity: Amount of usage being requested
            
        Returns:
            QuotaCheckResult with allowance decision and details
        """
        # Get tenant with subscription and plan
        stmt = select(Tenant).where(Tenant.id == tenant_id)
        result = await self.session.execute(stmt)
        tenant = result.scalar_one_or_none()
        
        if not tenant:
            return QuotaCheckResult(
                allowed=False,
                current_usage=0,
                limit=0,
                remaining=0,
                usage_type=usage_type,
                retry_after_seconds=None,
                message="Tenant not found",
                status_code=404,
            )

        if not tenant.subscription or not tenant.subscription.plan:
            return QuotaCheckResult(
                allowed=False,
                current_usage=0,
                limit=0,
                remaining=0,
                usage_type=usage_type,
                retry_after_seconds=None,
                message="No active subscription",
                status_code=402,
            )

        plan = tenant.subscription.plan
        
        # Check if subscription is active
        if tenant.subscription.stripe_status not in ("active", "trialing"):
            return QuotaCheckResult(
                allowed=False,
                current_usage=0,
                limit=0,
                remaining=0,
                usage_type=usage_type,
                retry_after_seconds=None,
                message=f"Subscription status '{tenant.subscription.stripe_status}' requires payment",
                status_code=402,
            )

        # Get plan limit for this usage type
        if usage_type == UsageType.API_CALL:
            limit = plan.api_calls_limit
        else:
            limit = plan.ai_tokens_limit

        # Free plan with zero limit means feature not available
        if limit == 0:
            return QuotaCheckResult(
                allowed=False,
                current_usage=0,
                limit=0,
                remaining=0,
                usage_type=usage_type,
                retry_after_seconds=None,
                message=f"{usage_type.value} not available on {plan.name} plan. Upgrade to Pro.",
                status_code=402,
            )

        # Calculate current usage for current billing period
        # Use subscription period if available, otherwise current calendar month
        period_start = tenant.subscription.stripe_current_period_start
        if period_start is None:
            # Fallback to first day of current month
            now = datetime.now(timezone.utc)
            period_start = datetime(now.year, now.month, 1, tzinfo=timezone.utc)

        # Query current usage
        usage_stmt = select(func.coalesce(func.sum(UsageEvent.quantity), 0)).where(
            and_(
                UsageEvent.tenant_id == tenant_id,
                UsageEvent.usage_type == usage_type,
                UsageEvent.created_at >= period_start,
            )
        )
        usage_result = await self.session.execute(usage_stmt)
        current_usage = usage_result.scalar() or 0

        remaining = max(0, limit - current_usage)
        would_exceed = (current_usage + requested_quantity) > limit

        if would_exceed:
            # Determine retry_after - seconds until period end
            period_end = tenant.subscription.stripe_current_period_end
            if period_end:
                retry_after = int((period_end - datetime.now(timezone.utc)).total_seconds())
                retry_after = max(1, retry_after)
            else:
                retry_after = 3600  # Default 1 hour

            return QuotaCheckResult(
                allowed=False,
                current_usage=current_usage,
                limit=limit,
                remaining=remaining,
                usage_type=usage_type,
                retry_after_seconds=retry_after,
                message=f"{usage_type.value} quota exceeded. Limit: {limit}, Used: {current_usage}",
                status_code=429,
            )

        return QuotaCheckResult(
            allowed=True,
            current_usage=current_usage,
            limit=limit,
            remaining=remaining - requested_quantity,
            usage_type=usage_type,
            retry_after_seconds=None,
            message=None,
            status_code=200,
        )

    async def check_and_record(
        self,
        tenant_id: int,
        usage_type: UsageType,
        requested_quantity: int,
        idempotency_key: str,
        token_breakdown=None,
        metadata=None,
    ) -> tuple[QuotaCheckResult, MeteringResult | None]:
        """
        Atomically check quota and record usage if allowed.
        
        This is the main entry point for billable endpoints.
        """
        from app.services.metering import MeteringService, MeteringResult
        from app.schemas import UsageRecordRequest
        
        # First check quota
        quota_result = await self.check_quota(tenant_id, usage_type, requested_quantity)
        
        if not quota_result.allowed:
            return quota_result, None
        
        # Quota allows - record usage
        metering_service = MeteringService(self.session)
        
        if usage_type == UsageType.API_CALL:
            record_request = UsageRecordRequest(
                usage_type="api_call",
                quantity=requested_quantity,
                idempotency_key=idempotency_key,
                metadata=metadata,
            )
        else:
            record_request = UsageRecordRequest(
                usage_type="ai_tokens",
                quantity=requested_quantity,
                token_breakdown=token_breakdown,
                idempotency_key=idempotency_key,
                metadata=metadata,
            )
        
        metering_result = await metering_service.record_usage(tenant_id, record_request)
        
        # Update quota result with post-recording remaining
        quota_result.remaining = max(0, quota_result.remaining - requested_quantity)
        
        return quota_result, metering_result


async def get_quota_service() -> QuotaService:
    """FastAPI dependency for quota service."""
    async with db.session() as session:
        yield QuotaService(session)