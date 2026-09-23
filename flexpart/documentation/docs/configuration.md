# Configuration
To run FLEXPART, there are three important (sets) of files that need to be specified.
These are:

- the [**option files**](configuration.md#options), defining the set-up of the run,
- the [**pathnames file**](configuration.md#pathnames), defining the paths of where input and output are located, 
- the [**AVAILABLE file**](configuration.md#available), listing all available meteorological input,

Of course, there is also the **par_mod.f90** file, which needs to be specified before compiling (see [**Compiling FLEXPART**](building.md#compliling), but the parameters in this file are expected to not have to be changed between simulations.

In addition to the regular input files listed above, a simulation can also be started using a NetCDF file listing all particles to be released. This option can be switched on by specifying IPIN=3 in the COMMAND option file. More information about how to use this option can be found here: [User-defined initial conditions](configuration.md#ic).

When wanting to restart a previous simulation, see [restarting a simulation](configuration.md#restart).

## <a name="options"></a>Option files
These files define the simulation settings. At the start of a simulation, a copy of each file will be written to the output directory defined in the [**pathnames file**](configuration.md#pathnames).
All option files should be presented as namelists (i.e. &OPTIONFILE). A template of these files can be found in the options/ directory within the repository.

Inside the `options/` directory a template of all option files can be found:

- [COMMAND](configuration.md#command)
- [RELEASES](configuration.md#releases)
- [SPECIES](configuration.md#species)
- [OUTGRID](configuration.md#outgrid)
- [OUTGRID_NESTED](configuration.md#outgrid_nested)
- [AGECLASSES](configuration.md#ageclasses)
- [INITCONC (optional)](configuration.md#initconc)
- [RECEPTORS (optional)](configuration.md#receptors)
- [PARTOPTIONS (optional)](configuration.md#partoptions)
- [REAGENTS (optional)](configuration.md#reagents)
- [SATELLITES (optional)](configuration.md#satellites)

### <a name="command"></a>COMMAND
Sets the behaviour of the run (time range, backward or forward, output frequency, etc.). A table of all options is listed below.

- **Time variables**: Flexpart can be run in forward or backward mode. In forward mode, particles are being traced forward in time, while in backward more, the origin of particles are being traced, going backward in time. This can be set by the [LDIRECT](configuration.md#ldirect) variable. The start and end of the simulation are set by [IBDATE](configuration.md#IBDATE):[IBTIME](configuration.md#IBTIME) and [IEDATE](configuration.md#IEDATE):[IETIME](configuration.md#IETIME). [IEDATE](configuration.md#IEDATE):[IETIME](configuration.md#IETIME) is always at a later time than [IBDATE](configuration.md#IBDATE):[IBTIME](configuration.md#IBTIME), also for backwards simulations. Output variables can be written at specified times: [LOUTSTEP](configuration.md#LOUTSTEP), and restart files will be written at every [LOUTRESTART](configuration.md#LOUTRESTART) interval.
- **Numerical variables**: [LSYNCTIME](configuration.md#LSYNCTIME) and LOUTSAMPLE set the integration interval, smaller generally giving better results, although below a certain number, not much will be gained. With the [CTL](configuration.md#CTL) and [IFINE](configuration.md#IFINE) setting, you can make integration steps even smaller for the turbulence computations.
- **Output variables**: The output is written at every [LOUTSTEP](configuration.md#LOUTSTEP) interval. Both gridded data ([IOUT](configuration.md#IOUT)>0) and particle based data ([IPOUT](configuration.md#IPOUT)=1) can be written to NetCDF files (binary option for gridded data). Nested output can be set by the [NESTED_OUTPUT](configuration.md#NESTED_OUTPUT) switch. Note that for gridded output, the [OUTGRID](configuration.md#OUTGRID) for ([IOUT](configuration.md#IOUT)>0) and [OUTGRID_NESTED](configuration.md#OUTGRID_NESTED) (for [NESTED_OUTPUT](configuration.md#NESTED_OUTPUT)=1) option files should be specified. [MAXFILESIZE](configuration.md#MAXFILESIZE) can be set to limit the size of the NetCDF files that contain the particle based data. [IND_RECEPTOR](configuration.md#IND_RECEPTOR) can be set to get concentrations or mixing ratios at specified receptor points set in the RECEPTORS options file. For backward simulations, [IND_RECEPTOR](configuration.md#IND_RECEPTOR) can be used to get wet or dry deposition gridded data. [SFC_ONLY](configuration.md#SFC_ONLY) and [LINIT_COND](configuration.md#LINIT_COND) are only working for binary output. 
- **Input variables**: IPIN can be set to chose the input type: either initial conditions from particles come from the [RELEASES](configuration.md#releases) file ([IPIN](configuration.md#IPIN)=0), from restart files of a previous run ([IPIN](configuration.md#IPIN)=1),
from a particle netCDF file written in a previous run (only works when the corresponding fields in [PARTOPTIONS](configuration.md#PARTOPTIONS) are chosen) ([IPIN](configuration.md#IPIN)=2), or from user-defined initial particle conditions ([IPIN](configuration.md#IPIN)=3). [MDOMAINFILL](configuration.md#MDOMAINFILL) can be set to distribute particles according to the air density or stratospheric ozone density profiles. This option overwrites the vertical levels set in the [RELEASES](configuration.md#releases) option file.

| Variable name | Description | Possible values and **default** (bold) |
| ----------- | ----------- | ----------- |
| <a name="ldirect"></a>LDIRECT | Simulation direction in time | **1 (forward)** or -1 (backward) |
| <a name="IBDATE"></a>IBDATE | Start date of the simulation | YYYYMMDD: YYYY=year, MM=month, DD=day |
| <a name="IBTIME"></a>IBTIME | Start time of the simulation | HHMISS: HH=hours, MI=minutes, SS=seconds. UTC zone. |
| <a name="IEDATE"></a>IEDATE | End date of the simulation | YYYYMMDD: YYYY=year, MM=month, DD=day |
| <a name="IETIME"></a>IETIME | End time of the simulation | HHMISS: HH=hours, MI=minutes, SS=seconds. UTC zone. |
| <a name="LOUTSTEP"></a>LOUTSTEP | Interval of model output. Average concentrations are calculated every LOUTSTEP (seconds) | **10800** |
| <a name="LOUTAVER"></a>LOUTAVER | Concentration averaging interval, instantaneous for value of zero (seconds) | **10800** |
| <a name="LOUTSAMPLE"></a>LOUTSAMPLE | Numerical sampling rate of output, higher statistical accuracy with shorter intervals (seconds) | **900** |
| <a name="LRECOUTSTEP"></a>LRECOUTSTEP | Interval of receptor output. Mixing ratios are calculated every LRECOUTSTEP (seconds) | **LOUTSTEP** |
| <a name="LRECOUTAVER"></a>LRECOUTAVER | Concentration averaging interval for receptors, instantaneous for value of zero (seconds) | **LOUTAVER** |
| <a name="LRECOUTSAMPLE"></a>LRECOUTSAMPLE | Numerical sampling rate of receptor output (seconds) | **LOUTSAMPLE** |
| <a name="LOUTRESTART"></a>LOUTRESTART | Time interval when a restart file is written (seconds) | **-1** |
| <a name="LSYNCTIME"></a>LSYNCTIME | All processes are synchronized to this time interval; all values above (and for radioactive decay also LOUTSTEP/2) should be dividable by this number (seconds) | **900** |
| <a name="CTL"></a>CTL | Factor by which particle transport time step in the ABL must be smaller than the Lagrangian timescale t l ; resulting time steps can be shorter than LSYNCTIME; LSYNCTIME is used if CTL < 0 | **-5.0** |
| <a name="IFINE"></a>IFINE | Additional reduction factor for time step used for vertical transport only considered if CTL > 1 | **4** |
| <a name="IOUT"></a>IOUT | Switch determining the gridded output type | 0 (no gridded output), **1 (forward: mass concentration; backwards: residence time)**, 2 (volume mixing ratio), 3 (1 and 2 combined), 4 (plume trajectories), 5 (1 and 4 combined), Add 8 for NetCDF output |
| <a name="IPOUT"></a>IPOUT | Switch for particle position output | **0 (no particle output)**, 1 (particle output every LOUTSTEP), 2 (particle output at the end of the simulation) |
| <a name="LSUBGRID"></a>LSUBGRID | Increase in ABL heights due to subgrid-scale orographic variations | **0 (off)**, 1 (on) |
| <a name="LCONVECTION"></a>LCONVECTION | Switch for convection parameterization | 0 (off), **1 (on)** |
| <a name="LTURBULENCE"></a>LTURBULENCE | Switch for turbulence parameterization | 0 (off), **1 (on)** |
| <a name="LTURBULENCE_MESO"></a>LTURBULENCE_MESO | Switch for mesoscale turbulence parameterization | **0 (off)**, 1 (on) |
| <a name="LAGESPECTRA"></a>LAGESPECTRA | Switch for calculation of age spectra (needs file [AGECLASSES](configuration.md#ageclasses) option file) | 0 (off), **1 (on)** |
| <a name="IPIN"></a>IPIN | Particle information input. Starting from [RELEASES](configuration.md#releases) option file, form restart.bin, or user-defined particle input data (see Silvia Bucci's stuff) | **0 (using RELEASES option file)**, 1 (using restart.bin file), 2 (using previous partoutput file), 3 (self made initial conditions), 4 (restart.bin and self made initial conditions) |
| <a name="IOUTPUTFOREACHRELEASE"></a>IOUTPUTFOREACHRELEASE | Switch for separate output fields for each location in the [RELEASES](configuration.md#releases) file | 0 (no), **1 (yes)** |
| <a name="IFLUX"></a>IFLUX | Output of mass fluxes through output grid box boundaries (northward, southward, eastward, westward, upward and downward) | 0 (off), **1 (on)** |
| <a name="MDOMAINFILL"></a>MDOMAINFILL | Switch for domain-filling calculations: particles are initialized to reproduce air density or stratospheric ozone density; for limited-area simulations, particles are generated at the domain boundaries | **0 (no)**, 1 (like air density), 2 (stratospheric ozone tracer) |
| <a name="IND_SOURCE"></a>IND_SOURCE | Unit to be used at the source; see Seibert and Frank (2004); Eckhardt et al. (2017) | **1 (mass)**, 2 (mass mixing ratio) |
| <a name="IND_RECEPTOR"></a>IND_RECEPTOR | Unit to be used at the receptor; see Seibert and Frank (2004); Eckhardt et al. (2017) | 0 (no receptor), **1 (mass)**, 2 (mass mixing ratio), 3 (backward only: wet deposition),  4 (backward only: dry depostion) |
| <a name="MQUASILAG"></a>MQUASILAG | Quasi-Lagrangian mode to track individual numbered particles | **0 (off)**, 1 (on) |
| <a name="NESTED_OUTPUT"></a>NESTED_OUTPUT | Switch to produce output also for a nested domain | **0 (no)**, 1 (yes) |
| <a name="LNETCDFOUT"></a>LNETCDFOUT | Switch to produce NetCDF output, overwritten to 1 when IOUT>8 and set to 0 when compiled without NetCDF libraries | 0 (no), **1 (yes)** |
| <a name="LINIT_COND"></a>LINIT_COND | Switch to produce output sensitivity to initial conditions given in concentration or mixing ratio units (in backwards mode only) | **0 (no)**, 1 (mass), 2 (mass mixing ratio) |
| <a name="LCMOUTPUT"></a>LCMOUTPUT | Linear Chemistry Module switch, should be used in combination with LDIRECT=1, MDOMAINFILL=1, IND_SOURCE=1, IND_RECEPTOR=1 | **0 (no)**, 1 (yes) |
| DRYDEP_ENABLED | Apply species-configured dry deposition. Disabling this does not disable gravitational settling. | **.true.**, .false. |
| WETDEP_ENABLED | Apply species-configured wet deposition/scavenging. | **.true.**, .false. |
| <a name="SFC_ONLY"></a>SFC_ONLY | Output of SRR for fluxes only for the lowest model layer, most useful for backward runs when LINIT_COND set to 1 or 2 | **0 (no)**, 1 (yes) |
| <a name="CBLFLAG"></a>CBLFLAG | Skewed rather than Gaussian turbulence in the convective ABL; when turned on, very short time steps should be used (see CTL and IFINE) | **0 (no)**, 1 (yes) |
| <a name="MAXTHREADGRID"></a>MAXTHREADGRID | Set maximum number of threads for doing grid computations. Recommended to set this to max 16. High numbers create more overhead and a larger memory footprint  | **1 (default=no parallelisation on grid)** integer |
| <a name="MAXFILESIZE"></a>MAXFILESIZE | Maximum output of each partoutput NetCDF-4 file in Mb before a new one is created  | *10000 (default=10GB)** integer |
| <a name="LOGVERTINTERP"></a>LOGVERTINTERP| Flag to set all vertical interpolation to logarithmic instead of linear  | *0=off (default)**, 1=on |
| <a name="NXSHIFT"></a>NXSHIFT|  Shift of the global meteorological data by number of grid cells. | Default 359 for ECMWF and 0 for GFS if not given |

<br/>

### <a name="releases"></a>RELEASES
This file contains the information about the particles initial conditions: how many, where and when they will be released, their mass and what species they are (defined in the SPECIES files).
The RELEASES file contains two types of namelists: 
 
 1. `&RELEASES_CTRL` namelist, specifying the total number of species and the specific species file associated (see [SPECIES](configuration.md#species)). There is only one of this namelist and it is found at the top of the file. 

 2. `&RELEASE` namelist, specifying for each release, the start and end of the release, the location of the release, and the number of particles that are to be released.

| Variable name `&RELEASES_CTRL` | Description | Data type |
| ------------- | ----------- | --------- |
|NSPEC | Total number of species | integer |
|SPECNUM_REL | Species numbers in directory SPECIES | integer(s divided by comma's) |

<br/>
And for each release:

| Variable name `&RELEASE` | Description | Data type |
| ------------- | ----------- | --------- |
|IDATE1 | Release start date | integer in the form of YYYYMMDD: YYYY=year, MM=month, DD=day|
|ITIME1 | Release start time in UTC | integers in the form of HHMISS: HH hours, MI=minutes, SS=seconds|
|IDATE2 | Release end date | same as IDATE1|
|ITIME2 | Release end time | same as ITIME1|
|LON1 | Left longitude of release box -180(NXSHIFT$\Delta$lon) < LON1 <180(NXSHIFT$\Delta$lon)| real |
|LON2 | Right longitude of release box, same as LON1| real |
|LAT1 | Lower latitude of release box, -90 < LAT1 < 90| real |
|LAT2 | Upper latitude of release box same format as LAT1 | real |
|Z1 | Lower height of release box meters/hPa above reference level| real |
|Z2 | Upper height of release box meters/hPa above reference level| real |
|ZKIND | Reference level | integer: 1=above ground, 2=above sea level, 3 for pressure in hPa|
|MASS | Total mass emitted, only relevant for fwd simulations| real |
|PARTS | Total number of particles to be released| integer |
|COMMENT | Comment, written in the outputfile| character string |

<br/>
**Note:** the RELEASES file is no longer necessary when using [IPIN](configuration.md#ipin)=3, giving full control to the user to decide where and when particles of different species are being released (see [User-defined initial conditions](configuration.md#ic)).

### <a name="species"></a>SPECIES
The subdirectory options/SPECIES/ needs to contain one or more files named SPECIES_nnn. In options/SPECIES/ templates for several species are given. These come with no warranty and will have to be renamed to SPECIES_nnn where nnn are three digits. For each species nnn listed in the header section of the RELEASES file, such a SPECIES_nnn file must exist. The parameters in the SPECIES_nnn file, contained in the namelist &SPECIES_PARAMS, set the species name and define the physicochemical properties of the species; they are described in Table 10. These are important for simulating radioactive or chemical decay, wet deposition (scavenging) for gases and aerosols, dry deposition for gases and aerosols, particle settling, and chemical reaction with the OH radical. Some parameters are only necessary for gas tracers and some are only necessary for aerosol tracers; thus, a namelist does not need to contain all parameters for both gases and particles. Optionally, since FLEXPART version 6.0, information about temporal emission variations can be added at the end of the file.

The following specifies the parameters associated with each physicochemical process simulated.

- Radioactive or chemical decay: set with PDECAY; off if PDECAY<0.
- Wet deposition for gases: set with PWETA_GAS, PWETB_GAS (for below-cloud) and PHENRY (for in-cloud). Switch off for both in- and below-cloud if either PWETA_GAS or PWETB_GAS is negative.
- Wet deposition for aerosols: set with PCCN_AERO, PIN_AERO for in-cloud scavenging and PCRAIN_AERO, PCSNOW_AERO and PDIA for below-cloud scavenging.
- Dry deposition for aerosols: set with PDENSITY, PDIA, PNDIA, and PDSIGMA; off if PDENSITY < 0. 
- Dry deposition for gases: set with PHENRY, PF0 and PRELDIFF; off if PRELDIFF < 0. Alternatively, a constant dry deposition velocity pdryvel can be given. 
- Settling of particles: set with PDENSITY and PDIA.
- Shape of particles: set with PSHAPE, PASPECTRATIO, PLA, PIA, PSA, and PORIENT.
- OH reaction: chemical reaction with the OH radical can be turned on by giving parameter PCCONST (cm^3 molecule^-1 s^-1 ), PDCONST (K) and PNCONST (no unit) positive values; defined by Eq. (13) in Pisso et al. (2019).
- Emission variation: emission variation during the hours (local time) of the day and during the days of the week can be specified. Factors should be 1.0 on average to obtain unbiased emissions overall. The area source factors (useful, e.g., for traffic emissions) are applied to emissions with a lower release height below 0.5 m above ground level (a.g.l.) and the point source factors (useful, e.g., for power plant emissions) to emissions with a lower release height than 0.5 m a.g.l. Default values are 1.0.

| Variable name | Description | Data type |
| ----------- | ----------- | --------- |
|PSPECIES | Tracer name | character(len=16) |
|<a name="PDECAY"></a>PDECAY | Species half life | real |
|PWETA_GAS | Below-cloud scavenging (gases) - A (weta_gas) | real |
|PWETB_GAS | Below-cloud scavenging (gases) - B (wetb_gas) | real |
|PCRAIN_AERO | Below-cloud scavenging (particles) - Crain (crain_aero) | real |
|PCSNOW_AERO | Below-cloud scavenging (particles) - Csnow (csnow_aero) | real |
|PCCN_AERO | In-cloud scavenging (particles) - CCNeff (ccn_aero) | real |
|PIN_AERO | In-cloud scavenging (particles) - INeff (in_aero) | real |
|PDENSITY | Dry deposition (particles) - rho | real |
|PDIA | Dry deposition (particles) - diameter or equivalent diameter for shape (meter) | real |
|PDSIGMA | Dry deposition (particles) - dsig | real |
|PNDIA | Dry deposition (particles) - ndia | integer |
|PDRYVEL | Alternative: dry deposition velocity | real |
|PRELDIFF | Dry deposition (gases) - D | real |
|PHENRY | Dry deposition (gases) - Henrys const. | real |
|PF0 | Dry deposition (gases) - f0 (reactivity) | real |
|PWEIGHTMOLAR | molweight | real |
|PREACTIONS | List of reactions, must correspond to names in REAGENTS | string |
|<a name="PCCONST"></a>PCCONST | OH Reaction rate - C [cm^3/molecule/sec], in order of PREACTIONS | real |
|<a name="PDCONST"></a>PDCONST | OH Reaction rate - D [K], in order of PREACTIONS | real |
|<a name="PNCONST"></a>PNCONST | OH Reaction rate - N [dimensionless], in order of PREACTIONS | real |
|PEMIS_PATH | Emissions path, if empty, no emissions | string |
|PEMIS_FILE | Generic file name for emissions, if empty, no emissions | string |
|PEMIS_NAME | Variable name for emissions, if empty, no emissions | string |
|PEMIS_UNIT | Unit of emissions | integer 0=per gridcell, 1=per m2 |
|PEMIS_COEFF | Coefficient to convert from emission input unit to kg/s | real |
|PSHAPE | Defining the shape of a particle | integer: **0=sphere (default)**, 1=any shape (defined by axes PLA,PIA,PSA), 2=cylinder, 3=cube, 4=tetrahedron, 5=octahedron, 6=ellipsoid |
|PASPECTRATIO | Aspect ratio of cylinders: works for PSHAPE=2 only | real |
|PLA | Longest axis in meter (Bagheri & Bonadonna 2016): only for PSHAPE=1 | real |
|PIA | Intermediate axis in meter: only for PSHAPE=1 | real |
|PSA | Smallest axis in meter: only for PSHAPE=1 | real |
|PORIENT | Falling orientation for aerosol particles of shape != 0 | integer: **0=horizontal (default)**, 1=random orientation of particles, 2=average between random and horizontal |

<br/>

### <a name="outgrid"></a>OUTGRID
The OUTGRID file specifies the domain and grid spacing of the three-dimensional output grid. Note that in a Lagrangian model, the domain and resolution of the gridded output are totally independent from those of the meteorological input (apart from the fact that the output domain must be contained within the computational domain). The output grid is available in binary and NetCDF format, which can be set by [IOUT](configuration.md#iout) in the [COMMAND](configuration.md#command) file.


| Variable name | Descriptions | Data type |
| ------------- | ------------ | --------- |
|OUTLON0 | Geographical longitude of the lower left corner of the output grid | real |
|OUTLAT0 | Geographical latitude of the lower left corner of the output grid | real |
|NUMXGRID | Number of grid points in the X direction (= No. of cells +1) | integer |
|NUMYGRID | Number of grid points in the Y direction (= No. of cells +1) | integer |
|DXOUT | Grid distance in the X direction | real |
|DYOUT | Grid distance in the Y direction | real |
|OUTHEIGHTS | The height of the levels (upper boundary) | real(s divided by comma's) |

<br/>

### <a name="outgrid_nest"></a>OUTGRID_NEST
Output can also be produced on one nested output grid with higher horizontal resolution.
This file specifies the size and dimensions of the nested output grid. The height levels are equal to those set in [OUTGRID](configuration.md#outgrid).

| Variable name | Descriptions | Data type |
| ------------- | ------------ | --------- |
|OUTLON0N | Geographical longitude of the lower left corner of the output grid | real |
|OUTLAT0N | Geographical latitude of the lower left corner of the output grid | real |
|NUMXGRIDN | Number of grid points in the X direction (= No. of cells +1) | integer |
|NUMYGRIDN | Number of grid points in the Y direction (= No. of cells +1) | integer |
|DXOUTN | Grid distance in the X direction | real |
|DYOUTN | Grid distance in the Y direction | real |

<br/>

### <a name="ageclasses"></a>AGECLASSES

The option to produce age class output can be activated by setting [LAGESPECTRA](configuration.md#lagespectra) in the [COMMAND](configuration.md#command) file. The AGECLASSES file then allows for the definition of a list of times (in seconds, in increasing order) that define the age classes used for model output. With this option, the model output (e.g., oncentrations) is split into contributions from particles of different age, defined as the time passed since the particle release. Particles are dropped from the simulation once they exceed the maximum age, skipping unnecesary computations. This is an important technique to limit the cpu usage for long-term simulations. Thus, even if the user is not interested in age information per se, it may often be useful to set one age class to define a maximum particle age.
The file should contain two namelist: 

1) &NAGE

| Variable name | Description | Data type |
| ------------- | ------------ | --------- |
|NAGECLASS | Number of ageclasses for the age spectra calculation | integer |

<br/>

2) &AGECLASS

| Variable name | Description | Data type |
| ------------- | ------------ | --------- |
|LAGE | Maximum age of particles in seconds for each ageclass | integer(s divided by comma's) |

<br/>

### <a name="initconc"></a>INITCONC

**Optional** Specifies input for initialising the mixing ratios. If hybrid pressure coordinates, the variable PS_NAME is required. Otherwise, either ALT_NAME or PRS_NAME need to be given. The file should contain two namelists:

1) &INITCONC_CTRL

| Variable name | Description | Data type |
| ------------- | ------------ | --------- |
|NINIT | Number of species for which initial concentration is specified | integer |
|SPECNUM_REL | List of species of length NSPEC set in [RELEASES](configuration.md#releases) | integer |

<br/>

2) &INITCONC

| Variable name | Description | Data type |
| ------------- | ------------ | --------- |
|PATH_NAME | Path to initial concentration files | character string |
|FILE_NAME | Generic name of file (using YYYY[MM][DD] for dates)  | character string |
|VAR_NAME | Name of concentration variable in file  | character string |
|HYA_NAME | Name of hybrid pressure coord A (use "" if none)| character string |
|HYB_NAME | Name of hybrid pressure coord B (use "" if none)| character string |
|PS_NAME | Name of surface pressure variable (use "" if none)  | character string |
|Q_NAME | Name of specific humidity variable (use "" if none, then assumes dry air mixing ratio) | character string |
|PRS_NAME | Name of vertical pressure coordinate (use "" if none) | character string |
|ALT_NAME | Name of altitude coordinate (use "" if none) | character string |
|COEFF | Coefficient from input unit to ppbv | real |


<br/>

### <a name="receptors"></a>RECEPTORS

**Optional** In addition to gridded model output, it is also possible to define receptor points. With this option output can be specifically produced for certain points at the surface in addition to gridded output. The RECEPTORS file contains a list with the definitions of the receptor name, longitude and latitude. If no such file is present, no receptors are written to output. At the moment, this data is added to the gridded_output file, when using netcdf, maybe this should be a dedicated RECEPTOR netcdf file instead.

| Variable name | Description | Data type |
| ------------- | ------------ | --------- |
|RECEPTOR | Name of the receptor point | character string |
|LON | Geographical longitude | real |
|LAT | Geographical latitude | real |
|ALT | Altitude | real |
|TIME | (Optional) time of receptor output | real |

<br/>

### <a name="partoptions"></a>PARTOPTIONS
**Optional** This option file is only necessary when requiring particle properties to be written out (IPOUT=1 in the COMMAND option file). In this file, the user can set what particle properties and interpolated fields they want to be written to files. At the moment, the available fields that can be written to file are:

- particle positions (longitude, latitude and height), 
- potential vorticity, 
- specific humidity, 
- density, temperature, 
- pressure, 
- particle mass, 
- separate cumulative wet and dry deposition masses, 
- settling velocity, 
- 3D velocities, 
- the height of the PBL, tropopause and topography.

Each property can also be printed out as an average instead of an instantaneous value. For example, if one makes internal time steps of 600 seconds each,
and writes properties to files every hour, the outputted value will be the average of the 6 previous values of the particle of the past hour. Note that this comes with an additional computational cost.

If the particle output is switched on (IPOUT=1), terminated particles are kept in the simulation, but values associated with them are set to `NaN` instead of being overwritten by newly released particles in the NetCDF output.
This comes with no additional computational cost, but it may need more memory than when running without the particle output option switched on. 
As some applications might use a large number of short-lived particles during a longer simulation, the behaviour of overwriting terminated particles can be restored by removing `ipout.eq.0` from the `get_newpart_index` subroutine, located in the file `particle_mod.f90`.
<br/>

### <a name="reagents"></a>REAGENTS
**Optional** Specifies chemical reagents for reactions. The corresponding rate constants are given in the SPECIES files (PREACTION).

| Variable name | Description | Data type |
| ------------- | ----------- | --------- |
| PREAGENT | Reagent name, must be the same as variable name and match those used in reactions list in SPECIES file | string |
| PREAG_PATH | path to reagent file | string |
| PHOURLY | Interpolate field to hourly based on solar zenith angle | integer: 0=no, 1=yes | 

<br/>

### <a name="satellites"></a>SATELLITES
**Optional** Specifies paths and input file names of satellite retrievals for which mixing ratios should be output

| Variable name | Description | Data type |
| ------------- | ----------- | --------- |
| PSATNAME | Name of satellite | string |
| PPATH | path to satellite files | string |
| PFILE | Generic name of satellite files | string ending with "YYYYMMDD.nc" | 

<br/>

## <a name="pathnames"></a>Pathnames file
The pathnames file is a text file containing the path to:

- first line: directory of the option files,
- second line: name of directory where output files are generated,
- third line: base path to the meteorological input data,
- fourth line: full path and filename of the AVAILABLE file (see [**AVAILABLE**](configuration.md#available)).

When using nested areas, the third and fourth line can be repeated with the respected meteorological data directory base paths and AVAILABLE_NEST file paths:

- Line 2n+3: path where meteorological fields are available (nested grid n),
- Line 2n+4: full path and filename of the AVAILABLE-file of nested grid n.

## <a name="available"></a>AVAILABLE files
The meteorological input data, one file for each input time, are stored in GRIB format in a common directory (specified in line 3 of pathnames). To enable FLEXPART to find these files, a file usually named AVAILABLE (given in line 4 of pathnames) contains a list of all available meteorological input files and their corresponding time stamps. Additional files containing nested input data may also be provided. In this case, a separate file containing the input file names (e.g., named AVAILABLE_NESTED) must be given. Date and time entries in the AVAILABLE* files for mother and nested
fields must be identical.

ECMWF data can be retrieved using [flex_extract](https://flexpart.img.univie.ac.at/flexextract/index.html)

## <a name="ic"></a>User-defined initial conditions
A simulation can be started using a NetCDF file listing all particles to be released. This option can be switched on by specifying [IPIN](configuration.md#ipin)=3 in the [COMMAND](configuration.md#command) option file. This file should be called **part_ic.nc** and located in the options directory defined in [Pathnames file](configuration.md#pathnames). It should have the following structure:

**Header**

| Variable name | Description | Data type |
| ------------- | ----------- | --------- |
| `nspecies` | Number of species | integer |
| `species` | Species IDs (see [SPECIES](configuration.md#species)) | 1D-array of integers |
| `kindz` | Reference level | integer: 1=above ground, 2=above sea level, 3 for pressure in hPa | 

<br/>

**Data**

| Variable name | Description | Data type |
| ------------- | ----------- | --------- |
| `longitude` | Initial longitude of each particle | 1D-array of reals with dimension `particle` |
| `latitude` | Initial latitude of each particle | 1D-array of reals with dimension `particle` |
| `height` | Initial height of each particle (meter above reference level) | 1D-array of reals with dimension `particle` |
| `time` | Release time of each particle seconds after simulation start (IBDATE/IBTIME for forward runs, IEDATE/IETIME for backward runs, set in [COMMAND](configuration.md#command)) | 1D-array of integers with dimension `particle` |
| `mass` | Initial mass of each particle (kg) | 2D-array of reals with dimension `species` and `particle` |
| `release` | Release ID of each particle, giving separate concentration fields for each release ID when [IOUTPUTFOREACHRELEASE](configuration.md#ioutputforeachrelease) in [COMMAND](configuration.md#command) is set | 1D-array of integers with dimension `particle` |

<br/>

## <a name="restart"></a>Restarting a simulation
In case your simulation crashes or if you simply want to extend your simulation period, it is possible to run using the restart option (COMMAND option file: IPIN=1 or IPIN=4 when initially running with part_ic.nc). You will need to decide if you will need this option before starting your initial simulation: LOUTRESTART in the COMMAND option file needs to be set to an appropriate time interval. For example, you can choose to set LOUTRESTART = 172800 s to get a new restart file ever 2 days. The restart files are written in binary and their name specifies the time within your simulation period they are written. When LOUTRESTART is set to -1, this option is disabled.

To run from one of these files, simply rename the desired restart_XXX.bin file to restart.bin, set IPIN=1 (or IPIN=4 when initially running with IPIN=3) and you can restart your run from there.

WARNING: If you chose to use gridded data output (IOUT>0), then new data will be written to this file. If it is not desirable to overwrite a gridded data output file from a previous run, copy this file to another directory.
