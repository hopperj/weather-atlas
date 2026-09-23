# Results: March–May 2026 CFFEPS–FLEXPART validation

**Experiment:** `gfas-v1.4.2-2026-03-19_2026-05-31`  
**Central candidate:** `march-may-2026-mcd64a1-central-v4`  
**Assessment date:** 2026-07-24  
**Decision:** not scientifically accepted; the simulation-write lock must
remain enabled

## 1. Main result

The central five-event source and transport chain completed and passed every
independent computational and mass-integrity check. It did **not** pass the
frozen scientific acceptance rule.

The strongest reasons are not software termination failures:

- the independent area design contained no major fire and did not meet the
  target number of events in any stratum;
- all three GFAS source diagnostics showed a large low bias under the frozen
  domain-wide active-union operator;
- TROPOMI aerosol height failed the frozen RMSE criterion and is diagnostic,
  not acceptance-capable;
- AirNow had only 14 pairs and failed every central surface criterion, while
  AQS had no paired monitor-hours;
- no acceptance-capable vertical profile or final surface archive was tested;
- the one-thread sensitivity contained two non-finite wet-deposition values;
  and
- independent reviews and four scheduled-cycle demonstrations are incomplete.

The formal machine-readable decision is stored beside the candidate as
`verification/scientific-acceptance-status-v2.json`.

## 2. Event population

MCD64A1 produced six area-qualified events: four weak, two moderate, and zero
major. This failed the preregistered target of three events in each stratum.
One moderate event was then excluded before model execution because the
official CWFIS FFMC raster was `NoData` at its location on both source days.
The retained central candidate therefore contained four weak events and one
moderate event:

| Event ID | Fuel | Latitude | Longitude | Area (ha) | Stratum | Source dates |
|---|---|---:|---:|---:|---|---|
| `29b5a0cf1203e3899a22ae95` | C2 | 60.3718 | -113.0421 | 128.7952 | moderate | May 23–25 |
| `90025884ffeb8e5015ed2c65` | O1A | 51.0942 | -100.9960 | 42.9317 | weak | May 14, 16 |
| `a61807c906e0188a57ffdc04` | M1_75 | 57.0036 | -123.2441 | 21.4659 | weak | May 6 |
| `a78cb090f5961762d3fe2b29` | C3 | 50.7885 | -100.2843 | 21.4659 | weak | Apr 26 |
| `bdf3e7ccc2984a8bbbe3f212` | C3 | 57.0006 | -123.2552 | 21.4659 | weak | May 5 |

Total retained independent area was 236.1245 ha over eight event-days. The
excluded event, `f8bad2a73b535ddc231c97f7`, was not replaced.

## 3. Central source and transport

The central source bundle contained 16,272 normalized release rows and the
following in-window species masses:

| Species | Released mass (kg) |
|---|---:|
| PM2.5 | 111,273.8172 |
| CO | 699,609.7036 |
| Black carbon | 1,927.8362 |

All 24 source-day/species members completed:

| Quantity | Result |
|---|---:|
| Source days | 8 |
| Species | 3 |
| FLEXPART members | 24 |
| Particles | 3,600,000 |
| Release records | 16,272 |
| Output fields | 24 hourly times × 9 heights per member |
| Threads per member | 8 |
| Concurrent independent members | 6 |
| Batch wall time | 265.417 s |

The schema-v2 verifier passed all completion markers, executable identity,
release mass, distinct seeds, file hashes, dimensions, time coordinates,
finite non-negative non-zero concentrations, and finite non-negative
deposition fields. The central run-manifest SHA-256 is
`cd92715ca22f94f23118cc6304dd9c4b8b01fd507b39e54560532b031dc5aa33`;
the schema-v2 verifier SHA-256 is
`a93d60f4c578cf1dd73ce90c6367820493f6c294196e6bcb90505237eed07be2`.

## 4. Finite-window CFFEPS mass accounting

