# Usage Metering & Billing Engine

> **FlyRank Internship Capstone — Backend Track**  
> A production-ready metering, quota enforcement, and Stripe billing engine built with FastAPI, PostgreSQL, and clean architecture.

[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-green.svg)](https://fastapi.tiangolo.com)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-blue.svg)](https://postgresql.org)
[![Stripe](https://img.shields.io/badge/Stripe-Test%20Mode-purple.svg)](https://stripe.com)
[![Tests](https://img.shields.io/badge/Tests-8%20passed-brightgreen.svg)](tests/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## 🎯 Project Overview

This capstone builds the **core billing engine** every SaaS needs: **how much has a customer used, what does it cost, and have they hit their limit?**

It implements a complete, production-ready system with:
- **Idempotent usage metering** — exactly-once recording via idempotency keys
- **Quota enforcement** — pre-action checks with correct HTTP status codes (429/402)
- **Real-world AI token pricing** — cached input cheaper, reasoning = output rate
- **Stripe subscription integration** — Checkout + signature-verified webhooks
- **Multi-tenant isolation** — complete data separation per customer

---

## 🏗️ Architecture

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

### Request Flows

| Flow | Path | Description |
|------|------|-------------|
| **Metering** | `POST /generate` → `QuotaService.check_and_record()` → `MeteringService.record_usage()` → DB | Idempotent usage recording with quota check |
| **Quota** | `GET /usage/quota/check` → `QuotaService.check_quota()` | Pre-action limit validation |
| **Rollup** | `GET /usage/rollup` → `MeteringService.get_monthly_usage()` | Monthly usage + cost aggregation |
| **Stripe Sync** | `checkout.session.completed` → webhook → `StripeService.handle_webhook()` → DB | Subscription state sync |

---

## ✨ Features Implemented

### 1. Idempotent Usage Metering
- **Database-level guarantee**: Unique constraint on `(tenant_id, idempotency_key)`
- **Exactly-once semantics**: Retried requests return original event with `is_duplicate: true`
- **Supported types**: `api_call` (count) + `ai_tokens` (token breakdown)

### 2. Quota Enforcement
- **Pre-action validation**: Checks *before* recording usage
- **Correct HTTP semantics**:
  - `429 Too Many Requests` — limit exceeded (with `Retry-After` header)
  - `402 Payment Required` — feature not on plan / subscription inactive
  - `200 OK` — allowed with remaining quota
- **Period-aware**: Uses Stripe subscription period when available, falls back to calendar month

### 3. AI Token Pricing (Real-World Rules)
| Token Category | Rate (¢/1M) | Notes |
|----------------|-------------|-------|
| Input (fresh) | 150 | Standard input tokens |
| Cached Input | 37 | **Cheaper** — provider had these cached |
| Output | 600 | Generated tokens |
| Reasoning | 600 | **Billed as output** — not a free category |

> **Key rule**: Token categories *cannot* be simply added — each priced independently at its own rate.

### 4. Stripe Integration (Test Mode)
- **Checkout flow**: `POST /billing/checkout` → Stripe Checkout → webhook → subscription created
- **Webhook handlers**: 
  - `checkout.session.completed` — create subscription
  - `customer.subscription.updated` — sync status/period/plan
  - `customer.subscription.deleted` — cancel → downgrade to Free
- **Security**: Signature verification (`stripe.Webhook.construct_event`), event deduplication

### 5. Multi-Tenant Data Isolation
- All queries scoped to `tenant_id`
- Foreign keys with `ON DELETE CASCADE`
- Row-level isolation at application + database level

### 6. Money Handling
- **All amounts stored as integer cents** (`BigInteger`) — **never floats**
- Pricing constants pinned in config (`.env`)
- Integer arithmetic: `(tokens * rate_cents) // 1_000_000`

---

## 🚀 Quick Start

### Prerequisites
- Docker & Docker Compose
- Python 3.11+
- Stripe CLI (for webhook testing)

### 1. Clone & Setup

```bash
git clone https://github.com/YOUR_USERNAME/flyrank-capstone-metering-billing.git
cd flyrank-capstone-metering-billing

# Start PostgreSQL
docker compose up -d

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Configure Environment

```bash
cp .env.example .env
# Edit .env with your Stripe test keys:
# - STRIPE_SECRET_KEY (sk_test_...)
# - STRIPE_PUBLISHABLE_KEY (pk_test_...)
# - STRIPE_WEBHOOK_SECRET (from `stripe listen`)
# - STRIPE_PRICE_ID_FREE, STRIPE_PRICE_ID_PRO (from Stripe Dashboard)
```

### 3. Create Stripe Products (Dashboard → Products)

| Product | Price | Interval | Copy to `.env` |
|---------|-------|----------|----------------|
| Free Plan | $0.00 | Monthly | `STRIPE_PRICE_ID_FREE` |
| Pro Plan | $29.00 | Monthly | `STRIPE_PRICE_ID_PRO` |

### 4. Seed Database & Run

```bash
# Seed plans + demo tenant
python -m scripts.seed

# Start server
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000

# In another terminal, forward webhooks
stripe listen --forward-to localhost:8000/api/v1/billing/webhooks/stripe
```

### 5. Test the API

```bash
# Health check
curl http://localhost:8000/health

# List plans
curl http://localhost:8000/api/v1/plans

# Create tenant
curl -X POST http://localhost:8000/api/v1/tenants \
  -H "Content-Type: application/json" \
  -d '{"name": "Acme Corp"}'

# Simulate AI generation (meters tokens, checks quota)
curl -X POST "http://localhost:8000/api/v1/generate?tenant_id=1" \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Write a haiku about billing", "max_tokens": 500, "idempotency_key": "test-1"}'

# Check quota
curl "http://localhost:8000/api/v1/usage/quota/check?tenant_id=1&usage_type=ai_tokens&quantity=1000"

# Monthly rollup
curl "http://localhost:8000/api/v1/usage/rollup?tenant_id=1"

# Upgrade to Pro (Stripe Checkout)
curl -X POST http://localhost:8000/api/v1/billing/checkout \
  -H "Content-Type: application/json" \
  -d '{"tenant_id": 1, "plan_name": "pro"}'
```

---

## 📚 API Reference

### Tenants
| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/v1/tenants` | Create tenant (auto-assigns Free plan) |
| `GET` | `/api/v1/tenants` | List all tenants |
| `GET` | `/api/v1/tenants/{id}` | Get tenant details |

### Plans
| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/v1/plans` | List all plans |
| `GET` | `/api/v1/plans/{name}` | Get plan details |

### Usage & Metering
| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/v1/usage/record` | Record usage event (idempotent) |
| `GET` | `/api/v1/usage/quota/check` | Check quota before action |
| `GET` | `/api/v1/usage/rollup` | Monthly usage + cost summary |

### Billable Endpoint (Demo)
| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/v1/generate` | Simulated AI generation → meters tokens, checks quota |

### Billing / Stripe
| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/v1/billing/checkout` | Create Stripe Checkout session |
| `POST` | `/api/v1/billing/webhooks/stripe` | Stripe webhook handler |
| `GET` | `/api/v1/billing/success` | Checkout success page |
| `GET` | `/api/v1/billing/cancel` | Checkout cancel page |

---

## 🧪 Testing

### Run Test Suite

```bash
python -m pytest tests/ -v
```

### Run Acceptance Probes (from Capstone Brief)

```bash
# Probe 1: Idempotency
python -c "
import httpx
payload = {'prompt': 'test', 'max_tokens': 100, 'idempotency_key': 'probe-1'}
r1 = httpx.post('http://localhost:8000/api/v1/generate?tenant_id=1', json=payload)
r2 = httpx.post('http://localhost:8000/api/v1/generate?tenant_id=1', json=payload)
print('Same event_id:', r1.json()['usage_event_id'] == r2.json()['usage_event_id'])
print('Second is_duplicate:', r2.json()['is_duplicate'])
"

# Probe 2: Quota Boundary
curl "http://localhost:8000/api/v1/usage/quota/check?tenant_id=1&usage_type=api_call&quantity=1000"
curl "http://localhost:8000/api/v1/usage/quota/check?tenant_id=1&usage_type=api_call&quantity=1001"

# Probe 3: Stripe Checkout
curl -X POST http://localhost:8000/api/v1/billing/checkout \
  -H "Content-Type: application/json" \
  -d '{"tenant_id": 1, "plan_name": "pro"}'
# Complete checkout in browser, then:
curl "http://localhost:8000/api/v1/usage/rollup?tenant_id=1"

# Probe 4: Webhook Security
curl -X POST http://localhost:8000/api/v1/billing/webhooks/stripe \
  -H "Content-Type: application/json" \
  -H "stripe-signature: invalid" \
  -d '{"type": "checkout.session.completed", "id": "evt_test", "data": {"object": {}}}'
stripe trigger checkout.session.completed
stripe trigger checkout.session.completed

# Probe 5: Pricing Rules
python -c "
from app.services.pricing import pricing_calculator
b = pricing_calculator.calculate_token_cost(input_tokens=1000, cached_input_tokens=500, output_tokens=2000, reasoning_tokens=500)
print('Total:', b.total_cost_cents, 'cents')
print('Cached cheaper:', b.cached_input_cost_cents < b.input_cost_cents)
print('Reasoning=output:', b.reasoning_cost_cents == b.output_cost_cents * 0.25)
"
```

---

## 📁 Project Structure

```
flyrank-capstone-metering-billing/
├── app/
│   ├── api/              # FastAPI routes
│   │   ├── tenants.py    # Tenant, plan, subscription endpoints
│   │   └── usage.py      # Metering, quota, billing, generate endpoints
│   ├── core/
│   │   └── config.py     # Pydantic Settings (env config)
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
├── tests/                # Test suite (8 tests)
├── .env.example          # Environment template
├── docker-compose.yml    # PostgreSQL
├── requirements.txt      # Python dependencies
├── alembic.ini           # Migration config
├── capstone.yaml         # Capstone manifest
├── EVIDENCE.md           # Requirement proofs
├── BUILDLOG.md           # AI-assisted build log
└── README.md             # This file
```

---

## 🔧 Configuration

All config via environment variables (`.env`):

```env
# Database
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/metering_billing
DATABASE_URL_SYNC=postgresql+psycopg2://postgres:postgres@localhost:5432/metering_billing

# Stripe (Test Mode Only)
STRIPE_SECRET_KEY=sk_test_...
STRIPE_PUBLISHABLE_KEY=pk_test_...
STRIPE_WEBHOOK_SECRET=whsec_...
STRIPE_PRICE_ID_FREE=price_xxx
STRIPE_PRICE_ID_PRO=price_yyy

# App
APP_ENV=development
APP_HOST=0.0.0.0
APP_PORT=8000
LOG_LEVEL=INFO

# Pricing (cents per unit)
PRICE_API_CALL_CENTS=1
PRICE_INPUT_TOKEN_PER_MILLION_CENTS=150
PRICE_CACHED_INPUT_TOKEN_PER_MILLION_CENTS=37
PRICE_OUTPUT_TOKEN_PER_MILLION_CENTS=600
PRICE_REASONING_TOKEN_PER_MILLION_CENTS=600
```

---

## 📋 Capstone Requirements Checklist

| Requirement | Status | Evidence |
|-------------|--------|----------|
| Idempotent metering (exactly-once) | ✅ | `EVIDENCE.md` Probe 1 |
| Quota enforcement (429/402) | ✅ | `EVIDENCE.md` Probe 2 |
| AI token pricing rules | ✅ | `EVIDENCE.md` Probe 5 |
| Stripe Checkout + webhooks | ✅ | `EVIDENCE.md` Probe 3, 4 |
| Multi-tenant isolation | ✅ | DB schema + queries |
| Integer money math | ✅ | All costs in cents |
| Signature-verified webhooks | ✅ | `EVIDENCE.md` Probe 4 |
| Event deduplication | ✅ | `EVIDENCE.md` Probe 4 |

---

## 📝 Limitations (Honest Assessment)

- **No proration**: Mid-cycle upgrades charge full price (stretch goal)
- **No invoicing**: Monthly statements not generated (stretch goal)
- **No usage alerts**: No 80%/100% notifications (stretch goal)
- **Single demo endpoint**: Only `/generate` exercises metering
- **Stripe test mode only**: No live payment processing
- **Simplified auth**: `tenant_id` via query param (not JWT/OAuth)
- **Calendar month fallback**: Used when Stripe period unavailable

---

## 🛠️ Tech Stack

| Layer | Technology |
|-------|------------|
| Language | Python 3.11+ |
| Framework | FastAPI 0.115+ |
| Database | PostgreSQL 16 (asyncpg) |
| ORM | SQLAlchemy 2.0 (async) |
| Migrations | Alembic |
| Payments | Stripe (Test Mode) |
| Testing | pytest + httpx |
| Config | Pydantic Settings |
| Containerization | Docker Compose |

---

## 🤝 AI-Assisted Development

This project was built with AI assistance (Claude). See [`BUILDLOG.md`](BUILDLOG.md) for:
- Where AI generated code
- Where AI was wrong and what was corrected
- Key design decisions made by human

> **Principle**: "AI-assisted building is encouraged — and owned. You must be able to explain any 2–3 lines of your code."

---

## 📄 License

MIT License — see [LICENSE](LICENSE) for details.

---

## 🙏 Acknowledgments

- **FlyRank Internship** — Backend Track Capstone
- **Stripe** — Excellent test mode + CLI for local development
- **FastAPI / SQLAlchemy** — Modern, type-safe Python frameworks
- **PostgreSQL** — Rock-solid relational database

---

## 📞 Contact

**Author**: [Your Name]  
**Capstone**: FlyRank Internship — Backend Track  
**Repository**: https://github.com/YOUR_USERNAME/flyrank-capstone-metering-billing

---

**Built with ❤️ for the FlyRank Internship Capstone**