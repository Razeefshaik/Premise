---
authors: [p_jun]
---
# Runbook: payments on call

## Charge failures
Check paymentservice latency first, then checkoutservice timeouts.

## Refund mismatches
refundworker computes refunds from paymentservice charge records. A mismatch usually means a charge record is missing or doubled.
