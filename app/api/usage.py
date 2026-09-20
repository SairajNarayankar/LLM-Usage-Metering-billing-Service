"""API routes for usage metering, quota enforcement, and billing."""
from fastapi import APIRouter, Depends, HTTPException, status, Header, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timezone
from typing import Optional
from app.db.database import get_db_session
from app.models import Tenant, UsageEvent, UsageType, Plan
from app.schemas import (
    UsageRecordRequest,
    UsageRecordResponse,
    QuotaCheckResponse,
    UsageRollupResponse,
    GenerateRequest,
    GenerateResponse,
    TokenUsageSimulated,
    CheckoutSessionRequest,
    CheckoutSessionResponse,
    WebhookEventResponse,
)
from app.services.metering import MeteringService, get_metering_service
from app.services.quota import QuotaService, get_quota_service
from app.services.stripe_service import StripeService, get_stripe_service
from app.services.pricing import pricing_calculator
import uuid


router = APIRouter(prefix="/usage", tags=["usage"])


@router.post("/record", response_model=UsageRecordResponse)
async def record_usage(
    request: UsageRecordRequest,
    tenant_id: int,
    metering_service: MeteringService = Depends(get_metering_service),
) -> UsageRecordResponse:
    """
    Record a usage event with idempotency.
    
    The idempotency_key ensures exactly-once recording even under retries.
    """
    # Verify tenant exists
    stmt = select(Tenant).where(Tenant.id == tenant_id)
    result = await metering_service.session.execute(stmt)
    tenant = result.scalar_one_or_none()
    
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found",
        )

    result = await metering_service.record_usage(tenant_id, request)

    return UsageRecordResponse(
        usage_event_id=result.usage_event.id,
        tenant_id=tenant_id,
        usage_type=result.usage_event.usage_type.value,
        quantity=result.usage_event.quantity,
        cost_cents=result.cost_cents,
        created_at=result.usage_event.created_at,
        idempotency_key=result.usage_event.idempotency_key,
        is_duplicate=result.is_duplicate,
    )


@router.get("/quota/check", response_model=QuotaCheckResponse)
async def check_quota(
    tenant_id: int,
    usage_type: str,
    quantity: int = 1,
    quota_service: QuotaService = Depends(get_quota_service),
) -> QuotaCheckResponse:
    """
    Check if tenant has quota for the requested usage.
    
    Returns 429 if quota exceeded, 402 if plan doesn't allow, 200 if allowed.
    """
    try:
        utype = UsageType(usage_type)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid usage_type: {usage_type}",
        )

    result = await quota_service.check_quota(tenant_id, utype, quantity)

    if result.status_code == 429:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=result.message,
            headers={"Retry-After": str(result.retry_after_seconds)} if result.retry_after_seconds else None,
        )
    elif result.status_code == 402:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=result.message,
        )
    elif result.status_code == 404:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=result.message,
        )

    return QuotaCheckResponse(
        allowed=result.allowed,
        current_usage=result.current_usage,
        limit=result.limit,
        remaining=result.remaining,
        usage_type=result.usage_type.value,
        retry_after_seconds=result.retry_after_seconds,
        message=result.message,
    )


@router.get("/rollup", response_model=UsageRollupResponse)
async def get_usage_rollup(
    tenant_id: int,
    period_start: Optional[str] = None,
    period_end: Optional[str] = None,
    metering_service: MeteringService = Depends(get_metering_service),
) -> UsageRollupResponse:
    """
    Get monthly usage rollup for a tenant.
    
    If period_start/period_end not provided, uses current billing period from subscription.
    """
    # Verify tenant exists
    stmt = select(Tenant).where(Tenant.id == tenant_id)
    result = await metering_service.session.execute(stmt)
    tenant = result.scalar_one_or_none()
    
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found",
        )

    # Determine period from subscription if not provided
    if not period_start or not period_end:
        if tenant.subscription and tenant.subscription.stripe_current_period_start:
            period_start = period_start or tenant.subscription.stripe_current_period_start.isoformat()
            period_end = period_end or tenant.subscription.stripe_current_period_end.isoformat()
        else:
            # Default to current calendar month
            now = datetime.now(timezone.utc)
            period_start = period_start or datetime(now.year, now.month, 1, tzinfo=timezone.utc).isoformat()
            if now.month == 12:
                period_end = period_end or datetime(now.year + 1, 1, 1, tzinfo=timezone.utc).isoformat()
            else:
                period_end = period_end or datetime(now.year, now.month + 1, 1, tzinfo=timezone.utc).isoformat()

    rollup = await metering_service.get_monthly_usage(tenant_id, period_start, period_end)

    return UsageRollupResponse(**rollup)


