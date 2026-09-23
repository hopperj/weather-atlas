# W8 research plan: four scheduled validation shadow cycles

**Blocker:** only one frozen research cycle exists; four scheduled runs have
not completed inside declared cycle windows  
**Dependency:** W5 fixed release and W7 final scientific approval  
**Minimum elapsed time:** four scheduled cycle windows plus one dress rehearsal  
**Output:** immutable four-cycle reliability dossier

## Objective

Demonstrate that the reviewed smoke system can acquire its available
operational inputs, create a validation run, execute CFFEPS/FLEXPART, verify
complete outputs, and publish validation-only artifacts on schedule without
interactive or production writes.

This is an execution-reliability gate. It does not replace external scientific
validation and does not automatically unlock production.

## Existing mechanism

The repository already contains a feature-gated Airflow DAG:

```text
airflow/dags/flexpart_smoke_validation.py
```

It schedules at `09:15 UTC` daily only when
`SMOKE_VALIDATION_RUNS_ENABLED=true`, enqueues `run_kind="validation"`, and is
documented as never unlocking interactive or operational writes.

Use this validation path. Do not enable `SIMULATION_WRITES_ENABLED` for the
four-cycle demonstration.

## Pre-cycle dress rehearsal

Run one explicitly uncounted rehearsal to measure:

- upstream CWFIS/GFS availability by 09:15 UTC;
- queue delay;
- CFFEPS and FLEXPART runtime;
- storage/write time;
- verifier and tiling/publication time;
- notification latency; and
- typical transient failure modes.

Use the rehearsal only to set operational service-level windows and repair
orchestration. It does not count as one of the four cycles and cannot be used
to change scientific settings.

Freeze the cycle SLA, input cutoff, retry policy, and success criteria after
the rehearsal and before cycle 1.

## Proposed frozen cycle window

Subject to rehearsal evidence, start with:

- scheduled enqueue: 09:15 UTC;
- enqueue tolerance: by 09:30 UTC;
- upstream input cutoff: explicitly declared per provider/product;
- terminal verified state: within 6 hours of scheduled enqueue;
- no more than one active validation run;
- immutable attempt directory for every try; and
- cycle result emitted before the next daily schedule.

These values are proposed, not yet preregistered. If upstream data routinely
arrive later, choose a later fixed schedule before cycle 1 rather than granting
ad hoc extensions.

Require four **consecutive** counted cycles to pass. A failed counted cycle
remains failed and restarts the consecutive count after the cause is resolved.
This is stricter and clearer than selecting four successes from many attempts.

## Scientific configuration

Tag and freeze one reviewed release containing:

- CFFEPS executable and patch identities;
- FLEXPART executable and W5 fix;
- emission-factor registry;
- fuel crosswalk and CFFDRS sampling;
- operational event/area method;
- GFS meteorology preparation;
- species and deposition settings;
- particle budget, thread count, seeds/seed policy;
- domain/grid/output levels;
- output verifier; and
- Airflow/container/config identities.

Operational near-real-time area may differ from final MCD64A1 validation area
because monthly burned-area products are delayed. Declare the operational area
operator and its scientific status. The shadow cycles demonstrate reliable
execution of that frozen operational candidate; final historical scientific
accuracy remains supported by W1–W6.

## Cycle success criteria

Every counted cycle must:

1. start inside the frozen window;
2. freeze all available inputs at the cutoff and record missing/late products;
3. create one immutable validation run and attempt ID;
4. pass input schema, unit, time, spatial, and checksum validation;
5. complete every expected CFFEPS source and FLEXPART member, or correctly
   complete a preregistered no-fire cycle;
6. pass the schema-v2 whole-output verifier for concentration, wet deposition,
   and dry deposition;
7. preserve release/source mass equality and unique seeds;
8. build expected map/visualization artifacts if part of the reviewed release;
9. finish inside the SLA;
10. write metrics and status to the validation namespace only; and
11. emit an alert/status record without manual intervention.

