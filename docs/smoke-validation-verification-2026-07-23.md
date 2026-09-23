# CFFEPS–FLEXPART verification result — 2026-07-23

## Decision

The corrected central CFFEPS–FLEXPART chain is computationally verified. It is
not yet scientifically accepted under the frozen protocol.

Candidate `november-2025-mcd64a1-central-v2` completed all 24 independent
FLEXPART members, and the independent output verifier passed every recorded
mass, seed, completion, checksum, dimension, time, height, and concentration
check. The source chain conserves the complete MCD64A1 daily burned area and
passes the internal CFFEPS fuel-mass gate. The full software regression suite
also passes.

Scientific acceptance remains false because:

1. only four independently area-supported events are available—two weak, two
   moderate, and no major fire;
2. the diagnostic GFAS inventory comparison fails all three species gates and
   is dominated by a documented event-coverage mismatch;
3. no acceptance-capable MISR plume-height comparison has run;
4. no acceptance-capable hourly NAPS smoke-enhancement comparison has run;
5. the frozen sensitivity matrix is incomplete;
6. the two required independent scientific reviews are unsigned; and
7. four scheduled-cycle executions have not been demonstrated.

This result supports continued controlled validation work. It does not support
removing the production submission lock.

The machine-readable form of this assessment is
[`smoke-validation-verification-2026-07-23.json`](smoke-validation-verification-2026-07-23.json).

## Frozen identities

| Artifact | SHA-256 |
|---|---|
| Protocol, `docs/smoke-validation-protocol.md` | `fc8801b7bcc768dd28b2cca38e6fc770988f96f6ebf839d2e8ea2f129ad46342` |
| Thresholds, `config/smoke/validation.yaml` | `2b789afafb1739cc49d42f9216f8cdd72e416de14da6e08fec1fc84475c31727` |
| Candidate v2 configuration | `3a9832b6be385ff5a4e7f1368de5c05af6e0265c0fc9c96697ef982713951285` |
| Candidate run manifest | `c008b18d52b6dbe494eb1f6bcf6792dd99bde2d6dcb65960038d3e7c7c793fd9` |
| Candidate input manifest | `fb08a49907457503ee3a9389fc00cac24a5443b1660d92b2d406be85b6da2d8e` |
| Normalized emissions bundle | `30128dc48e94bb1406f837e3b47c47d265f6db15899f96de7fd5a4fd7983a74e` |
| FLEXPART output-verification report | `60e7260bbe3962596aa23b3ee911dbacd206941fcb6a1e3b8123095029930c7a` |
| GFAS diagnostic manifest | `917efe5ddb6b893f55ba5c6dea4848b72dcb20959cd8a8f9e6f8f0b7e52bde67` |

The v2 candidate was frozen before its outputs were generated. Its only
scientific change from v1 is the dated amendment that conserves all daily
MCD64A1 area over CFFEPS's 23 active intervals. The GFAS values were not used
to make that correction.

## Independent burned-area support

The frozen MCD64A1 operator decoded all 46 Canada-intersecting granules and
retained 282 QA-accepted burn pixels in the experiment interval. It excluded
two pixels claimed by multiple fire events.

Four of 869 frozen events have unambiguous area support:

| Event | Selected fuel | Area (ha) | Stratum |
|---|---:|---:|---|
| `0d345695144eaf09813a566f` | C3 | 64.3976 | weak |
| `064ab7723737feddb2f8a046` | C4 | 85.8635 | weak |
| `3c1fcc5d180489359985b4d5` | C5 | 107.3293 | moderate |
| `078b2261a884fd95c1e881d3` | C3 | 150.2611 | moderate |

The total area is 407.851479 ha, allocated across ten event-days. Every source
run assigns its complete requested daily increment. Because the sample has no
major event and does not reach three events in any stratum, it fails the
preregistered population design.

## Source and transport verification

