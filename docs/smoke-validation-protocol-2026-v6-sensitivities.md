# March–May 2026 validation protocol v6 sensitivity amendment

**Protocol ID:** `cffeps-flexpart-external-validation-2026-07-24-v6-sensitivities`  
**Status:** sensitivity matrix frozen before any sensitivity candidate output  
**Frozen:** 2026-07-24 13:26:18 UTC (10:26:18 ADT)  
**Parent protocol:** [`smoke-validation-protocol-2026-v5-amendment.md`](smoke-validation-protocol-2026-v5-amendment.md)  
**Central candidate:** `march-may-2026-mcd64a1-central-v4`

## Timing and interpretation

The central GFAS, TROPOMI, AirNow, and AQS results existed before this
amendment. None of the sensitivity candidates below had been generated.
These runs quantify robustness and attribution; they cannot rescue a failed
central gate, change an event identity, alter a threshold, or make a
diagnostic acceptance-capable.

Each sensitivity changes exactly one declared operator relative to the v4
central candidate. All other values are inherited by a deterministic deep
merge from the checksummed v4 configuration. Event eligibility and the
complete-input exclusions remain fixed. A high-confidence area curve may have
zero area on a central source date, but it may not add or replace an event.

## Frozen matrix

| Candidate | Single change | Configuration SHA-256 |
|---|---|---|
| `march-may-2026-mcd64a1-ef-low-v6` | Registry `low` emission factors | `38993693dc3bbdbb5cd5051f9da45203649bf5e4981eeff15a6fe1f9f4efcb6f` |
| `march-may-2026-mcd64a1-ef-high-v6` | Registry `high` emission factors | `43c302b0c6edb9c822f93f6277c516271b6d47715852ad929818b16632a87f97` |
| `march-may-2026-mcd64a1-area-high-confidence-v6` | MCD64A1 high-confidence daily burned area | `c02cb5feb31893db5917a4b3ac14296622a2459595d542d020d69c977d2a1f77` |
| `march-may-2026-mcd64a1-injection-uniform-v6` | Equal mass in 12 layers from 0 m AGL to CFFEPS plume top | `6c9ec2132040c27a71ef492adf11cbd67030912af5726a96a97cf5c457a399a6` |
| `march-may-2026-mcd64a1-particles-300k-v6` | 300,000 rather than 150,000 particles per species-day | `9d2c78d798cdc83a07c80f1f98ef4a5c8164eb752dd78c63312ca9fb5b3c2292` |
| `march-may-2026-mcd64a1-threads-1-v6` | One rather than eight OpenMP threads per member | `3854d1ae9b464e16122e947d29dbba764e4efe229c7483a0f925d9ea2a96e999` |

The low, central, and high emission-factor masses must be ordered for every
species. Every completed sensitivity must pass the same independent structural
verifier as the central run. Particle and thread comparisons retain identical
source mass and member seeds; field differences are reported without
post-result retuning. Area and injection alternatives are scientific
sensitivities and are descriptive rather than pass/fail replacements.

## Field comparison operator

For every common species, source day, time, height, latitude, and longitude,
the candidate concentration is compared with central output. Reports include
total concentration-field sum, signed normalized sum difference, normalized
L1 difference, RMSE, maximum absolute difference, Pearson correlation over
the active union, and count of positive cells. Deposition fields are compared
separately from concentration.

No concentration threshold is used in the common-grid field metrics. Exact
zero/zero cells enter RMSE but not the active-union correlation. A missing
member, shape mismatch, time mismatch, non-finite value, negative value, or
source-mass mismatch where mass should be invariant is a hard verification
failure.

Central wet and dry deposition fields are also integrated and reported by
species and day. This is deposition attribution, not a no-deposition causal
run; a future no-deposition candidate must receive its own preregistered
amendment.
