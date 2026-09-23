# March–May 2026 validation protocol v2 amendment

**Protocol ID:** `cffeps-flexpart-external-validation-2026-07-24-v2`  
**Status:** frozen before a successful MCD64A1 area result or any candidate-model output  
**Frozen:** 2026-07-24 12:49:05 UTC (09:49:05 ADT)  
**Parent protocol:** [`smoke-validation-protocol-2026.md`](smoke-validation-protocol-2026.md)  
**Area configuration:** [`../config/smoke/mcd64a1_area_v2.yaml`](../config/smoke/mcd64a1_area_v2.yaml)  
**Candidate configuration:** [`../config/smoke/validation_candidate_2026_v2.yaml`](../config/smoke/validation_candidate_2026_v2.yaml)  
**Evaluation gates:** [`../config/smoke/validation_2026_v2.yaml`](../config/smoke/validation_2026_v2.yaml)

## Reason for the amendment

The first v1 area attempt failed while loading MCD64A1, before it could create
an event-area result. At global sinusoidal cell `(11087, 22254)`, one monthly
granule reported a burn date of 2026-04-24 and another reported 2026-05-23.
The v1 operator keyed accepted observations by spatial cell alone and required
every cross-month classification at that cell to be identical. That assumption
cannot represent two temporally distinct burn occurrences at one 500 m cell.

The failure exposed an input-model defect, not a poor candidate score. No
CFFEPS emissions, FLEXPART result, GFAS comparison, TROPOMI matchup, surface
matchup, or evaluation metric existed when this amendment was specified.

## Amended occurrence rule

Operator `mcd64a1-event-area-v2` identifies an accepted burn occurrence by:

```text
(global sinusoidal row, global sinusoidal column, reported burn date)
```

The following rules are frozen:

1. Two records with the same cell and burn date must have identical
   uncertainty, QA, and reliable-window classification. Identical records are
   deduplicated while retaining both granule names; a classification conflict
   remains a hard error.
2. Records at the same cell with different reported burn dates are retained as
   distinct burn occurrences.
3. Event seeding, connected growth, temporal compatibility, overlap exclusion,
   high-confidence screening, and daily aggregation operate on burn
   occurrences rather than spatial cells.
4. Two distinct occurrences at one cell may both contribute one equal-area
   cell to different dates. This represents mapped reburning, not simultaneous
   duplication.
5. Reports expose both unique spatial-cell and unique burn-occurrence counts,
   exact duplicate counts, and repeat-burn coordinates.

All QA flags, temporal padding, seed radius, eight-neighbour topology, event
identities, country/fuel selection, area strata, candidate settings,
observation operators, metrics, and evaluation thresholds remain unchanged.

## Interpretation

MCD64A1 is a monthly burned-area product whose Burn Date layer describes the
date assigned to a burned grid cell. A multi-month experiment can contain a
later mapped burn at a previously burned coordinate. Collapsing those records
by coordinate loses temporal and area information; counting identical
cross-month records twice inflates it. The v2 occurrence key distinguishes
those cases without consulting candidate output.

This post-registration amendment must be reported in any manuscript. Results
from v1 and v2 must not be pooled or presented as if v2 had been the original
rule.
