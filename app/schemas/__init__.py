"""Pydantic schemas for API requests and responses."""
from datetime import datetime
from typing import Optional, Literal
from pydantic import BaseModel, Field, ConfigDict


# === Tenant Schemas ===
class TenantCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)


class TenantResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    stripe_customer_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime


# === Plan Schemas ===
class PlanResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    display_name: str
    api_calls_limit: int
    ai_tokens_limit: int
    monthly_price_cents: int


# === Subscription Schemas ===
class SubscriptionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: int
    plan_id: int
    stripe_subscription_id: Optional[str] = None
    stripe_status: str
    stripe_current_period_start: Optional[datetime] = None
    stripe_current_period_end: Optional[datetime] = None
    stripe_cancel_at_period_end: bool = False
    created_at: datetime
    updated_at: datetime


# === Usage Schemas ===
class TokenBreakdown(BaseModel):
    """AI token usage breakdown for a single request."""
    input_tokens: int = Field(default=0, ge=0)
    cached_input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    reasoning_tokens: int = Field(default=0, ge=0)

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.cached_input_tokens + self.output_tokens + self.reasoning_tokens


class UsageRecordRequest(BaseModel):
    """Request to record a usage event."""
    usage_type: Literal["api_call", "ai_tokens"]
    quantity: int = Field(..., ge=1)  # For api_call: 1; For ai_tokens: total token count
    token_breakdown: Optional[TokenBreakdown] = None
    idempotency_key: str = Field(..., min_length=1, max_length=255)
    metadata: Optional[str] = None


class UsageRecordResponse(BaseModel):
    """Response after recording usage."""
    usage_event_id: int
    tenant_id: int
    usage_type: str
    quantity: int
    cost_cents: int
    created_at: datetime
    idempotency_key: str
    is_duplicate: bool = False  # True if this request was a duplicate (returned existing event)


class QuotaCheckResponse(BaseModel):
    """Response from quota check before allowing an action."""
    allowed: bool
    current_usage: int
    limit: int
    remaining: int
    usage_type: str
    retry_after_seconds: Optional[int] = None
    message: Optional[str] = None


class UsageRollupResponse(BaseModel):
    """Monthly usage rollup for a tenant."""
    tenant_id: int
    period_start: datetime
    period_end: datetime
    plan_name: str
    api_calls_used: int
    api_calls_limit: int
    ai_tokens_used: int
    ai_tokens_limit: int
    api_calls_cost_cents: int
    ai_tokens_cost_cents: int
    total_cost_cents: int


# === Stripe Schemas ===
class CheckoutSessionRequest(BaseModel):
    """Request to create a Stripe Checkout session."""
    tenant_id: int
    plan_name: Literal["free", "pro"]
    success_url: str = Field(default="http://localhost:8000/billing/success")
    cancel_url: str = Field(default="http://localhost:8000/billing/cancel")


class CheckoutSessionResponse(BaseModel):
    checkout_url: str
    session_id: str


class WebhookEventResponse(BaseModel):
    """Response from webhook handler."""
    received: bool
    event_type: str
    processed: bool
    message: str


# === Billing/Generate Endpoint Schemas ===
class GenerateRequest(BaseModel):
    """Dummy billable endpoint request - simulates AI generation."""
    prompt: str = Field(..., min_length=1)
    max_tokens: int = Field(default=1000, ge=1, le=8192)
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    idempotency_key: str = Field(..., min_length=1, max_length=255)


class TokenUsageSimulated(BaseModel):
    """Simulated token usage from generation."""
    input_tokens: int
    cached_input_tokens: int
    output_tokens: int
    reasoning_tokens: int

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.cached_input_tokens + self.output_tokens + self.reasoning_tokens


class GenerateResponse(BaseModel):
    """Response from the dummy generate endpoint."""
    generated_text: str
    token_usage: TokenUsageSimulated
    usage_event_id: int
    cost_cents: int
    quota_remaining: QuotaCheckResponse
    is_duplicate: bool = False