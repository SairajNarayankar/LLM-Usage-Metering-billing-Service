# Evidence Document

> **Instructions**: For each requirement checkbox in Section 6 of the capstone brief, paste one proof here.
> Proof can be: test output, curl transcript, log line, or screenshot reference.
> Claims without evidence score as **not done**.

---

## Metering

### ✅ A billable action creates exactly one usage event, even under retries — deduplicated by idempotency key.

**Proof**:
```
[Paste curl transcript showing same request sent twice with same idempotency_key → exactly one usage_event row]
```

**Test command**:
```bash
# First request
curl -X POST http://localhost:8000/api/v1/generate \
  -H "Content-Type: application/json" \
  -H "X-Tenant-ID: 1" \
  -d '{"prompt": "test", "max_tokens": 100, "idempotency_key": "evidence-1"}'

# Second request (same idempotency key)
curl -X POST http://localhost:8000/api/v1/generate \
  -H "Content-Type: application/json" \
  -H "X-Tenant-ID: 1" \
  -d '{"prompt": "test", "max_tokens": 100, "idempotency_key": "evidence-1"}'

# Verify only one row in DB
docker compose exec postgres psql -U postgres -d metering_billing -c "SELECT * FROM usage_events WHERE idempotency_key='evidence-1';"
```

---

## Quotas

### ✅ Usage is checked against the tenant's plan; requests over the limit are rejected.

**Proof**:
```
[Paste curl transcript or log showing quota check rejecting request over limit]
```

### ✅ Responses carry the correct status codes (429 / 402) and a message explaining why.

**Proof**:
```
[Paste curl transcript showing 429 response with Retry-After header and clear message]
```

```
[Paste curl transcript showing 402 response with upgrade message]
```

---

## Cost Calculation

### ✅ Monthly usage rolls up into a cost figure per tenant.

**Proof**:
```
[Paste GET /api/v1/usage/rollup response showing used, limit, cost_cents for both types]
```

### ✅ AI token pricing handles cached input tokens, reasoning tokens, and output pricing correctly.

**Proof**:
```
[Paste pricing calculation breakdown showing:
  - input_tokens * input_rate
  - cached_input_tokens * cached_rate (cheaper)
  - output_tokens * output_rate
  - reasoning_tokens * output_rate (billed as output)
  Total matches expected]
```

**Test case**:
- Input: 1000 tokens, Cached: 500, Output: 2000, Reasoning: 500
- Expected: (1000*150 + 500*37 + 2000*600 + 500*600) / 1_000_000 = X cents

### ✅ Pricing constants are pinned in config, with proof of correct totals in EVIDENCE.md.

**Proof**:
```
[Reference to .env.example and app/core/config.py showing all pricing constants]
[Reference to app/services/pricing.py showing calculation logic]
```

---

## Stripe Integration

### ✅ Subscription checkout works end-to-end in Stripe test mode.

**Proof**:
```
[Paste Stripe Checkout session creation response + browser checkout completion screenshot or stripe CLI trigger output]
```

### ✅ Webhooks verify signatures, ignore duplicate events, and update tenant plan/status.

**Proof**:
```
[Paste webhook handler log showing:
  1. Valid signature → processed=true
  2. Forged signature → 400 error
  3. Replay same event_id → processed=false (deduplicated)]
```

**Test commands**:
```bash
# Valid webhook (via stripe CLI)
stripe trigger checkout.session.completed

# Forged signature
curl -X POST http://localhost:8000/api/v1/billing/webhooks/stripe \
  -H "Content-Type: application/json" \
  -H "stripe-signature: invalid" \
  -d '{"type": "checkout.session.completed", "id": "evt_forge", "data": {"object": {}}}'

# Replay same event
stripe trigger checkout.session.completed  # run twice
```

---

## Data Model, Tests & Documentation

### ✅ Database includes tenants, plans, subscriptions, and usage events; customer data isolated per tenant.

**Proof**:
```
[Paste migration file (migrations/versions/001_initial.py) showing all 4 tables with FK constraints]
[Paste query showing tenant isolation: SELECT * FROM usage_events WHERE tenant_id=1 vs tenant_id=2]
```

### ✅ README + architecture diagram + setup instructions; the required files from Section 10 present.

**Proof**:
```
[List of required files present in repo root:]
- README.md ✅
- capstone.yaml ✅
- EVIDENCE.md ✅
- BUILDLOG.md ✅
- .env.example ✅
- docker-compose.yml ✅
- requirements.txt ✅
- alembic.ini ✅
```

---

## Acceptance Probes (from Section 12)

### Probe 1 — Idempotency
**Command**: Send same billable request twice with one idempotency key
**Expected**: Exactly one usage event; second response mirrors first
**Evidence**: [Paste transcript]

### Probe 2 — Quota Boundary
**Command**: Drive tenant to exact quota → request at boundary → request after
**Expected**: Boundary behaves per documented rule; next returns 429/402 with clear message
**Evidence**: [Paste transcript]

### Probe 3 — Stripe Checkout
**Command**: Complete Stripe test Checkout
**Expected**: Webhook flips tenant Free → Pro; GET /usage shows new limits
**Evidence**: [Paste transcript + rollup before/after]

### Probe 4 — Webhook Security
**Command**: Send forged webhook (bad signature) → Replay real event twice
**Expected**: Forged → 400, nothing changes; Replay → processed once
**Evidence**: [Paste transcript]

### Probe 5 — Pricing Rules
**Command**: Check pinned pricing rules with cached-input and reasoning tokens
**Expected**: GET /usage matches exact expected totals
**Evidence**: [Paste calculation + rollup response]

---

## Notes

- All evidence should be **copy-pasteable** and **verifiable** by evaluator
- Use `docker compose exec postgres psql ...` for DB queries
- Use `curl -v` for full request/response transcripts
- Timestamps help verify chronological order