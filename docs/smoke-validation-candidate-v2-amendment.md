# November 2025 validation candidate v2 amendment

**Candidate:** `november-2025-mcd64a1-central-v2`  
**Frozen:** 2026-07-23 20:16:08 UTC, before any v2 output was produced  
**Configuration:** `config/smoke/validation_candidate_v2.yaml`  
**Configuration SHA-256:** `3a9832b6be385ff5a4e7f1368de5c05af6e0265c0fc9c96697ef982713951285`

## Reason for the new version

Candidate v1 defined a linear cumulative burned-area curve from 00:00 through
24:00 UTC. The portable CFFEPS execution initializes at its first profile and
produces no phase fuel at that step, leaving 23 active hourly phase intervals.
The original adapter evaluated the requested curve only at intervals with
phase rows. It therefore allocated exactly 23/24, or 95.8333%, of every
MCD64A1 daily area increment.

This was found by an explicit daily-area conservation check while v1
`attempt-003` was still running. That attempt was stopped and excluded. The
error was not inferred from, or calibrated against, the GFAS score.

## Amended temporal operator

V2 retains the 00:00–24:00 UTC linear curve as the daily target but adds a
mass-conserving observation operator:

1. evaluate the target curve across every active CFFEPS phase interval;
2. sum the initially assigned area increments;
3. multiply every positive active-interval increment by
   `requested daily increment / initially assigned increment`; and
4. require the final assigned sum to equal the complete MCD64A1 daily
   increment.

For this candidate, the normalization is exactly `24/23`. The operation
preserves the relative CFFEPS hourly phase pattern and the full independent
daily area, but places no release in CFFEPS's initialization hour. This
one-hour support limitation must be reported in any manuscript.

## Unchanged design

The MCD64A1 area operator, four selected events, ten event-days, fuel
selection, CWFIS fire-weather fields, GFS meteorology, CFFEPS factors and plume
profile, FLEXPART physics, domain, grid, 150,000 particles per species-day,
random-seed policy, species isolation, GFAS pair operator, protocol, and frozen
evaluation thresholds are unchanged from v1.

V1 artifacts remain immutable evidence of the two verification failures. No
v1 output is counted toward the v2 result.
