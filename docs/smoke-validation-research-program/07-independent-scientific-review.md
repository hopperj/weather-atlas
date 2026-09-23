# W7 research plan: independent scientific review

**Blocker:** wildfire-emissions and air-quality methods/results are unsigned  
**Dependency:** draft review can begin during W1/W5; final sign-off requires
W2, W3, W4, and W6  
**Estimated calendar time:** 2–6 weeks, dominated by reviewer availability  
**Output:** signed review records and a closed issue-disposition ledger

## Objective

Obtain independent expert assessment that:

- the source-emissions and plume-rise design is scientifically defensible;
- the surface/vertical observation operators and statistics are appropriate;
- the conclusions do not exceed the evidence;
- protocol changes and failures are transparently reported; and
- no production acceptance is granted while blocking scientific issues remain.

Review is a scientific governance gate, not a ceremonial signature.

## Required reviewers

### Wildfire-emissions reviewer

Minimum relevant expertise:

- Canadian FBP/FWI or comparable fire-behaviour systems;
- burned-area and fuel-consumption uncertainty;
- fire emission factors and combustion phases;
- plume rise/injection; and
- inventory intercomparison.

### Air-quality/model-evaluation reviewer

Minimum relevant expertise:

- surface PM2.5 monitoring and QA;
- smoke-background estimation;
- satellite/lidar aerosol vertical products;
- atmospheric transport-model evaluation;
- dependence-aware statistics and uncertainty.

Reviewers should not have authored the implementation being accepted. A
collaborator may review if the relationship and conflict are disclosed, but at
least one reviewer should be institutionally independent when practical.

Optionally recruit a third reproducibility/numerical reviewer for W5, build
identity, manifests, and rerun instructions.

## Recruitment package

Prepare a two-page invitation containing:

- system and intended use;
- exact decision they are being asked to review;
- expected time and schedule;
- public/private status of data and code;
- conflict-of-interest request;
- publication/co-authorship policy;
- confidentiality and attribution preference; and
- a clear statement that “approve with blocking conditions” is acceptable.

Do not imply that reviewers are expected to endorse operational deployment.

## Review stages

### Stage 1: protocol review before holdout output

Both reviewers receive:

- successor protocol and amendments;
- acceptance evidence matrix;
- cohort selection/availability ledger;
- event inclusion/exclusion rules;
- observation operators;
- thresholds and statistical analysis plan;
- sensitivity matrix;
- software/model build identity; and
- data-management and publication plan.

Required decision:

```text
approve for prospective execution
approve with non-blocking comments
revise before execution
```

Holdout output cannot be opened until every “revise before execution” item is
closed.

### Stage 2: methods and implementation review

Review:

- MCD64A1/VNP64A1 occurrence and uncertainty operators;
- fire-state and fuel selection;
- CFFEPS finite-window mass accounting;
- emission-factor registry;
- vertical injection;
- FLEXPART physics/species/deposition;
- GFAS support/coverage operator;
- MISR/lidar matching;
- NAPS background and pairing;
- metric implementations; and
- numerical fix and complete-output verifier.

Provide small reproducible fixtures and code links rather than only prose.

### Stage 3: result and interpretation review

After immutable evaluations exist, reviewers inspect:

- complete central and sensitivity results;
- failed and excluded attempts;
- event/station/plume influence;
- uncertainty and coverage attribution;
- publication methods/results draft;
- machine acceptance assessment; and
- proposed permitted/prohibited claims.

Required final status:

```text
approved
approved with non-blocking limitations
not approved
```

Scientific acceptance requires both required reviewers to approve and zero
open blocking comments.

## Standard review questions

### Emissions/plume reviewer

1. Is area independent of candidate emissions and correctly matched to events?
2. Are fuel, FFMC/DMC/DC, and mixture parameters defensible?
3. Does finite-window mass accounting distinguish consumed, released, queued,
   and unaccounted fuel correctly?
4. Are species factors and units scientifically supported?
5. Is the 12-layer injection operator appropriate for the claimed scope?
6. Is the GFAS comparison like-for-like and free from circular seeding?
7. Are area, factor, timing, and injection sensitivities plausible?

