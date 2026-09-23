# Independent-review handoff for the formal W2–W8 sequence

**Protocol:** `cffeps-flexpart-successor-holdout-2026-v1`  
**Candidate:** `w1-2023-successor-central-v1`  
**Prepared:** 2026-07-27  
**Current authority:** no holdout execution; production writes disabled

## Purpose

This handoff is for two people who are independent of implementation:

1. an emissions/plume-science reviewer; and
2. an air-quality/model-evaluation reviewer.

The pre-execution review is a scientific control, not an administrative
rubber stamp. The central W2, W3, and W4 outputs and all W6 candidate outputs
remain closed until both required roles issue favourable, artifact-specific
decisions and every blocking issue is resolved.

## Review order

1. Read the protocol, consolidated execution plan, and formal execution
   record.
2. Verify every SHA-256 in `source-and-build-manifest.json` against the
   referenced file.
3. Review the issue-disposition ledger. Do not change a blocking issue to
   non-blocking merely to permit execution.
4. Reproduce the small software fixtures and inspect the W5 numerical
   evidence.
5. Complete the role-specific work below without opening candidate output.
6. Write a reviewer-controlled signoff using the supplied JSON template.
   Copy the complete artifact-hash mapping from the package manifest
   verbatim.
7. Run `scripts/verify_smoke_reviewer_signoffs.py`. Holdout execution is
   authorized only if that gate and the separate Phase-0 preflight both pass.

## Emissions/plume-science review

The reviewer must independently:

- inspect all 16 frozen MISR/MINX overpasses;
- freeze the plume/band selection, source attribution, polygon, terrain,
  wind-correction, valid-point, overlap, and rejection rules;
- confirm that no candidate height or performance entered selection;
- decide whether the documented viewing of one raw MINX header compromises
  the prospective blind;
- review the Fire M3 location/time assignment and fuel/CFFDRS-state mapping;
- review the MCD64A1 occurrence, ambiguity, QA, uncertainty, and burned-area
  operator;
- freeze a causal pre-overpass emission-history rule, including the burn-date
  uncertainty, spin-up interval, and evolution of fire-weather state; and
- reproduce the normalized historical GFS profile and FLEXPART-input
  interface on at least one frozen case.

### W3 machine dossier added 2026-07-27

The implementation author has completed a height-blind machine analysis and
causal CFFEPS source construction. Read
[the complete methods and results record](progress/2026-07-27-w3-blind-observation-and-causal-emissions.md)
before disposition. Reproduction commands and exact operator parameters are in
the [W3 reproduction runbook](w3-reproduction-runbook-2026-07-27.md), and
artifact schemas plus the complete 16-case disposition are in the
[W3 data dictionary](w3-artifact-data-dictionary-2026-07-27.md).

### Expanded W3 availability dossier added 2026-07-27

The original 16-case cohort remains immutable, but it is no longer the full
statement of MISR availability. Read
[the expanded 2017-current inventory](progress/2026-07-27-w3-expanded-misr-2017-current.md).
The publication-facing claims and limitations are in the
[expanded MISR publication update](w3-expanded-misr-publication-update-2026-07-27.md).
The exhaustive MERLIN screen found 109 observation-qualified fire-overpass
candidates. Of these, 88 also have complete Fire M3 state/fuel and independent
MCD64A1 area inputs, across 37 MISR orbits.

These 88 records are not yet execution-authorized. Before selecting a central
cohort, the reviewer must:

- freeze a physical-fire/complex clustering rule so plume families in one
  orbit or nearby source detections are not counted as independent fires;
- review the provisional 250 m AGL and 10-valid-retrieval rule without using
  its resulting sample count;
- freeze a performance-blind central/reserve selection, targeting at least 20
  central cases and limiting concentration within any one fire complex;
- verify that the central cohort still contains at least 10 independent
  fire-overpasses after clustering;
- acquire and reproduce historical GFS only after that freeze; and
- reproduce the time-causal Fire M3/MCD64A1/CFFEPS construction without
  permitting observations after overpass to influence releases.

The reviewer must specifically decide:

- whether the provisional `250 m AGL` floor and minimum of 10 valid retrievals
  are scientifically justified without reference to the resulting sample
  count;
- whether the blue-first `Good`/`Fair` land-smoke rule and prohibition on
  post-extraction red-band fallback are acceptable;
- whether the earlier viewing of one MINX header requires retiring the cohort;
- whether final MCD64A1 may be used under the explicit
  retrospective-physical-causality label;
- whether Fire M3's latest-prior-state rule, 5 km radius, 24-hour state
  lookback, and no-state/no-release treatment are acceptable; and
- whether conservative hourly CFFEPS omissions, cumulative area only through
  each source hour, and the absence of active-interval area redistribution are
  appropriate.

The immutable original-cohort machine intersection is 6 overpasses, below the
formal minimum of 10. Do not change a threshold to restore the minimum on that
already processed cohort. The expanded pool is the prospective replacement:
freeze its scientifically justified observation and clustering operators
before choosing the central cases or opening model output.

If the blinding deviation is unacceptable, retire the current W3 cohort and
freeze a new prospective cohort. Do not replace cases based on agreement with
the model.

## Air-quality/model-evaluation review

The reviewer must independently:

- inspect the final-NAPS source, revision, methods, units, flags, and station
  coordinate histories;
- review the performance-blind Fire M3 exclusion rule;
- add and freeze exclusions for documented instrument
  maintenance/calibration and known non-wildfire exceptional events;
- confirm that NAPS concentration magnitudes and candidate output were not
  consulted when producing exclusions;
- review the exact station-hour pairing, background, minimum-data,
  zero-floor, model-cell, layer, and time operators; and
- reproduce the W2/W4 metric and clustered-bootstrap fixtures.

## Required decisions

At pre-execution stage each role must choose exactly one:

- `approve_for_prospective_execution`;
- `approve_with_non_blocking_comments`; or
- `revise_before_execution`.

Only the first two are favourable. Reviewers must record their identity,
affiliation, relevant expertise, conflict disclosure, access limitations,
attribution/publication expectations, rationale, UTC signing time, and
reviewer-controlled attestation method.

After all central and sensitivity experiments, both reviewers must conduct a
second results-and-claims review. A reviewed model release can be issued only
after both final decisions are favourable and every blocking issue is closed.
Only that reviewed release may enter W8.

## W8 timing rule

The W8 rehearsal is uncounted and occurs after final W7 acceptance. Its
timing policy is then frozen. The four counted cycles must be four genuinely
elapsed, consecutive announced schedule windows; timestamps cannot be
backfilled or simulated. Every cycle retains its input availability,
attempt/output, verification, latency, failure, retry, and no-production-write
evidence.
