# Usage Metering & Billing Engine

> FlyRank Internship Capstone — Backend Track

A production-ready backend service for metering customer usage, enforcing subscription quotas, calculating costs with real-world AI token pricing rules, and integrating with Stripe for subscription management.

## Architecture

```
┌─────────────────┐     ┌──────────────────┐     ┌──────────────────┐
│   Client App    │────▶│  FastAPI Server  │────▶│   PostgreSQL     │
│                 │     │                  │     │                  │
│  POST /generate │     │  MeterService    │     │  tenants         │
│  POST /usage    │     │  QuotaService    │     │  plans           │
│  GET  /usage    │     │  StripeService   │     │  subscriptions   │
└─────────────────┘     └────────┬─────────┘     │  usage_events    │
                                 │               └──────────────────┘
                                 ▼
                        ┌──────────────────┐
                        │     Stripe       │
                        │  (Test Mode)     │
                        │                  │
                        │  Checkout        │
                        │  Webhooks        │
                        └──────────────────┘
```

### Request Flow

1. **Metering Path**: `POST /api/v1/generate` → `QuotaService.check_and_record()` → `MeteringService.record_usage()` → Database
2. **Quota Enforcement**: Checked *before* recording usage; returns `429` (quota exceeded) or `402` (upgrade required)
3. **Cost Calculation**: Real-time pricing with cached input, reasoning tokens billed as output
4. **Stripe Sync**: `checkout.session.completed` → webhook → updates tenant plan/status

## Features

- ✅ **Idempotent Metering**: Exactly-once usage recording via idempotency keys (DB unique constraint)
- ✅ **Quota Enforcement**: Pre-action checks with `429 Too Many Requests` / `402 Payment Required`
- ✅ **AI Token Pricing**: Cached input (cheaper), reasoning tokens (billed as output), per-category rates
- ✅ **Stripe Integration**: Checkout flow + signature-verified webhooks with deduplication
- ✅ **Multi-tenant**: Complete data isolation per tenant
- ✅ **Integer Money Math**: All costs stored as cents (no floats)

## Quick Start

### Prerequisites
- Docker & Docker Compose
- Python 3.11+
- Stripe CLI (for webhook testing)

### Setup

```bash
# 1. Clone and enter directory
cd flyrank-capstone-metering-billing

# 2. Start PostgreSQL
docker compose up -d

# 3. Create virtual environment
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# 4. Install dependencies
pip install -r requirements.txt

# 5. Configure environment
cp .env.example .env
# Edit .env with your Stripe test keys (from Stripe Dashboard > Developers > API keys)
# Get webhook secret: stripe listen --forward-to localhost:8000/api/v1/billing/webhooks/stripe

# 6. Seed database
python scripts/seed.py

# 7. Run server
uvicorn app.main:app --reload --port 8000
```

### Stripe CLI Setup (for local webhook testing)

```bash
# Install Stripe CLI
# Windows: scoop install stripe  |  Mac: brew install stripe/stripe-cli/stripe  |  Linux: see docs

# Login to Stripe (opens browser)
stripe login

# Forward webhooks to local server
stripe listen --forward-to localhost:8000/api/v1/billing/webhooks/stripe
# Copy the webhook signing secret (whsec_...) to .env STRIPE_WEBHOOK_SECRET

# In another terminal, trigger test events
stripe trigger checkout.session.completed
stripe trigger customer.subscription.updated
stripe trigger customer.subscription.deleted
```

## API Reference

### Tenants
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/tenants` | Create tenant (auto-assigns Free plan) |
| GET | `/api/v1/tenants` | List all tenants |
| GET | `/api/v1/tenants/{id}` | Get tenant details |

### Plans
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/plans` | List all plans |
| GET | `/api/v1/plans/{name}` | Get plan details |

### Usage & Metering
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/usage/record` | Record usage event (idempotent) |
| GET | `/api/v1/usage/quota/check` | Check quota before action |
| GET | `/api/v1/usage/rollup` | Monthly usage + cost summary |

### Billable Endpoint (Demo)
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/generate` | Simulated AI generation → meters tokens, checks quota |

