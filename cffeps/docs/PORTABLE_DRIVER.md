# Portable CFFEPS profile driver

The upstream CFFEPS 4.1 executable reads GEM FST fields through ECCC-specific
libraries. `weatherapp-cffeps` instead consumes one location-specific profile
per model hour and calls the same upstream `cffeps_calc` routine.

The command accepts a Fortran namelist containing the fire location, FBP fuel
index, estimated area, detection time, FFMC, DMC, DC, and model switches.
FFMC/DMC/DC are required because they cannot be recovered uniquely from the
single FWI value in the public Fire M3 hotspot feed.

The profile file has no header. Each hour starts with:

```text
YEAR MONTH DAY HOUR SPECIFIC_HUMIDITY WIND_SPEED_KNOTS DEWPOINT_K
```

It is followed by exactly 40 lines of:

```text
PRESSURE_PA TEMPERATURE_K GEOPOTENTIAL_HEIGHT_M_AGL
```

Pressure must strictly decrease and height must strictly increase. The output
CSV contains CFFEPS plume top, fire area, and current flaming, smoldering, and
residual fuel-consumption rates. Application code applies the separately
versioned species registry to those phase rates.

For causal historical reconstructions, the namelist may additionally provide
`fire_weather_state_path`. That headerless file contains one
`FFMC DMC DC` record per meteorological profile hour. The portable driver
updates those three fire-weather codes and recomputes BUI immediately before
the corresponding CFFEPS call. When the option is absent, the original
constant namelist values are used for every hour. A state record must therefore
be selected from observations available at or before its profile hour; the
driver does not perform that temporal selection itself.

The optional `estimated_area_state_path` similarly contains one nonnegative,
nondecreasing cumulative area in hectares per profile hour. It replaces
`fire%estarea` immediately before that hour's CFFEPS calculation. Supplying a
causal cumulative series prevents an early source hour from using the fire's
later pre-overpass size in its growth and plume-rise calculation. When the
option is absent, the legacy constant `estarea_ha` namelist value is retained.

The W3 causal-selection rules, exact historical commands, output schemas, and
revision history are documented in:

```text
docs/smoke-validation-research-program/
  progress/2026-07-27-w3-blind-observation-and-causal-emissions.md
  w3-reproduction-runbook-2026-07-27.md
  w3-artifact-data-dictionary-2026-07-27.md
```

The three phase-rate columns are explicitly normalized to metric tonnes per
hour. Upstream CFFEPS 4.1 applies a `1.0e-3` storage factor to these arrays even
though nearby comments call them tonnes per hour; its cumulative
`totalemissions` field does not use that factor. The portable driver therefore
multiplies the phase arrays by 1,000 at the output boundary.

CFFEPS distributes new fuel through future-time queues according to combustion
residence time. The driver exposes the flaming, smouldering, and residual fuel
remaining in those queues after every finite-window output hour. The Python
adapter independently checks that released fuel plus the final pending queue
agrees with CFFEPS's cumulative consumed-fuel total within 5%. This closed
balance detects the original 1,000-fold source-unit error without incorrectly
classifying fuel scheduled after a finite driver window as missing. Pending
fuel does not enter a transport member whose horizon has ended.
