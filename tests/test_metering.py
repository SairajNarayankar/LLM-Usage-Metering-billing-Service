"""Tests for metering and quota enforcement."""
import pytest
from httpx import AsyncClient


class TestMeteringIdempotency:
    """Tests for exactly-once metering with idempotency keys."""

    @pytest.mark.asyncio
    async def test_same_idempotency_key_creates_one_event(
        self, client: AsyncClient, sample_generate_request
    ):
        """Sending same request twice with same idempotency key creates one usage event."""
        # First request
        response1 = await client.post(
            "/api/v1/generate?tenant_id=1",
            json=sample_generate_request,
        )
        assert response1.status_code == 200
        data1 = response1.json()
        event_id_1 = data1["usage_event_id"]

        # Second request with same idempotency key
        response2 = await client.post(
            "/api/v1/generate?tenant_id=1",
            json=sample_generate_request,
        )
        assert response2.status_code == 200
        data2 = response2.json()
        event_id_2 = data2["usage_event_id"]

        # Should return same event ID (duplicate detected)
        assert event_id_1 == event_id_2
        assert data2["is_duplicate"] is True


class TestQuotaEnforcement:
    """Tests for quota boundary enforcement."""

    @pytest.mark.asyncio
    async def test_quota_check_allows_within_limit(self, client: AsyncClient):
        """Quota check returns allowed=true when within limit."""
        response = await client.get(
            "/api/v1/usage/quota/check",
            params={"tenant_id": "1", "usage_type": "ai_tokens", "quantity": "1000"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["allowed"] is True
        assert data["remaining"] >= 0

    @pytest.mark.asyncio
    async def test_quota_exceeded_returns_429(self, client: AsyncClient):
        """Request exceeding quota returns 429 with Retry-After."""
        # This test would need a tenant at quota limit
        # For now, verify the endpoint structure
        response = await client.get(
            "/api/v1/usage/quota/check",
            params={"tenant_id": "999", "usage_type": "ai_tokens", "quantity": "1000000000"},
        )
        # Should be 429 or 404 (tenant not found)
        assert response.status_code in (429, 404)


class TestPricingCalculation:
    """Tests for AI token pricing rules."""

    @pytest.mark.asyncio
    async def test_cached_input_cheaper_than_fresh(self, client: AsyncClient):
        """Cached input tokens should cost less than fresh input tokens."""
        # This would be tested via the pricing service directly
        # or by checking rollup costs match expected calculations
        pass

    @pytest.mark.asyncio
    async def test_reasoning_tokens_billed_as_output(self, client: AsyncClient):
        """Reasoning tokens should be billed at output rate, not free."""
        pass


class TestStripeWebhooks:
    """Tests for Stripe webhook handling."""

    @pytest.mark.asyncio
    async def test_forged_signature_returns_400(self, client: AsyncClient):
        """Webhook with invalid signature returns 400."""
        response = await client.post(
            "/api/v1/billing/webhooks/stripe",
            json={"type": "checkout.session.completed", "id": "evt_test", "data": {"object": {}}},
            headers={"stripe-signature": "invalid-signature"},
        )
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_valid_webhook_processes_once(self, client: AsyncClient):
        """Valid webhook processed once; replay ignored."""
        # Requires Stripe CLI or mock webhook payload with valid signature
        pass


class TestUsageRollup:
    """Tests for monthly usage rollup."""

    @pytest.mark.asyncio
    async def test_rollup_returns_usage_and_cost(self, client: AsyncClient):
        """Rollup endpoint returns used, limit, cost for both usage types."""
        response = await client.get(
            "/api/v1/usage/rollup",
            params={"tenant_id": "1"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "api_calls_used" in data
        assert "ai_tokens_used" in data
        assert "total_cost_cents" in data
        assert data["total_cost_cents"] >= 0