Ten CFFEPS 4.1 source runs completed. Their maximum relative disagreement
between summed hourly phase fuel and the model's cumulative consumed-fuel
diagnostic is 0.006361, comfortably inside the frozen 0.05 gate. Total emitted
mass is:

| Species | Emitted mass (kg) |
|---|---:|
| PM2.5 | 543.3726778 |
| CO | 3,291.5845867 |
| Black carbon | 18.2865871 |

FLEXPART transported every species on each of eight source dates, producing 24
members. Six independent processes were scheduled concurrently; each member
used eight model threads and a distinct deterministic seed. Process scheduling
does not couple the scientific members.

The verified run contains:

- 3,600,000 particles;
- 16,560 release records;
- 24 hourly concentration fields per member;
- nine vertical levels;
- finite, nonnegative, nonzero concentration in every member;
- a successful FLEXPART completion marker in every member;
- exact release-mass agreement with the normalized emissions bundle; and
- matching concentration-file checksums.

The batch wall time was 569.133 seconds.

## GFAS inventory diagnostic

The GFAS comparison is explicitly diagnostic and cannot count as independent
scientific acceptance. For each species it contains 375 active-union
grid-cell-day pairs. The candidate has ten positive source cell-days, while
GFAS has 366 positive cell-days in the frozen domain and interval.

| Species | NMB | Pearson R | FAC2 | Frozen criteria passed |
|---|---:|---:|---:|---|
| PM2.5 | -0.999960 | -0.0339 | 0.000 | No |
| CO | -0.999971 | -0.0345 | 0.000 | No |
| Black carbon | -0.999970 | -0.0348 | 0.000 | No |

The discrepancy is real under the frozen observation operator. Its dominant
known explanation is unequal fire coverage: the candidate intentionally
contains only the four events with independent burned-area support, whereas
the domain-wide GFAS active union contains all GFAS fires. This does not prove
that the four event-level CFFEPS sources are unbiased, and it says nothing
about FLEXPART transport. A defensible follow-up must construct like-for-like
event support or obtain independent areas for all fires; it must not crop the
domain after seeing these results.

## Acceptance-capable observations not yet run

MISR requires at least ten quality-screened plume-height pairs matched to the
eligible events. No such matched polygon/overpass set is present.

NAPS requires at least 100 hourly station smoke-enhancement pairs with a
preregistered local background. The local 2025 integrated reference-method
archive is a 24-hour product and cannot implement that hourly observation
operator. Hourly data and the corresponding smoke-day/background exclusions
are still required.

## Remaining sensitivity and governance work

Without changing event inclusion, the central candidate must be repeated with:

- low and high species emission factors;
- low and high defensible MCD64A1 area/timing realizations;
- alternative mass-conserving vertical injection profiles;
- at least two particle counts;
- one-thread and multithread stochastic comparison;
- median and 20th-percentile NAPS backgrounds; and
- wet/dry deposition enabled and disabled for attribution.

Finally, a wildfire-emissions scientist and an air-quality scientist must sign
the registry and methods, and at least four scheduled validation cycles must
complete inside their cycle windows.

## Regression evidence

After the corrected candidate completed:

```text
pytest: 204 passed, 19 skipped
skips: PostgreSQL integration tests; WEATHER_TEST_DATABASE_URL not configured
CFFEPS: 10 golden cases and 6 FBP sensitivity cases passed
Ruff: all changed validation files passed
uv lock --check: passed
```

## Audit value of failed attempts

All predecessor attempts remain preserved:

- v1 `attempt-001` stopped after a successful single-member timing pilot;
- v1 `attempt-002` was invalidated after the GFAS diagnostic exposed a
  1,000-fold portable-driver unit error; and
- v1 `attempt-003` was invalidated after the source audit exposed a 23/24 daily
  burned-area allocation.

Neither defect was hidden or overwritten. The unit correction is protected by
a CFFEPS fuel-mass gate, and the area correction was issued as a new,
pre-output candidate version. This is evidence that the verification process
is detecting consequential scientific-interface defects rather than merely
confirming that executables terminate.
