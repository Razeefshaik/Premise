---
authors: [p_sofia]
updated: 2026-10-09
---
# Runbook: email delivery budget

## Bound the attempts
emailservice currently allows five attempts; the external provider allows ten.
ADR-011 promises G_EMAIL_WITHIN_BUDGET through A_EMAIL_BUDGET. Eight attempts stay within
that recorded limit; eleven do not. The provider limit is an external fact.

## Diagnose a delayed message
Record the message identifier, attempt number, provider response and queue age. Confirm
the effective attempt limit before changing backoff. This model checks the attempt count,
not wall-clock delivery time or whether a message was actually delivered.

## Ownership
Sofia owns this runbook. The platform team owns emailservice. Link an incident to the
relevant source evidence so later reviewers can distinguish a policy from a past observation.
