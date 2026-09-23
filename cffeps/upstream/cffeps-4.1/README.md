## This is CFFEPS ECCC RAQDPS branch ##

Source code from Dr. Kerry Anderson of Canadian Forest Service, Natural
Resources Canada, Government of Canada - original C code ported to FORTRAN by
ECCC for operational RAQDPS.  Current code utilizing IO functions of
https://github.com/ECCC-ASTD-MRD/librmn needed for operational NWP data access.

Current Version of [CFFEPS User Manual](CFFEPS_20201123_v2.10.pdf)

Internal revision tracking: this is cloned from arqi/cffeps repository (tag
CFFEPSv4.1) revision -- extracted and modified for github release.
*/cffeps/commit/98265cb5f27f6696e6fa44af6073e95601f7ada9*

## Standalone (offline) version ##
The main program is for standalone (or offline) calculation of fire emissions,
with inputs/outputs similar to the original C version (CFFEPS v2.x).

Instead of input control as `ini file` pass as argument in the v2x version,
this v4x FORTRAN version expects control file as FORTRAN namelist input
`input_config.nml`

However, the output plume injection height parameters estimate from CFFEPSv4x
can be different from the original C version, largely due to different
meteorlogical inputs.  The original C version calculates plume injection height
with 5-layer extracted, thus layer-interpolated, meteorology whereas the FORTRAN
version allows for native fst input with full GEM model layers.

Compared to the original C version, the actual 'cffeps' executable
runtime is longer with this FORTRAN standalone version due to online access of
input hourly meteorology files (GEM fst). This IO overhead is now part of CFFEPS
runtime.

#### Forecast vs. Hindcast ####
CFFEPS is primarily adopted for RAQDPSFW (FireWork) forecast operation, however
the same suite can be easily modified to process emissions for hindcast runs.

The main difference between forecast and hindcast is that, forecast assumes
hotspot persistence, such that past 24-hr hotspot is used to estimate emissions
for the forecast runs, thus emissions generated with forecast meteorology.
OTH, with hindcast, curren-day hotspots are used with current-day meteorology for
more temporal matching fire emissions.


## Online version ##
The subroutines in this version have been included in research version of
[GEM-MACH] as CFFEPS module to provide runtime, online calculation of fire
emissions (i.e. CFFEPS-online version).

Pre-processing of fire input with 24-hour fire energy spin-up is necessary for
this option.

This online CFFEPS pre-processing step have also been incorporated in the
gemmach_module and is triggered by gem-mach namelist `chm_cffeps_online_l=.true.`.

The CFFEPS-online version is applicable for GEM-MACH 2-way coupled simulation
when meteorology influenceing fire emissions can be altered due direct/indirect
aerosol effects.

Following lists the equivalent subroutine as used in GEM-MACH module

| **CFFEPSv4 standalone** | **GEMMACH CFFEPS module** | **Note** |
| :---  | :--- | :--- |
| mach_cffeps_main.ftn90 | mach_cffeps.f90 | main program/subroutine |
| mach_cffeps_init.f90 | chm_cffeps_init.ftn90 |
| mach_cffeps_emissions_mod.f90 | mach_cffeps_emissions_mod.ftn90 |
| mach_cffeps_calc.f90 | mach_cffeps_calc.ftn90 |
| mach_cffeps_speciations_mod.f90 | mach_cffeps_speciations_mod.ftn90 | ADOM2/SAPRC speciation profile
| mach_cffeps_procalc.f90 | mach_cffeps_procalc.ftn90 |
| mach_cffeps_plumes_mod.f90 | mach_cffeps_plumes_mod.ftn90 |
| mach_cffeps_energy.f90 | mach_cffeps_energy.ftn90 |
| mach_cffeps_diurnal_mod.f90 | mach_cffeps_diurnal_mod.ftn90 |
| mach_cffeps_fbp_mod.f90 | mach_cffeps_fbp_mod.ftn90 |
| mach_cffeps_mod.f90 | mach_cffeps_mod.ftn90 |
| mach_readfst.f90 | | standalone use only |