Across the eight event-days, CFFEPS reported 4,054.9270 t of cumulative
consumed fuel. Of this total:

| Accounting term | Tonnes | Fraction |
|---|---:|---:|
| Released inside the 24-hour window | 3,626.9707 | 89.4460% |
| Still queued after hour 24 | 421.1340 | 10.3857% |
| Unaccounted within the 5% event-day gate | 6.8226 | 0.1683% |

Every event-day passed the frozen hard gate. The aggregate unaccounted mass
comes almost entirely from two O1A grass event-days, each exactly at the
kernel's 5% remainder boundary. Queued mass was not moved into the transport
window, so the FLEXPART experiment represents only in-window combustion.
The audit SHA-256 is
`f8e4ca40063c06210154d70d30b26df91d6f96b4ab68c773c15c67dac45e4fd8`.

## 5. GFAS source-inventory diagnostic

The extracted v1.4.2 source-day bundle contained 24 GRIB messages: eight dates
for each of PM2.5, CO, and BC. Each species produced 1,088 active-union
grid-cell-day pairs.

| Species | NMB | Pearson R | FAC2 | Result |
|---|---:|---:|---:|---|
| PM2.5 | -0.9561 | 0.1425 | 0.00184 | fail |
| CO | -0.9705 | 0.1401 | 0.00184 | fail |
| Black carbon | -0.9856 | 0.1433 | 0.00092 | fail |

All three species passed only the minimum pair count and failed the bias,
correlation, and FAC2 criteria. A dominant known cause is unequal population
coverage: the candidate intentionally contains only five independently
area-supported fires, whereas the active-union GFAS field contains all
GFAS-active Canadian cells on those dates.

This result establishes a gross discrepancy under the frozen operator, but it
does not isolate emission-factor error and does not test FLEXPART transport.
A like-for-like fire mask was not introduced after seeing the result.

Key provenance:

- GFAS bundle SHA-256:
  `fc314a88a17bf542efa20a2f71e32d014da43254281f6e29aca5bde32600cfec`
- bundle manifest SHA-256:
  `4a5f437a8969017f868615da129b67f6df812bf9d0dfc24cdc7d70d1bab9bb93`
- pair manifest SHA-256:
  `4748c722b0cec5321740c096984691844a624a0a9f235faf59f9da95c906bd40`

## 6. TROPOMI aerosol-height diagnostic

The frozen operator retained 83 QA-screened satellite pixel/model pairs and
rejected two additional pixels with zero model column mass.

| Metric | Value | Frozen criterion | Result |
|---|---:|---:|---|
| Pair count | 83 | at least 20 | pass |
| Mean bias | -1,140.8 m | -1,500 to 1,500 m | pass |
| RMSE | 2,734.0 m | no more than 2,500 m | fail |
| Pearson R | 0.5160 | at least 0.30 | pass |

The modelled mass-weighted mean height averaged 1,798.3 m AGL and TROPOMI
aerosol mid-height averaged 2,939.1 m AGL. The negative mean bias indicates a
lower modelled vertical distribution under this operator.

The RMSE failure is retained. The 83 rows are clustered satellite pixels, not
83 independent fire events, and TROPOMI's extinction-weighted height is not
strictly equivalent to the FLEXPART mass-weighted statistic. This comparison
is informative but cannot satisfy the acceptance-capable vertical-profile
gate. Pair CSV SHA-256:
`a8d28b82056a8b58318955d35400ac4d5bbf3da2b5052544758d9253f1b41423`.

## 7. Surface PM2.5

### AirNow

The adapter scanned 1,416 hourly files containing 1,419,300,789 bytes. The
frozen spatial/temporal/background operator produced only 14 paired
monitor-hours.

| Background | N | NMB | NMAE | Pearson R | Result |
|---|---:|---:|---:|---:|---|
| Median | 14 | -0.9218 | 1.0457 | -0.4177 | fail |
| 20th percentile | 14 | -0.9750 | 0.9779 | 0.1429 | fail |

