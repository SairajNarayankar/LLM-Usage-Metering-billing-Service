"""Initial migration - create all tables.

Revision ID: 001
Revises: 
Create Date: 2024-01-01 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create plans table
    op.create_table(
        'plans',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('name', sa.String(length=50), nullable=False),
        sa.Column('display_name', sa.String(length=100), nullable=False),
        sa.Column('stripe_price_id', sa.String(length=255), nullable=True),
        sa.Column('api_calls_limit', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('ai_tokens_limit', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('monthly_price_cents', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name'),
        sa.UniqueConstraint('stripe_price_id'),
    )

    # Create tenants table
    op.create_table(
        'tenants',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('stripe_customer_id', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('stripe_customer_id'),
    )
    op.create_index('ix_tenants_stripe_customer_id', 'tenants', ['stripe_customer_id'], unique=False)

    # Create subscriptions table
    op.create_table(
        'subscriptions',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('tenant_id', sa.BigInteger(), nullable=False),
        sa.Column('plan_id', sa.BigInteger(), nullable=False),
        sa.Column('stripe_subscription_id', sa.String(length=255), nullable=True),
        sa.Column('stripe_status', sa.String(length=50), nullable=False, server_default='incomplete'),
        sa.Column('stripe_current_period_start', sa.DateTime(timezone=True), nullable=True),
        sa.Column('stripe_current_period_end', sa.DateTime(timezone=True), nullable=True),
        sa.Column('stripe_cancel_at_period_end', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['plan_id'], ['plans.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('tenant_id'),
        sa.UniqueConstraint('stripe_subscription_id'),
    )
    op.create_index('ix_subscriptions_stripe_subscription_id', 'subscriptions', ['stripe_subscription_id'], unique=False)
    op.create_index('ix_subscriptions_tenant_plan', 'subscriptions', ['tenant_id', 'plan_id'], unique=False)

    # Create usage_events table
    op.create_table(
        'usage_events',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('tenant_id', sa.BigInteger(), nullable=False),
        sa.Column('usage_type', sa.String(length=20), nullable=False),
        sa.Column('quantity', sa.Integer(), nullable=False),
        sa.Column('input_tokens', sa.Integer(), nullable=True, server_default='0'),
        sa.Column('cached_input_tokens', sa.Integer(), nullable=True, server_default='0'),
        sa.Column('output_tokens', sa.Integer(), nullable=True, server_default='0'),
        sa.Column('reasoning_tokens', sa.Integer(), nullable=True, server_default='0'),
        sa.Column('idempotency_key', sa.String(length=255), nullable=False),
        sa.Column('cost_cents', sa.BigInteger(), nullable=False, server_default='0'),
        sa.Column('request_metadata', sa.String(length=1000), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('tenant_id', 'idempotency_key', name='uq_tenant_idempotency_key'),
    )
    op.create_index('ix_usage_events_tenant_id', 'usage_events', ['tenant_id'], unique=False)
    op.create_index('ix_usage_events_usage_type', 'usage_events', ['usage_type'], unique=False)
    op.create_index('ix_usage_events_created_at', 'usage_events', ['created_at'], unique=False)
    op.create_index('ix_usage_events_tenant_type_created', 'usage_events', ['tenant_id', 'usage_type', 'created_at'], unique=False)
    op.create_index('ix_usage_events_idempotency_key', 'usage_events', ['idempotency_key'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_usage_events_idempotency_key', table_name='usage_events')
    op.drop_index('ix_usage_events_tenant_type_created', table_name='usage_events')
    op.drop_index('ix_usage_events_created_at', table_name='usage_events')
    op.drop_index('ix_usage_events_usage_type', table_name='usage_events')
    op.drop_index('ix_usage_events_tenant_id', table_name='usage_events')
    op.drop_table('usage_events')
    
    op.drop_index('ix_subscriptions_tenant_plan', table_name='subscriptions')
    op.drop_index('ix_subscriptions_stripe_subscription_id', table_name='subscriptions')
    op.drop_table('subscriptions')
    
    op.drop_index('ix_tenants_stripe_customer_id', table_name='tenants')
    op.drop_table('tenants')
    
    op.drop_table('plans')