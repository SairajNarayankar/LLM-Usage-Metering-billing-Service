"""Usage event model with idempotency support."""
import enum
from datetime import datetime
from sqlalchemy import (
    Column,
    BigInteger,
    String,
    Integer,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    func,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship
from app.db.database import Base


class UsageType(str, enum.Enum):
    """Types of billable usage."""
    API_CALL = "api_call"
    AI_TOKENS = "ai_tokens"


class TokenCategory(str, enum.Enum):
    """AI token categories for pricing."""
    INPUT = "input"
    CACHED_INPUT = "cached_input"
    OUTPUT = "output"
    REASONING = "reasoning"


class UsageEvent(Base):
    """Immutable usage event record with idempotency key."""

    __tablename__ = "usage_events"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id = Column(BigInteger, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)

    # Usage details
    usage_type = Column(Enum(UsageType), nullable=False, index=True)
    quantity = Column(Integer, nullable=False)  # For API calls: count; For tokens: token count

    # AI Token breakdown (only used when usage_type=AI_TOKENS)
    input_tokens = Column(Integer, nullable=True, default=0)
    cached_input_tokens = Column(Integer, nullable=True, default=0)
    output_tokens = Column(Integer, nullable=True, default=0)
    reasoning_tokens = Column(Integer, nullable=True, default=0)

    # Idempotency - prevents duplicate recording
    idempotency_key = Column(String(255), nullable=False, index=True)

    # Cost calculation (in cents, computed at record time)
    cost_cents = Column(BigInteger, nullable=False, default=0)

    # Metadata
    request_metadata = Column(String(1000), nullable=True)  # JSON string for extra context
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)

    # Relationships
    tenant = relationship("Tenant", back_populates="usage_events")

    # Constraints
    __table_args__ = (
        # Unique constraint on tenant + idempotency_key ensures exactly-once recording
        UniqueConstraint("tenant_id", "idempotency_key", name="uq_tenant_idempotency_key"),
        # Composite index for quota queries
        Index("ix_usage_events_tenant_type_created", "tenant_id", "usage_type", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<UsageEvent(id={self.id}, tenant_id={self.tenant_id}, type={self.usage_type}, qty={self.quantity}, key={self.idempotency_key[:8]}...)>"