The median-background mean modelled enhancement was 0.0307 µg m-3, compared
with 0.3929 µg m-3 observed. Every central criterion failed, including the
minimum sample of 100. The background sensitivity did not reverse the
underprediction. These data are provisional and not acceptance-capable.

The AirNow input file-set SHA-256 is
`7ec3dea8e6b9a84a9d8c946456796aa5e3744841f779ac0716be388169eec96e`;
the median pair CSV SHA-256 is
`54d7dd64a17e7a9869d882679ba6177cdf549dfcc6681a714ef4a69ad5f904cd`.

### AQS

The adapter streamed 2,315,564 records from the 2026 88101 and 88502 archives.
No eligible US monitor coincided with an active model cell and source-day
hour. The result was zero pairs; all 192 model hours lacked an observation in
an active cell. Statistical metrics are therefore not evaluable, and the
100-pair gate fails. The empty pair-table SHA-256 is
`7010b2a02596adad30a9d12689c4e6b2ca53107a32de0f24eeced3fb90eeb22e`.

## 8. Frozen sensitivities

All emission-factor brackets were ordered as intended for all species. Five of
the six sensitivity candidates passed the schema-v2 whole-output verifier.

| One-factor change | Source-mass ratio to central | Concentration normalized L1 | Signed sum difference | R | Whole-output result |
|---|---|---:|---:|---:|---|
| Low emission factors | BC 0.444; CO 0.800; PM2.5 0.782 | 0.2034 | -0.2033 | 0.99992 | pass |
| High emission factors | BC 1.940; CO 1.251; PM2.5 1.290 | 0.2575 | 0.2574 | 0.99993 | pass |
| High-confidence area | all 1.000 | 0.00893 | -0.000006 | 0.99995 | pass |
| Uniform vertical injection | all 1.000 | 0.5600 | 0.1132 | 0.84511 | pass |
| 300,000 particles | all 1.000 | 0.00956 | 0.000113 | 0.99995 | pass |
| One thread | all 1.000 | 0.01186 | 0.00225 | 0.99992 | **fail** |

The high-confidence area curve gave the same source mass as central for the
five retained events, so its small differences are stochastic rerun
differences rather than a meaningful burned-area perturbation. It does not
provide a broad area-uncertainty bracket.

Doubling particles changed the aggregate concentration field by less than 1%
normalized L1. Changing vertical injection produced the largest mass-invariant
response: 56.0% normalized L1 and R = 0.845, showing that the vertical
injection operator materially controls the transported field.

The one-thread concentration field was finite and close to central, but its
2026-05-25 PM2.5 output contained two non-finite cumulative wet-deposition
values at the grid corner in the final two times. The upgraded whole-output
verifier correctly failed this candidate. The failure was not hidden by
excluding deposition from verification. Its verifier SHA-256 is
`a9012ba0521a24485c175218fe7d331451944888fdd8af080d3f4532bebb7067`.

The field-comparison report SHA-256 is
`0b5e092ed25122842a84b622c21c874febc88bbc877847ae44cd0e2f876078d0`.

## 9. Central deposition attribution

Final cumulative deposition was integrated independently for every
source-day/species member:

| Species | Wet (kg) | Dry (kg) | Total (kg) | Fraction of released mass |
|---|---:|---:|---:|---:|
| PM2.5 | 22,932.1741 | 14.1302 | 22,946.3043 | 20.6215% |
| CO | 43,310.5015 | 0.4364 | 43,310.9379 | 6.1907% |
| Black carbon | 365.5976 | 2.6742 | 368.2718 | 19.1029% |

These are 24-hour within-member deposition totals. They are not a comparison
against a no-deposition run and do not quantify the causal reduction in
surface concentration.

## 10. Acceptance assessment