### Air-quality reviewer

1. Are MISR/lidar and FLEXPART vertical quantities comparable?
2. Are plume, terrain, time, and QA operators defensible?
3. Is the final NAPS archive and method/instrument screening appropriate?
4. Does the background exclude other smoke without using model performance?
5. Are model/station matching, units, and interval conventions correct?
6. Are thresholds, dependence treatment, and uncertainty reports appropriate?
7. Do conclusions distinguish primary PM2.5 from total ambient aerosol?

### Both

1. Were cohorts frozen without performance selection?
2. Are exclusions complete and auditable?
3. Could compensating component errors explain a passing end-to-end result?
4. Does any sensitivity reverse the conclusion?
5. Are claims narrower than or equal to the evidence?
6. Should the system remain locked?

## Issue management

Store each comment with:

- stable issue ID;
- reviewer and review stage;
- file/section/code reference;
- severity: blocking, major non-blocking, minor, editorial;
- requested evidence/change;
- owner and due date;
- response and artifact hash;
- reviewer disposition; and
- closed timestamp.

The implementation team cannot unilaterally downgrade a reviewer-marked
blocking item. Disagreement is recorded, and either the reviewer closes it or
an agreed third expert adjudicates.

Scientific changes made in response to post-result review require a new
candidate/holdout. Editorial clarification may update documentation without a
rerun if it does not alter methods or interpretation.

## Reproducibility package

Reviewers receive:

```text
review-package/
  README.md
  protocol/
  acceptance-evidence-matrix.yaml
  source-and-build-manifest.json
  cohort-ledgers/
  methods/
  evaluation-reports/
  sensitivity-reports/
  failed-attempt-ledger/
  software-verification.json
  reproduction-commands.md
  permitted-and-prohibited-claims.md
```

Large licensed data may remain in controlled storage, but reviewers must be
able to inspect manifests and derived pairs. Record any data they could not
access.

## Sign-off record

For each reviewer archive:

- name, affiliation, expertise;
- ORCID or stable professional identity if they agree;
- conflict disclosure;
- materials and artifact hashes reviewed;
- review dates;
- final status;
- remaining non-blocking limitations;
- signature or authenticated written approval; and
- permission for acknowledgement or co-authorship.

A reviewer signature confirms their review conclusion, not ownership of all
code or data.

## Publication ethics

Agree before review on:

- whether methodological contribution merits co-authorship;
- acknowledgement wording;
- access to manuscript drafts;
- handling of dissent;
- data/code availability statement; and
- embargo or provider-licence constraints.

Do not offer authorship merely in exchange for approval.

## Definition of done

- One qualified emissions reviewer and one qualified air-quality reviewer are
  documented.
- Conflicts and inaccessible materials are disclosed.
- Both approved the prospective protocol before holdout output.
- Every blocking comment has a traceable disposition and is closed.
- Both approve the final methods, results, limitations, and acceptance
  assessment.
- Signed records include the exact artifact hashes reviewed.
- Non-blocking limitations appear in the publication record.

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| Reviewer recruitment delays | Recruit during W1/W5; provide scoped schedule and concise package |
| Reviewer cannot access large/licensed data | Supply checksummed derived pairs and arranged controlled access |
| Review produces scientific changes after results | Create a new model/candidate and new holdout; do not patch the result |
| Conflict of interest | Disclose it and add an independent third reviewer |
| Informal email approval is ambiguous | Use a standard decision form with artifact hashes |

## Execution checklist

- [ ] Draft reviewer role descriptions and conflict policy.
- [ ] Recruit emissions and air-quality reviewers.
- [ ] Assemble Stage 1 protocol package.
- [ ] Close all pre-execution blocking comments.
- [ ] Record approval to open holdout output.
- [ ] Provide implementation fixtures and result package.
- [ ] Track every comment in the issue ledger.
- [ ] Close all final blocking comments.
- [ ] Archive signed artifact-specific approvals.
- [ ] Add limitations and acknowledgements to the manuscript record.
