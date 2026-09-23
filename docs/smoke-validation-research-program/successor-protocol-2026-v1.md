# CFFEPS–FLEXPART successor holdout protocol, 2026 v1

**Protocol ID:** `cffeps-flexpart-successor-holdout-2026-v1`  
**Status:** technically frozen; prospective independent review required  
**Production writes:** disabled

> **Scope update, 2026-07-27:** This v1 protocol and its original 16-case W3
> artifacts remain immutable. An exhaustive 2017-current MERLIN inventory has
> identified 88 source-area-qualified candidates across 37 orbits. That pool
> is not automatically incorporated into v1. A physical-fire clustering rule,
> central/reserve selection, independent review, complete inputs, and a new
> immutable protocol/package freeze are required before it replaces the
> original cohort. See the
> [expanded MISR publication update](w3-expanded-misr-publication-update-2026-07-27.md).

This protocol implements the W2, W3, W4, W6, W7, and W8 execution plan. Its
machine-readable source is
`config/smoke/validation_successor_2026_v1.yaml`. All selection, observation,
pairing, rejection, statistics, sensitivity, and invalidation rules are
frozen before held-out FLEXPART output is opened.

## Cohorts and firewall

W2 uses the retained/reserve 2023 input-only source cohort. W3 uses the
prospectively catalogued 2017–2018 MISR MINX overpasses that survive
input-only fire assignment and completeness review. W4 uses final 2023 NAPS
station-hours selected through the frozen station and model-signal operators.
GFAS, MINX height, NAPS concentration, and candidate output cannot select a
source event or seed CFFEPS/FLEXPART.

## Primary experiments

- W2 compares PM2.5, CO, and BC at grid-cell-day resolution. The full-domain
  active-union operator is central; an independently burned-area-supported
  mask and one-cell dilation provide the preregistered coverage analysis.
- W3 compares the median wind-corrected MINX AGL height for one plume-overpass
  with area- and time-weighted FLEXPART PM2.5 mass-weighted mean AGL height.
- W4 compares final NAPS smoke enhancement with the exact interval-end
  FLEXPART 0–50 m containing-cell value. Background is the same-station,
  same-UTC-hour median over ±14 days, with at least seven eligible values.

The exact numerical gates and deterministic bootstrap seeds are in the
machine-readable protocol and are not repeated by downstream evaluators.

## Sensitivity, failures, and review

The W6 matrix is one-factor-at-a-time except for the explicit four-case
deposition factorial. Every attempt is immutable. A favourable sensitivity
cannot replace a failed central result. Any central failure is reported,
diagnosed outside the holdout, and may motivate a newly frozen future
holdout.

Two independent reviewers—one in emissions/plume science and one in
air-quality/model evaluation—must approve the artifact hashes before
execution and again after inspecting all results, failures, exclusions, and
claims. The software validates their signoffs but cannot create them.
