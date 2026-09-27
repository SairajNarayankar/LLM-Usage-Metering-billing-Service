import httpx

print('=' * 60)
print('FINAL ACCEPTANCE PROBES')
print('=' * 60)

# PROBE 1: Idempotency
print()
print('PROBE 1: Idempotency - Send same request twice with same key')
payload = {'prompt': 'final test', 'max_tokens': 50, 'idempotency_key': 'final-probe-1'}
r1 = httpx.post('http://localhost:8000/api/v1/generate?tenant_id=1', json=payload)
r2 = httpx.post('http://localhost:8000/api/v1/generate?tenant_id=1', json=payload)
d1 = r1.json()
d2 = r2.json()
print('  First: event_id=%s, duplicate=%s' % (d1['usage_event_id'], d1['is_duplicate']))
print('  Second: event_id=%s, duplicate=%s' % (d2['usage_event_id'], d2['is_duplicate']))
print('  PASS: Same event_id = %s' % (d1['usage_event_id'] == d2['usage_event_id']))

# PROBE 2: Quota boundary
print()
print('PROBE 2: Quota boundary - 429/402 responses')
r = httpx.get('http://localhost:8000/api/v1/usage/quota/check?tenant_id=1&usage_type=api_call&quantity=1000')
print('  At limit (1000): %s - %s' % (r.status_code, 'PASS' if r.status_code == 200 else 'FAIL'))

r = httpx.get('http://localhost:8000/api/v1/usage/quota/check?tenant_id=1&usage_type=api_call&quantity=1001')
print('  Over limit (1001): %s - %s' % (r.status_code, 'PASS' if r.status_code == 429 else 'FAIL'))

r = httpx.get('http://localhost:8000/api/v1/usage/quota/check?tenant_id=999&usage_type=ai_tokens&quantity=1000')
print('  No tenant (404): %s - %s' % (r.status_code, 'PASS' if r.status_code == 404 else 'FAIL'))

# PROBE 3: Stripe Checkout
print()
print('PROBE 3: Stripe Checkout flow')
r = httpx.post('http://localhost:8000/api/v1/billing/checkout', 
    json={'tenant_id': 1, 'plan_name': 'pro', 'success_url': 'http://localhost:8000/billing/success', 'cancel_url': 'http://localhost:8000/billing/cancel'})
print('  Checkout: %s - %s' % (r.status_code, 'PASS' if r.status_code == 200 else 'FAIL'))
if r.status_code == 200:
    data = r.json()
    print('  Session ID: %s...' % data.get('session_id', 'N/A')[:20])
    print('  Checkout URL: %s' % ('PASS' if data.get('checkout_url', '').startswith('https://checkout.stripe.com') else 'FAIL'))

# PROBE 4: Webhook Security
print()
print('PROBE 4: Webhook Security')
r = httpx.post('http://localhost:8000/api/v1/billing/webhooks/stripe',
    json={'type': 'checkout.session.completed', 'id': 'evt_test', 'data': {'object': {}}},
    headers={'stripe-signature': 'invalid-signature'})
print('  Forged signature (400): %s - %s' % (r.status_code, 'PASS' if r.status_code == 400 else 'FAIL'))

# PROBE 5: Pricing Rules
print()
print('PROBE 5: AI Token Pricing Rules')
from app.services.pricing import pricing_calculator

# Test cached input cheaper
b1 = pricing_calculator.calculate_token_cost(input_tokens=1000000, cached_input_tokens=0, output_tokens=0, reasoning_tokens=0)
b2 = pricing_calculator.calculate_token_cost(input_tokens=0, cached_input_tokens=1000000, output_tokens=0, reasoning_tokens=0)
print('  1M fresh input: %s cents' % b1.input_cost_cents)
print('  1M cached input: %s cents' % b2.cached_input_cost_cents)
print('  Cached cheaper: %s' % ('PASS' if b2.cached_input_cost_cents < b1.input_cost_cents else 'FAIL'))

# Test reasoning = output rate
b3 = pricing_calculator.calculate_token_cost(input_tokens=0, cached_input_tokens=0, output_tokens=1000000, reasoning_tokens=0)
b4 = pricing_calculator.calculate_token_cost(input_tokens=0, cached_input_tokens=0, output_tokens=0, reasoning_tokens=1000000)
print('  1M output: %s cents' % b3.output_cost_cents)
print('  1M reasoning: %s cents' % b4.reasoning_cost_cents)
print('  Reasoning = output rate: %s' % ('PASS' if b3.output_cost_cents == b4.reasoning_cost_cents else 'FAIL'))

# Test rollup pricing
r = httpx.get('http://localhost:8000/api/v1/usage/rollup?tenant_id=1')
print('  Rollup: %s - %s' % (r.status_code, 'PASS' if r.status_code == 200 else 'FAIL'))

print()
print('=' * 60)
print('ALL PROBES COMPLETED')
print('=' * 60)