### Billing / Stripe
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/billing/checkout` | Create Stripe Checkout session |
| POST | `/api/v1/billing/webhooks/stripe` | Stripe webhook handler |
| GET | `/api/v1/billing/success` | Checkout success page |
| GET | `/api/v1/billing/cancel` | Checkout cancel page |

## Usage Examples

### Create a Tenant
```bash
curl -X POST http://localhost:8000/api/v1/tenants \
  -H "Content-Type: application/json" \
  -d '{"name": "Acme Corp"}'
```

### Simulate AI Generation (Meters Tokens)
```bash
curl -X POST http://localhost:8000/api/v1/generate \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "Write a haiku about billing systems",
    "max_tokens": 500,
    "idempotency_key": "gen-001"
  }' \
  -H "X-Tenant-ID: 1"
```

### Check Quota
```bash
curl "http://localhost:8000/api/v1/usage/quota/check?tenant_id=1&usage_type=ai_tokens&quantity=1000"
```

### Get Usage Rollup
```bash
curl "http://localhost:8000/api/v1/usage/rollup?tenant_id=1"
```

### Upgrade to Pro (Stripe Checkout)
```bash
curl -X POST http://localhost:8000/api/v1/billing/checkout \
  -H "Content-Type: application/json" \
  -d '{"tenant_id": 1, "plan_name": "pro"}'
```

## Pricing Constants (configurable via .env)

| Component | Rate (cents per million) |
|-----------|-------------------------|
| API Call | 1¢ per call |
| Input Tokens | 150¢ / 1M |
| Cached Input Tokens | 37¢ / 1M |
| Output Tokens | 600¢ / 1M |
| Reasoning Tokens | 600¢ / 1M (billed as output) |

*Rates approximate Gemini 1.5 Flash pricing for demonstration.*

## Project Structure

```
flyrank-capstone-metering-billing/
├── app/
│   ├── api/              # FastAPI routes
│   │   ├── tenants.py    # Tenant, plan, subscription endpoints
│   │   └── usage.py      # Metering, quota, billing, generate endpoints
│   ├── core/
│   │   └── config.py     # Pydantic settings
│   ├── db/
│   │   └── database.py   # SQLAlchemy async setup
│   ├── models/           # SQLAlchemy models
│   │   ├── tenant.py     # Tenant, Plan, Subscription
│   │   └── usage.py      # UsageEvent, UsageType, TokenCategory
│   ├── schemas/          # Pydantic request/response models
│   ├── services/         # Business logic
│   │   ├── pricing.py    # Token pricing calculator
│   │   ├── metering.py   # Idempotent usage recording
│   │   ├── quota.py      # Quota enforcement
│   │   └── stripe_service.py  # Checkout + webhooks
│   └── main.py           # FastAPI app factory
├── migrations/           # Alembic migrations
├── scripts/
│   └── seed.py           # Database seeding
├── tests/                # Test suite
├── .env.example          # Environment template
├── docker-compose.yml    # PostgreSQL
├── requirements.txt      # Python dependencies
├── alembic.ini           # Migration config
├── capstone.yaml         # Capstone manifest
├── EVIDENCE.md           # Requirement proofs
├── BUILDLOG.md           # AI-assisted build log
└── README.md             # This file
```

## Limitations

- **No proration**: Mid-cycle upgrades charge full price (stretch goal)
- **No invoicing**: Monthly statements not generated (stretch goal)
- **No usage alerts**: No 80%/100% notifications (stretch goal)
- **Single dummy endpoint**: Only `/generate` exercises metering
- **Stripe test mode only**: No live payment processing
- **No authentication**: Tenant ID passed as header/query param for simplicity
- **Calendar month fallback**: Uses subscription period when available, else calendar month

## Testing

```bash
# Run tests (when implemented)
pytest tests/ -v

# Manual acceptance probes (from capstone brief)
# Probe 1: Idempotency - send same request twice with same idempotency_key
# Probe 2: Quota boundary - drive tenant to limit, verify 429/402
# Probe 3: Stripe Checkout - complete test flow, verify plan flip
# Probe 4: Webhook security - forge signature → 400, replay → ignored
# Probe 5: Pricing - verify cached input & reasoning token rules
```

## License

MIT — FlyRank Internship Capstone Project