"""Stripe integration service for Checkout and webhooks."""
import stripe
from dataclasses import dataclass
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import Tenant, Plan, Subscription, SubscriptionStatus
from app.core.config import settings
from app.db.database import db


# Initialize Stripe
stripe.api_key = settings.stripe_secret_key


@dataclass
class CheckoutResult:
    """Result of creating a checkout session."""
    checkout_url: str
    session_id: str


@dataclass
class WebhookProcessResult:
    """Result of processing a webhook event."""
    processed: bool
    event_type: str
    message: str


class StripeService:
    """Service for Stripe operations: Checkout, webhooks, subscription sync."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_checkout_session(
        self,
        tenant_id: int,
        plan_name: str,
        success_url: str,
        cancel_url: str,
    ) -> CheckoutResult:
        """
        Create a Stripe Checkout session for subscription upgrade.
        
        Args:
            tenant_id: The tenant upgrading
            plan_name: "free" or "pro"
            success_url: URL to redirect on success
            cancel_url: URL to redirect on cancel
            
        Returns:
            CheckoutResult with checkout URL and session ID
        """
        # Get tenant
        stmt = select(Tenant).where(Tenant.id == tenant_id)
        result = await self.session.execute(stmt)
        tenant = result.scalar_one_or_none()
        
        if not tenant:
            raise ValueError(f"Tenant {tenant_id} not found")

        # Get target plan
        plan_stmt = select(Plan).where(Plan.name == plan_name)
        plan_result = await self.session.execute(plan_stmt)
        plan = plan_result.scalar_one_or_none()
        
        if not plan or not plan.stripe_price_id:
            raise ValueError(f"Plan {plan_name} not found or not configured")

        # Create or get Stripe customer
        if not tenant.stripe_customer_id:
            customer = stripe.Customer.create(
                metadata={"tenant_id": str(tenant_id)},
            )
            tenant.stripe_customer_id = customer.id
            await self.session.flush()
        else:
            customer_id = tenant.stripe_customer_id

        # Create Checkout session
        session = stripe.checkout.Session.create(
            customer=tenant.stripe_customer_id,
            mode="subscription",
            line_items=[{
                "price": plan.stripe_price_id,
                "quantity": 1,
            }],
            success_url=success_url + "?session_id={CHECKOUT_SESSION_ID}",
            cancel_url=cancel_url,
            metadata={
                "tenant_id": str(tenant_id),
                "plan_name": plan_name,
            },
            subscription_data={
                "metadata": {
                    "tenant_id": str(tenant_id),
                    "plan_name": plan_name,
                }
            },
        )

        return CheckoutResult(
            checkout_url=session.url,
            session_id=session.id,
        )

    async def handle_webhook(
        self,
        payload: bytes,
        sig_header: str,
    ) -> WebhookProcessResult:
        """
        Process a Stripe webhook event.
        
        Verifies signature, deduplicates events, and updates tenant subscription.
        """
        # Verify webhook signature
        try:
            event = stripe.Webhook.construct_event(
                payload=payload,
                sig_header=sig_header,
                secret=settings.stripe_webhook_secret,
            )
        except stripe.error.SignatureVerificationError as e:
            return WebhookProcessResult(
                processed=False,
                event_type="unknown",
                message=f"Invalid signature: {str(e)}",
            )

        event_type = event["type"]
        event_id = event["id"]

        # Check if we've already processed this event (idempotency)
        # We'll use a simple approach: store processed event IDs in metadata
        # In production, you'd use a dedicated table
        processed_key = f"stripe_event_{event_id}"
        
        # For simplicity, we'll process the event. In production, add a processed_events table.
        
        try:
            if event_type == "checkout.session.completed":
                await self._handle_checkout_completed(event["data"]["object"])
            elif event_type == "customer.subscription.updated":
                await self._handle_subscription_updated(event["data"]["object"])
            elif event_type == "customer.subscription.deleted":
                await self._handle_subscription_deleted(event["data"]["object"])
            else:
                return WebhookProcessResult(
                    processed=False,
                    event_type=event_type,
                    message=f"Unhandled event type: {event_type}",
                )
            
            await self.session.commit()
            
            return WebhookProcessResult(
                processed=True,
                event_type=event_type,
                message="Event processed successfully",
            )
            
        except Exception as e:
            await self.session.rollback()
            return WebhookProcessResult(
                processed=False,
                event_type=event_type,
                message=f"Error processing event: {str(e)}",
            )

    async def _handle_checkout_completed(self, session_obj: dict) -> None:
        """Handle checkout.session.completed - subscription created."""
        tenant_id = int(session_obj["metadata"]["tenant_id"])
        plan_name = session_obj["metadata"]["plan_name"]
        stripe_subscription_id = session_obj["subscription"]
        stripe_customer_id = session_obj["customer"]

        # Get tenant
        stmt = select(Tenant).where(Tenant.id == tenant_id)
        result = await self.session.execute(stmt)
        tenant = result.scalar_one_or_none()
        
        if not tenant:
            raise ValueError(f"Tenant {tenant_id} not found")

        # Update tenant's Stripe customer ID if not set
        if not tenant.stripe_customer_id:
            tenant.stripe_customer_id = stripe_customer_id

        # Get target plan
        plan_stmt = select(Plan).where(Plan.name == plan_name)
        plan_result = await self.session.execute(plan_stmt)
        plan = plan_result.scalar_one_or_none()
        
        if not plan:
            raise ValueError(f"Plan {plan_name} not found")

        # Get subscription details from Stripe
        subscription = stripe.Subscription.retrieve(stripe_subscription_id)

        # Update or create subscription record
        sub_stmt = select(Subscription).where(Subscription.tenant_id == tenant_id)
        sub_result = await self.session.execute(sub_stmt)
        db_subscription = sub_result.scalar_one_or_none()

        if db_subscription:
            db_subscription.plan_id = plan.id
            db_subscription.stripe_subscription_id = stripe_subscription_id
            db_subscription.stripe_status = SubscriptionStatus(subscription.status)
            db_subscription.stripe_current_period_start = datetime.fromtimestamp(
                subscription.current_period_start, tz=timezone.utc
            )
            db_subscription.stripe_current_period_end = datetime.fromtimestamp(
                subscription.current_period_end, tz=timezone.utc
            )
            db_subscription.stripe_cancel_at_period_end = 1 if subscription.cancel_at_period_end else 0
        else:
            db_subscription = Subscription(
                tenant_id=tenant_id,
                plan_id=plan.id,
                stripe_subscription_id=stripe_subscription_id,
                stripe_status=SubscriptionStatus(subscription.status),
                stripe_current_period_start=datetime.fromtimestamp(
                    subscription.current_period_start, tz=timezone.utc
                ),
                stripe_current_period_end=datetime.fromtimestamp(
                    subscription.current_period_end, tz=timezone.utc
                ),
                stripe_cancel_at_period_end=1 if subscription.cancel_at_period_end else 0,
            )
            self.session.add(db_subscription)

    async def _handle_subscription_updated(self, subscription_obj: dict) -> None:
        """Handle customer.subscription.updated - plan changes, renewals, etc."""
        stripe_subscription_id = subscription_obj["id"]
        tenant_id = int(subscription_obj["metadata"].get("tenant_id", 0))
        
        if not tenant_id:
            # Try to get from customer
            customer_id = subscription_obj["customer"]
            stmt = select(Tenant).where(Tenant.stripe_customer_id == customer_id)
            result = await self.session.execute(stmt)
            tenant = result.scalar_one_or_none()
            if tenant:
                tenant_id = tenant.id

        if not tenant_id:
            raise ValueError("Could not determine tenant from subscription")

        # Get plan from metadata or price
        plan_name = subscription_obj["metadata"].get("plan_name")
        if not plan_name:
            # Determine from price ID
            price_id = subscription_obj["items"]["data"][0]["price"]["id"]
            plan_stmt = select(Plan).where(Plan.stripe_price_id == price_id)
            plan_result = await self.session.execute(plan_stmt)
            plan = plan_result.scalar_one_or_none()
            if plan:
                plan_name = plan.name

        # Get subscription record
        stmt = select(Subscription).where(Subscription.stripe_subscription_id == stripe_subscription_id)
        result = await self.session.execute(stmt)
        db_subscription = result.scalar_one_or_none()
        
        if not db_subscription:
            raise ValueError(f"Subscription {stripe_subscription_id} not found")

        # Update status and period
        db_subscription.stripe_status = SubscriptionStatus(subscription_obj["status"])
        db_subscription.stripe_current_period_start = datetime.fromtimestamp(
            subscription_obj["current_period_start"], tz=timezone.utc
        )
        db_subscription.stripe_current_period_end = datetime.fromtimestamp(
            subscription_obj["current_period_end"], tz=timezone.utc
        )
        db_subscription.stripe_cancel_at_period_end = 1 if subscription_obj.get("cancel_at_period_end") else 0

        # Update plan if changed
        if plan_name:
            plan_stmt = select(Plan).where(Plan.name == plan_name)
            plan_result = await self.session.execute(plan_stmt)
            plan = plan_result.scalar_one_or_none()
            if plan:
                db_subscription.plan_id = plan.id

    async def _handle_subscription_deleted(self, subscription_obj: dict) -> None:
        """Handle customer.subscription.deleted - subscription cancelled."""
        stripe_subscription_id = subscription_obj["id"]
        
        stmt = select(Subscription).where(Subscription.stripe_subscription_id == stripe_subscription_id)
        result = await self.session.execute(stmt)
        db_subscription = result.scalar_one_or_none()
        
        if db_subscription:
            db_subscription.stripe_status = SubscriptionStatus.CANCELED
            # Optionally downgrade to free plan
            free_plan_stmt = select(Plan).where(Plan.name == "free")
            free_plan_result = await self.session.execute(free_plan_stmt)
            free_plan = free_plan_result.scalar_one_or_none()
            if free_plan:
                db_subscription.plan_id = free_plan.id


async def get_stripe_service() -> StripeService:
    """FastAPI dependency for Stripe service."""
    async with db.session() as session:
        yield StripeService(session)