# Dummy billable endpoint - simulates AI generation
generate_router = APIRouter(prefix="/generate", tags=["generate"])


@generate_router.post("", response_model=GenerateResponse)
async def generate(
    request: GenerateRequest,
    tenant_id: int,
    quota_service: QuotaService = Depends(get_quota_service),
) -> GenerateResponse:
    """
    Dummy billable endpoint that simulates AI text generation.
    
    This endpoint:
    1. Checks quota for AI tokens
    2. Simulates token usage
    3. Records usage event with idempotency
    4. Returns generated text and cost
    """
    # Simulate token usage based on request
    # In reality, this would come from an actual LLM call
    prompt_tokens = min(len(request.prompt) // 4, 2000)  # Rough estimate
    cached_tokens = prompt_tokens // 3  # Simulate some cached tokens
    fresh_input = prompt_tokens - cached_tokens
    output_tokens = min(request.max_tokens, 1500)
    reasoning_tokens = output_tokens // 5  # Simulate reasoning tokens

    token_breakdown = TokenUsageSimulated(
        input_tokens=fresh_input,
        cached_input_tokens=cached_tokens,
        output_tokens=output_tokens,
        reasoning_tokens=reasoning_tokens,
    )

    total_tokens = token_breakdown.total_tokens

    # Check quota and record usage atomically
    quota_result, metering_result = await quota_service.check_and_record(
        tenant_id=tenant_id,
        usage_type=UsageType.AI_TOKENS,
        requested_quantity=total_tokens,
        idempotency_key=request.idempotency_key,
        token_breakdown=token_breakdown,
        metadata=f"generate:{request.prompt[:50]}",
    )

    if not quota_result.allowed:
        if quota_result.status_code == 429:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=quota_result.message,
                headers={"Retry-After": str(quota_result.retry_after_seconds)} if quota_result.retry_after_seconds else None,
            )
        elif quota_result.status_code == 402:
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail=quota_result.message,
            )
        else:
            raise HTTPException(
                status_code=quota_result.status_code,
                detail=quota_result.message,
            )

    # Calculate cost
    breakdown = pricing_calculator.calculate_token_cost(
        input_tokens=fresh_input,
        cached_input_tokens=cached_tokens,
        output_tokens=output_tokens,
        reasoning_tokens=reasoning_tokens,
    )
    cost_cents = breakdown.total_cost_cents

    # Simulate generated text
    generated_text = f"[Simulated AI response to: '{request.prompt[:50]}...'] This is a dummy response for metering demonstration. Tokens used: {total_tokens}"

    return GenerateResponse(
        generated_text=generated_text,
        token_usage=token_breakdown,
        usage_event_id=metering_result.usage_event.id,
        cost_cents=cost_cents,
        quota_remaining=QuotaCheckResponse(
            allowed=True,
            current_usage=quota_result.current_usage + total_tokens,
            limit=quota_result.limit,
            remaining=quota_result.remaining,
            usage_type="ai_tokens",
            retry_after_seconds=None,
            message=None,
        ),
    )


# Billing/Stripe routes
billing_router = APIRouter(prefix="/billing", tags=["billing"])


@billing_router.post("/checkout", response_model=CheckoutSessionResponse)
async def create_checkout(
    request: CheckoutSessionRequest,
    stripe_service: StripeService = Depends(get_stripe_service),
) -> CheckoutSessionResponse:
    """Create a Stripe Checkout session for plan upgrade."""
    result = await stripe_service.create_checkout_session(
        tenant_id=request.tenant_id,
        plan_name=request.plan_name,
        success_url=request.success_url,
        cancel_url=request.cancel_url,
    )
    return CheckoutSessionResponse(
        checkout_url=result.checkout_url,
        session_id=result.session_id,
    )


@billing_router.post("/webhooks/stripe", response_model=WebhookEventResponse)
async def stripe_webhook(
    request: Request,
    stripe_service: StripeService = Depends(get_stripe_service),
) -> WebhookEventResponse:
    """
    Handle Stripe webhook events.
    
    Verifies signature, deduplicates, and updates subscription state.
    """
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")
    
    if not sig_header:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing stripe-signature header",
        )

    result = await stripe_service.handle_webhook(payload, sig_header)

    if not result.processed and "Invalid signature" in result.message:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result.message,
        )

    return WebhookEventResponse(
        received=True,
        event_type=result.event_type,
        processed=result.processed,
        message=result.message,
    )


@billing_router.get("/success")
async def billing_success(session_id: str):
    """Success page after Stripe Checkout."""
    return {"message": "Checkout successful", "session_id": session_id}


@billing_router.get("/cancel")
async def billing_cancel():
    """Cancel page after Stripe Checkout."""
    return {"message": "Checkout cancelled"}