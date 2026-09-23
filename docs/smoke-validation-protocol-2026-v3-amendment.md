# March–May 2026 validation protocol v3 amendment

**Protocol ID:** `cffeps-flexpart-external-validation-2026-07-24-v3`  
**Status:** frozen before any v3 candidate output  
**Frozen:** 2026-07-24 12:56:13 UTC (09:56:13 ADT)  
**Parent protocol:** [`smoke-validation-protocol-2026-v2-amendment.md`](smoke-validation-protocol-2026-v2-amendment.md)  
**Candidate configuration:** [`../config/smoke/validation_candidate_2026_v3.yaml`](../config/smoke/validation_candidate_2026_v3.yaml)  
**Evaluation gates:** [`../config/smoke/validation_2026_v3.yaml`](../config/smoke/validation_2026_v3.yaml)

## Reason for the amendment

The v2 candidate's first CFFEPS event-day failed the portable adapter's
fuel-mass check before FLEXPART was prepared. The 24 hourly phase outputs
contained 1,220.575896 t of fuel while CFFEPS reported 1,325.131590 t of
cumulative consumption, a 7.8902% difference.

Inspection of the unmodified CFFEPS 4.1 kernel showed that phase fuel is stored
in future-time queues according to flaming, smouldering, and residual
residence times. At the end of a finite 24-hour driver window, part of the
fuel already included in cumulative consumption can remain in queue for later
combustion. The v2 adapter compared released-within-window fuel to cumulative
fuel without including that pending queue. This was a mismatched accounting
boundary, not evidence that the portable driver's 1,000-fold unit
normalization was wrong.

The v2 attempt is preserved as a failed candidate. It produced no FLEXPART
output and no observation metric.

## Amended mass-balance rule

The portable driver now reports, without changing the CFFEPS kernel, the
flaming, smouldering, and residual fuel remaining in the queue after each
output hour. The hard unit-integrity check is:

```text
sum(phase fuel released during the window)
+ phase fuel pending after the final hour
= CFFEPS cumulative consumed fuel
```

The unchanged 5% relative-difference tolerance applies to that closed balance.
This still detects an incorrect phase-unit scale because both released and
pending queues share the same portable conversion while the independent
cumulative field does not.

The central transport horizon remains the preregistered 24 hours. Only phase
mass released inside that horizon enters FLEXPART. Final pending fuel and its
fraction of cumulative consumption are mandatory provenance and are reported
as finite-window truncation, not silently called emitted mass. No pending
mass is moved into an earlier hour or assigned an invented injection height.

This amendment corrects the bookkeeping interpretation but does not solve
continuous multi-day smoke carry-over. A later operational candidate should
run CFFEPS and FLEXPART continuously across day boundaries so queued
combustion and transported smoke persist. The current isolated 24-hour
experiment is suitable only for its declared finite-window diagnostics.

All event identities, burned areas, fuels, CFFDRS values, GFS profiles,
in-window CFFEPS phase rates, injection calculation, FLEXPART configuration,
observation operators, and evaluation thresholds remain unchanged.