Define a no-fire cycle before cycle 1. It should be a valid verified
`no_eligible_fire` outcome rather than fabricate a release, but four no-fire
cycles would not exercise transport. Require at least two of the four counted
cycles to contain one or more transported fire members. If fire activity is
insufficient, schedule counted cycles during a more active period or use
predeclared real-time replay cycles with fixed wall-clock windows.

## Retry and failure policy

Classify failures:

- **provider unavailable/late;**
- **input invalid/incomplete;**
- **orchestration/infrastructure;**
- **model nonzero exit;**
- **scientific output invalid;**
- **verification/publication;**
- **SLA miss.**

Automatic retry is allowed only under the frozen retry policy and always
creates a new attempt record. A retry does not erase the first failure. Manual
data substitution, config change, or result edit invalidates that cycle.

If a scientific output is non-finite or violates mass integrity, stop the
counted sequence and reopen W5/W6 as appropriate.

## Monitoring and evidence

Capture:

- Airflow logical date, scheduled/start/end times, task attempts, host/container;
- queue and task durations;
- input availability and cutoff decision;
- database run/scenario IDs;
- every input/config/executable/output checksum;
- member count, particles, releases, and source mass;
- full verifier result;
- output and visualization manifests;
- alert delivery;
- storage use and cleanup status; and
- any operator intervention.

Add a dashboard/table with one row per logical cycle and immutable links to
attempt evidence.

## Implementation plan

Extend the validation DAG and operational state carefully:

```text
airflow/dags/flexpart_smoke_validation.py
python/weather_ingest/smoke_operational.py
scripts/verify_smoke_validation_candidate.py
```

Add:

```text
python/weather_ingest/smoke_cycle_assessment.py
scripts/build_smoke_cycle_assessment.py
airflow/tests/test_flexpart_smoke_validation.py
tests/ingestion/test_smoke_cycle_assessment.py
```

The cycle assessor should read manifests and orchestration timestamps rather
than accept a manually entered “passed” flag. It must verify that writes
remained in the validation namespace and that the production feature lock did
not change.

Add an environment preflight that reports required variables without printing
their secret values.

## Required artifacts

```text
scheduled-cycles/
  cycle-protocol.md
  cycle-protocol.yaml
  release-manifest.json
  rehearsal/
  cycle-001/
    logical-cycle.json
    attempts/
    assessment.json
  cycle-002/
  cycle-003/
  cycle-004/
  four-cycle-summary.json
  incident-ledger.json
  reviewer-signoff.json
```

## Definition of done

- One uncounted rehearsal established the frozen schedule/SLA.
- One reviewed model/container/config release was used unchanged.
- Four consecutive counted cycles passed every success criterion.
- At least two counted cycles executed real fire transport.
- Every cycle completed inside its frozen window.
- Attempts and failures are immutable and visible.
- No interactive or production simulation write was enabled.
- The four-cycle summary is machine-generated and independently reviewed.
- A human governance step, not the DAG, decides whether the production lock
  can later change.

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| Upstream data arrive after 09:15 UTC | Measure in rehearsal and freeze a later schedule before cycle 1 |
| Four cycles have no fires | Run during active season or use preregistered real-time replay windows |
| Retry hides first failure | Immutable attempt IDs and cycle-level assessment |
| Manual intervention becomes necessary | Mark cycle failed, fix cause, restart consecutive count |
| Validation accidentally writes production state | Namespace assertion and database/API integration test |
| Feature flag changes automatically | Prohibit in code and verify environment/config hashes each cycle |

## Execution checklist

- [ ] Complete W5 and W7 and tag the reviewed release.
- [ ] Add cycle assessor and validation-namespace assertions.
- [ ] Run Airflow/DAG/database integration tests.
- [ ] Perform one uncounted rehearsal.
- [ ] Freeze schedule, SLA, input cutoff, retries, and no-fire rules.
- [ ] Announce the four counted logical dates before cycle 1.
- [ ] Execute cycles without config or code changes.
- [ ] Restart count after any failed cycle.
- [ ] Generate machine four-cycle summary.
- [ ] Obtain independent operational/reproducibility review.
- [ ] Feed the dossier into a new human-reviewed acceptance assessment.