| Required gate | Status |
|---|---|
| Central engineering and mass integrity | pass |
| Weak/moderate/major event design | fail |
| Resolved GFAS gross source discrepancy | fail |
| Acceptance-capable vertical observation | not run |
| Final acceptance-capable surface PM2.5 | not run |
| Frozen sensitivity matrix | fail/incomplete |
| Independent emissions and air-quality review | pending |
| Four scheduled-cycle demonstrations | not run |

The correct decision is **not accepted**. `SIMULATION_WRITES_ENABLED` must not
be changed on the basis of this experiment.

## 11. Final software verification

The final repository state was checked after the assessment code and
publication records were added:

```text
pytest: 220 passed, 19 skipped, 8 warnings
skips: PostgreSQL integration tests; WEATHER_TEST_DATABASE_URL is not configured
CFFEPS: 10 golden cases and 6 FBP sensitivity cases passed
Ruff: all changed validation Python files and tests passed
uv lock --check: passed; 91 packages resolved
```

The warnings were seven NumPy masked-array shape deprecations and one
non-georeferenced in-memory raster warning in a tile test. None was a failed
validation assertion. The structured regression record is
`docs/smoke-validation-software-verification-2026-07-24.json`.

## 12. What the result does and does not show

The experiment shows that the implementation can build a checksummed source
bundle, conserve the declared daily areas and release masses, complete
independent FLEXPART members, and reproduce all reported pilot diagnostics
from frozen artifacts. It also demonstrates that the validation machinery can
detect consequential issues: finite-window accounting, missing source state,
gross inventory disagreement, insufficient observation support, and a
thread-dependent non-finite deposition output.

It does not establish unbiased fire emissions, validated plume injection,
validated surface PM2.5, or operational robustness across fire sizes. The
small, weak-fire-dominated event population and unequal GFAS coverage prevent
population-wide conclusions.

## 13. Work required for a future acceptance attempt

The implementation-ready program for completing every item is
[the scientific acceptance research program](smoke-validation-research-program/README.md).
Its machine-readable tracker is
[`acceptance-evidence-matrix.yaml`](smoke-validation-research-program/acceptance-evidence-matrix.yaml).

1. Freeze a new event interval containing at least three weak, three moderate,
   and three major independently area-supported fires.
2. Resolve the GFAS coverage mismatch with a preregistered like-for-like event
   support test, while retaining the original active-union result.
3. Acquire acceptance-capable MISR, lidar, or equivalent vertical profiles and
   freeze a footprint/overpass operator before extraction.
4. Evaluate final NAPS or an equivalent final hourly surface archive with
   enough smoke-enhancement pairs.
5. Diagnose the one-thread wet-deposition non-finite values and demonstrate
   clean whole-output verification across thread counts.
6. Preregister and run the missing no-deposition causal sensitivity and a
   defensible low/high burned-area realization.
7. Obtain independent wildfire-emissions and air-quality scientific reviews.
8. Complete at least four scheduled validation cycles inside their windows.

None of these actions should alter or overwrite this result.

## 14. Subsequent prospective MISR result

After this immutable pilot was assessed, W3 observation availability was
expanded without consulting FLEXPART output. An exhaustive 2017-current
MERLIN query identified 388 Canadian-interior plume families in 78 MISR
orbits. Under the unchanged provisional observation rule, 109 qualified; 88
also had complete Fire M3 state/fuel and qualifying independent MCD64A1 area,
spanning 37 orbits.

The wording in item 3 above should therefore be interpreted as “freeze and
execute the expanded MISR cohort,” not “MISR observations are unavailable.”
The candidate shortage is resolved. No modelled plume-height metrics have
been produced, and the pilot's `not accepted` decision is unchanged.

The updated research interpretation and manuscript language are in the
[expanded MISR publication update](smoke-validation-research-program/w3-expanded-misr-publication-update-2026-07-27.md).
