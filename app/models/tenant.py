"""Tenant and Plan models."""
import enum
from datetime import datetime
from sqlalchemy import (
    Column,
    String,
    Integer,
    BigInteger,
    DateTime,
    Enum,
    ForeignKey,
    UniqueConstraint,
    Index,
    func,
)
from sqlalchemy.orm import relationship
from app.db.database import Base


class PlanType(str, enum.Enum):
    """Subscription plan types."""
    FREE = "free"
    PRO = "pro"


class SubscriptionStatus(str, enum.Enum):
    """Stripe subscription statuses."""
    ACTIVE = "active"
    PAST_DUE = "past_due"
    CANCELED = "canceled"
    INCOMPLETE = "incomplete"
    INCOMPLETE_EXPIRED = "incomplete_expired"
    TRIALING = "trialing"
    UNPAID = "unpaid"
    PAUSED = "paused"


class Tenant(Base):
    """Tenant (customer organization) model."""

    __tablename__ = "tenants"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    stripe_customer_id = Column(String(255), unique=True, nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    subscription = relationship("Subscription", back_populates="tenant", uselist=False)
    usage_events = relationship("UsageEvent", back_populates="tenant", lazy="dynamic")

    def __repr__(self) -> str:
        return f"<Tenant(id={self.id}, name='{self.name}')>"


class Plan(Base):
    """Subscription plan with quotas."""

    __tablename__ = "plans"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    name = Column(String(50), unique=True, nullable=False)  # free, pro
    display_name = Column(String(100), nullable=False)
    stripe_price_id = Column(String(255), unique=True, nullable=True)

    # Quotas (monthly)
    api_calls_limit = Column(Integer, nullable=False, default=0)
    ai_tokens_limit = Column(Integer, nullable=False, default=0)

    # Pricing
    monthly_price_cents = Column(Integer, nullable=False, default=0)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    subscriptions = relationship("Subscription", back_populates="plan")

    def __repr__(self) -> str:
        return f"<Plan(name='{self.name}', api_calls={self.api_calls_limit}, tokens={self.ai_tokens_limit})>"


class Subscription(Base):
    """Tenant subscription linking to a plan."""

    __tablename__ = "subscriptions"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id = Column(BigInteger, ForeignKey("tenants.id", ondelete="CASCADE"), unique=True, nullable=False)
    plan_id = Column(BigInteger, ForeignKey("plans.id", ondelete="RESTRICT"), nullable=False)

    # Stripe fields
    stripe_subscription_id = Column(String(255), unique=True, nullable=True, index=True)
    stripe_status = Column(Enum(SubscriptionStatus), nullable=False, default=SubscriptionStatus.INCOMPLETE)
    stripe_current_period_start = Column(DateTime(timezone=True), nullable=True)
    stripe_current_period_end = Column(DateTime(timezone=True), nullable=True)
    stripe_cancel_at_period_end = Column(Integer, nullable=False, default=0)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    tenant = relationship("Tenant", back_populates="subscription")
    plan = relationship("Plan", back_populates="subscriptions")

    # Constraints
    __table_args__ = (
        Index("ix_subscriptions_tenant_plan", "tenant_id", "plan_id"),
    )

    def __repr__(self) -> str:
        return f"<Subscription(tenant_id={self.tenant_id}, plan_id={self.plan_id}, status={self.stripe_status})>"