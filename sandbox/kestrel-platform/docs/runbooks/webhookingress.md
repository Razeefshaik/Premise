---
authors: [p_anika]
---
# Runbook: webhookingress

## Duplicate confirmations
If paymentservice reports a duplicate confirmation, check the dedupe store in the shared Redis cluster.
Paylane retries for the length of its retry window; our dedupe records must outlive it.

## Slow acknowledgements
webhookingress must acknowledge before Paylane's delivery timeout, otherwise Paylane retries.
