"""AI Token pricing calculator with real-world pricing rules."""
from dataclasses import dataclass
from app.core.config import settings


@dataclass(frozen=True)
class PricingConstants:
    """Immutable pricing constants (in cents)."""
    api_call_cents: int
    input_token_per_million_cents: int
    cached_input_token_per_million_cents: int
    output_token_per_million_cents: int
    reasoning_token_per_million_cents: int

    @classmethod
    def from_settings(cls) -> "PricingConstants":
        return cls(
            api_call_cents=settings.price_api_call_cents,
            input_token_per_million_cents=settings.price_input_token_per_million_cents,
            cached_input_token_per_million_cents=settings.price_cached_input_token_per_million_cents,
            output_token_per_million_cents=settings.price_output_token_per_million_cents,
            reasoning_token_per_million_cents=settings.price_reasoning_token_per_million_cents,
        )


@dataclass(frozen=True)
class TokenCostBreakdown:
    """Detailed cost breakdown for AI tokens."""
    input_tokens: int
    cached_input_tokens: int
    output_tokens: int
    reasoning_tokens: int

    input_cost_cents: int
    cached_input_cost_cents: int
    output_cost_cents: int
    reasoning_cost_cents: int

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.cached_input_tokens + self.output_tokens + self.reasoning_tokens

    @property
    def total_cost_cents(self) -> int:
        return (
            self.input_cost_cents
            + self.cached_input_cost_cents
            + self.output_cost_cents
            + self.reasoning_cost_cents
        )


class PricingCalculator:
    """
    Calculates costs for usage events.
    
    Pricing Rules (from brief):
    - Cached input tokens are cheaper than fresh input tokens
    - Reasoning tokens count as output tokens (billed at output rate)
    - Token categories cannot simply be added together - each has its own rate
    """

    def __init__(self, constants: PricingConstants | None = None):
        self.constants = constants or PricingConstants.from_settings()

    def calculate_api_call_cost(self, quantity: int = 1) -> int:
        """Calculate cost for API calls (in cents)."""
        return quantity * self.constants.api_call_cents

    def calculate_token_cost(
        self,
        input_tokens: int = 0,
        cached_input_tokens: int = 0,
        output_tokens: int = 0,
        reasoning_tokens: int = 0,
    ) -> TokenCostBreakdown:
        """
        Calculate cost for AI tokens with proper pricing rules.
        
        Rules:
        - Input tokens: billed at input rate
        - Cached input tokens: billed at discounted cached rate
        - Output tokens: billed at output rate
        - Reasoning tokens: billed as output tokens (not a separate free category)
        """
        # Per-million pricing, so divide by 1,000,000 and multiply
        # Using integer arithmetic: (tokens * rate_cents) // 1_000_000
        input_cost = (input_tokens * self.constants.input_token_per_million_cents) // 1_000_000
        cached_input_cost = (cached_input_tokens * self.constants.cached_input_token_per_million_cents) // 1_000_000
        output_cost = (output_tokens * self.constants.output_token_per_million_cents) // 1_000_000
        reasoning_cost = (reasoning_tokens * self.constants.reasoning_token_per_million_cents) // 1_000_000

        return TokenCostBreakdown(
            input_tokens=input_tokens,
            cached_input_tokens=cached_input_tokens,
            output_tokens=output_tokens,
            reasoning_tokens=reasoning_tokens,
            input_cost_cents=input_cost,
            cached_input_cost_cents=cached_input_cost,
            output_cost_cents=output_cost,
            reasoning_cost_cents=reasoning_cost,
        )

    def calculate_token_cost_from_breakdown(self, breakdown: TokenCostBreakdown) -> int:
        """Get total cost from a breakdown."""
        return breakdown.total_cost_cents


# Global instance
pricing_calculator = PricingCalculator()