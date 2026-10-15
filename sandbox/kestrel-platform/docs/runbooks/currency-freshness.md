---
authors: [p_tess, p_ravi]
updated: 2026-10-08
---
# Runbook: currency freshness

## Check the cache before extending its lifetime
currencyservice stores rates for 30 minutes. ADR-003 requires A_RATE_TTL and A_RATES_SOURCE
for G_RATES_FRESH. A cache entry younger than an hour does not prove its upstream rate is fresh.

## Evidence review
The provider publication attestation was due for review on September 30. Until an active
person supplies a current attestation in ADR-003, G_RATES_FRESH remains unknown.
Do not extend review dates as an incident workaround; first check the provider publication log.

## Incident evidence
Capture the source publication timestamp, cache insertion timestamp, currency pair and
response timestamp. Ask the platform team to compare those with the authored decision.
