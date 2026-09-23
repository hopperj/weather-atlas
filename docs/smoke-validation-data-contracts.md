# Smoke validation data contracts

The governing scientific protocol is
[`smoke-validation-protocol.md`](smoke-validation-protocol.md). This file defines
the adapter-level interchange contracts. GFAS is an inventory intercomparison,
not independent observational truth and not, by itself, an acceptance test.

The validation harness consumes a frozen matched-pair CSV rather than silently
joining changing upstream datasets at evaluation time. Each row must contain
numeric `observed` and `modelled` columns. It may also contain `time`, `latitude`,
`longitude`, `event_id`, `station_id`, `species`, and source-specific identifiers.
The harness records the pair-file, threshold-file, and run-manifest SHA-256 values.

Adapters must construct the pairs as follows:

- `gfas_inventory`: aggregate the independently seeded CFFEPS source emissions
  and CAMS GFAS v1.2 daily analysis fluxes to the same species, UTC day, and
  0.1-degree grid cell. Convert GFAS `kg m-2 s-1` to cell-day kilograms with
  the geodesic cell area and 86,400 seconds. Do not compare concentration output
  to emission flux. Do not use GFAS FRP, emissions, or injection height to seed
  the CFFEPS candidate. Keep GFAS injection height as a separate diagnostic.
- `misr_plume_height`: match a MISR plume polygon/time to the contributing fire
  event, convert both heights to metres AGL using the same terrain reference, and
  compare the observed statistic with a statistic derived from the FLEXPART
  aerosol vertical profile at the MISR overpass. Raw CFFEPS plume top is a
  separately labelled source-model diagnostic, not the primary transported-plume
  comparison.
- `naps_pm25`: sample the model grid at each NAPS station and UTC hour, apply the
  model's interval convention, retain missing observations as missing (never zero),
  and compare primary wildfire PM2.5 with an observed smoke enhancement. Estimate
  background with the frozen event method in the protocol; never compare a
  smoke-only candidate directly with unadjusted total PM2.5 and call the result
  unbiased.

Source access and licensing remain explicit: CAMS GFAS uses ECMWF data access,
MISR is obtained from NASA ASDC, and NAPS is obtained from the Government of Canada
open-data archive. Raw source files and transformation code must be retained beside
the matched-pair artifact before a result can count toward operational acceptance.
Every adapter must also emit a manifest containing source checksums, software
version, inclusion/exclusion counts, spatial and temporal matching tolerances,
units, transformations, and the pair-file checksum.
