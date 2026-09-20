"""Database seed script for development and testing."""
import asyncio
from sqlalchemy import select
from app.db.database import db, Base
from app.models import Tenant, Plan, Subscription, PlanType, SubscriptionStatus
from app.core.config import settings


async def seed_database():
    """Seed the database with initial data."""
    print("Creating tables...")
    await db.create_tables()
    
    async with db.session() as session:
        # Check if plans already exist
        stmt = select(Plan).where(Plan.name.in_(["free", "pro"]))
        result = await session.execute(stmt)
        existing_plans = {p.name: p for p in result.scalars().all()}
        
        if "free" not in existing_plans:
            print("Creating Free plan...")
            free_plan = Plan(
                name="free",
                display_name="Free Tier",
                stripe_price_id=settings.stripe_price_id_free or "price_free_monthly",
                api_calls_limit=1000,
                ai_tokens_limit=100_000,
                monthly_price_cents=0,
            )
            session.add(free_plan)
            existing_plans["free"] = free_plan
        else:
            print("Free plan exists, updating...")
            free_plan = existing_plans["free"]
            free_plan.api_calls_limit = 1000
            free_plan.ai_tokens_limit = 100_000
            free_plan.monthly_price_cents = 0

        if "pro" not in existing_plans:
            print("Creating Pro plan...")
            pro_plan = Plan(
                name="pro",
                display_name="Pro Tier",
                stripe_price_id=settings.stripe_price_id_pro or "price_pro_monthly",
                api_calls_limit=100_000,
                ai_tokens_limit=10_000_000,
                monthly_price_cents=2900,  # $29.00/month
            )
            session.add(pro_plan)
            existing_plans["pro"] = pro_plan
        else:
            print("Pro plan exists, updating...")
            pro_plan = existing_plans["pro"]
            pro_plan.api_calls_limit = 100_000
            pro_plan.ai_tokens_limit = 10_000_000
            pro_plan.monthly_price_cents = 2900

        await session.flush()
        print(f"Plans ready: free (id={existing_plans['free'].id}), pro (id={existing_plans['pro'].id})")

        # Create a demo tenant if none exists
        stmt = select(Tenant).limit(1)
        result = await session.execute(stmt)
        existing_tenant = result.scalar_one_or_none()
        
        if not existing_tenant:
            print("Creating demo tenant...")
            demo_tenant = Tenant(name="Demo Company")
            session.add(demo_tenant)
            await session.flush()
            
            # Create free subscription for demo tenant
            demo_sub = Subscription(
                tenant_id=demo_tenant.id,
                plan_id=existing_plans["free"].id,
                stripe_status=SubscriptionStatus.ACTIVE,
            )
            session.add(demo_sub)
            print(f"Created demo tenant: {demo_tenant.name} (id={demo_tenant.id})")
        else:
            print(f"Demo tenant already exists: {existing_tenant.name} (id={existing_tenant.id})")

        await session.commit()
        print("Database seeded successfully!")


async def reset_database():
    """Drop and recreate all tables, then seed."""
    print("Dropping tables...")
    await db.drop_tables()
    await seed_database()


if __name__ == "__main__":
    asyncio.run(seed_database())