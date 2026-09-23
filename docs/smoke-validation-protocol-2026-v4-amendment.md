# March–May 2026 validation protocol v4 amendment

**Protocol ID:** `cffeps-flexpart-external-validation-2026-07-24-v4`  
**Status:** frozen before any v4 candidate output  
**Frozen:** 2026-07-24 13:05:20 UTC (10:05:20 ADT)  
**Parent protocol:** [`smoke-validation-protocol-2026-v3-amendment.md`](smoke-validation-protocol-2026-v3-amendment.md)  
**Candidate configuration:** [`../config/smoke/validation_candidate_2026_v4.yaml`](../config/smoke/validation_candidate_2026_v4.yaml)  
**Evaluation gates:** [`../config/smoke/validation_2026_v4.yaml`](../config/smoke/validation_2026_v4.yaml)

## Reason for the amendment

The v3 candidate successfully completed eight CFFEPS source days, then failed
before FLEXPART preparation when the official CWFIS FFMC raster was `NoData`
at event `f8bad2a73b535ddc231c97f7` on 2026-04-21. An input-only audit showed the
same missing FFMC state on the event's second source date, 2026-04-22. All
eight source days belonging to the other five events have valid FFMC, DMC, and
DC at the frozen nearest cell.

CFFEPS cannot infer FFMC from DMC/DC or from the hotspot FWI field, and the
protocol did not authorize spatial infilling. Running this event would require
inventing a required model input. The v3 attempt is preserved as invalid and
none of its partial source output counts as a candidate result.

## Amended eligibility execution

The scientific eligibility requirement itself is unchanged: a candidate event
needs all required inputs. Version 4 makes that requirement explicit and moves
the check before candidate output:

1. Start with every MCD64A1 area-qualified event.
2. Require one unique modal supported fuel.
3. Require the event location to lie inside the frozen transport domain.
4. Sample checksum-verified FFMC, DMC, and DC for every positive MCD64A1
   source day using the frozen nearest-cell operator.
5. If any required date or cell is missing, exclude the entire event and
   record every affected date and exact error.
6. Freeze the included values and source-manifest hashes in the input manifest,
   then reuse them during CFFEPS execution.

This is an input-availability exclusion performed without consulting CFFEPS
performance, FLEXPART output, or any observation metric. The excluded event is
not replaced. Its absence further weakens the already failed area-stratum
design.

All remaining event identities, areas, fuels, source dates, state values,
meteorology, CFFEPS/FLEXPART settings, observation operators, and evaluation
thresholds remain unchanged.
