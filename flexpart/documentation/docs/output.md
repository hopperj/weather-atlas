# Output files

An overview of all possible output files is provided in the table below. Notice that not all these files are written out in every model run; the user settings control which files are produced. At the beginning of a run, FLEXPART records descriptive metadata to either the gridded NetCDF output file ([IOUT](configuration.md#IOUT)>8 or [LNETCDFOUT](configuration.md#LNETCDFOUT)=1), the particle output ([IPOUT](configuration.md#IOUT)=1), or to a dedicated binary file header and a plain text file **header_txt** (with the exception of the orography data and release information). Corresponding files header_nest are produced if nested output is selected. 

When [IOUT](configuration.md#IOUT) is set to a non-zero value, FLEXPART produces gridded output. When requiring binary files ([IOUT](configuration.md#IOUT)<8), separate files are created for every output time step ([LOUTSTEP](configuration.md#LOUTSTEP)), species and domain (mother and, if requested, nest). The naming convention for these files is grid_type_date_nnn. When requiring NetCDF output ([IOUT](configuration.md#IOUT)>8), this information is all contained in one file for the mother grid, and one for a possible nested grid ([NESTED_OUTPUT](configuration.md#NESTED_OUTPUT)). When [IPOUT](configuration.md#IPOUT) is switched on, this information is also contained in the **partoutput_nnn.nc** files.

| Name | Format | Switches | Description of contents |
| ---- | ------ | -------- | ----------------------- |
| ** *Header* ** | | | |
| **`header`** | binary | [IOUT](configuration.md#IOUT)<8 | run metadata + ancillary data, included in **grid_conc_date.nc** and **partoutput_date.nc** when [IOUT](configuration.md#IOUT)>8 and [IPOUT](configuration.md#IPOUT)=1, respectively. |
| **`header_nest`** | binary | [NESTED_OUTPUT](configuration.md#NESTED_OUTPUT)=1 [IOUT](configuration.md#IOUT)<8 | run metadata + ancillary data, included in **grid_conc_date_nest.nc** and **partoutput_date_nest.nc** when [IOUT](configuration.md#IOUT)>8 and [IPOUT](configuration.md#IPOUT)=1, respectively. |
| **`header_txt`** | text | [IOUT](configuration.md#IOUT)<8 | human-readable run metadata (from [COMMAND](configuration.md#command)) |
| **`header_txt_releases`** | text | [IOUT](configuration.md#IOUT)<8 | human-readable run metadata (from [RELEASES](configuration.md#releases) or **part_ic.nc**) |
| **`dates`** | text | [IOUT](configuration.md#IOUT)<8 | time series: dates of output files |
| ** *Gridded data* ** | | | |
| **`grid_conc_date_nnn`** | binary | [LDIRECT](configuration.md#ldirect)=1 [IOUT](configuration.md#IOUT)=1,3,5 | 3D tracer mass density and 2D deposition |
| **`grid_pptv_date_nnn`** | binary | [LDIRECT](configuration.md#ldirect)=1 [IOUT](configuration.md#IOUT)=2,3 | 3D tracer volume mixing ratio and 2D deposition |
| **`grid_time_date_nnn`** | binary | [LDIRECT](configuration.md#ldirect)=-1 [IOUT](configuration.md#IOUT)=1 | 3D sensitivity of atmospheric receptor to emissions |
| **`grid_drydep_date_nnn`** | binary | [LDIRECT](configuration.md#ldirect)=-1 [IOUT](configuration.md#IOUT)=1 [IND_RECEPTOR](configuration.md#IND_RECEPTOR)=3 | 3D sensitivity of dry deposition receptor to emissions |
| **`grid_wetdep_date_nnn`** | binary | [LDIRECT](configuration.md#ldirect)=-1 [IOUT](configuration.md#IOUT)=1 [IND_RECEPTOR](configuration.md#IND_RECEPTOR)=4 | 3D sensitivity of wet deposition receptor to emissions |
| **`grid_conc_date.nc`** | NetCDF | [LDIRECT](configuration.md#ldirect)=1 [IOUT](configuration.md#IOUT)=9,10,11,13 | 3D tracer and 2D wet and dry deposition |
| **`grid_time_date.nc`** | NetCDF | [LDIRECT](configuration.md#ldirect)=-1 [IOUT](configuration.md#IOUT)=9 | 3D sensitivity of atmospheric receptor to emissions |
| **`grid_drydep_date.nc`** | NetCDF | [LDIRECT](configuration.md#ldirect)=-1 [IOUT](configuration.md#IOUT)=9 [IND_RECEPTOR](configuration.md#IND_RECEPTOR)=3 | 3D sensitivity of dry deposition receptor to emissions |
| **`grid_wetdep_date.nc`** | NetCDF | [LDIRECT](configuration.md#ldirect)=-1 [IOUT](configuration.md#IOUT)=9 [IND_RECEPTOR](configuration.md#IND_RECEPTOR)=4 | 3D sensitivity of wet deposition receptor to emissions |
| **`grid_initial_nnn`** | binary | [LDIRECT](configuration.md#ldirect)=-1 [LINIT_COND](configuration.md#LINIT_COND)>0 | 3D sensitivity of receptor concentrations and deposition to initial conditions |
| ** *Nested gridded data* ** | | | |
| **`grid_conc_nest_date_nnn`** | binary | [NESTED_OUTPUT](configuration.md#NESTED_OUTPUT)=1 [LDIRECT](configuration.md#ldirect)=1 [IOUT](configuration.md#IOUT)=1,3,5 | 3D tracer mass density and 2D deposition |
| **`grid_pptv_nest_date_nnn`** | binary | [NESTED_OUTPUT](configuration.md#NESTED_OUTPUT)=1 [LDIRECT](configuration.md#ldirect)=1 [IOUT](configuration.md#IOUT)=2,3 | 3D tracer volume mixing ratio and 2D deposition |
| **`grid_time_nest_date_nnn`** | binary | [NESTED_OUTPUT](configuration.md#NESTED_OUTPUT)=1 [LDIRECT](configuration.md#ldirect)=-1 [IOUT](configuration.md#IOUT)=1 | 3D sensitivity of atmospheric receptor to emissions |
| **`grid_drydep_nest_date_nnn`** | binary | [NESTED_OUTPUT](configuration.md#NESTED_OUTPUT)=1 [LDIRECT](configuration.md#ldirect)=-1 [IOUT](configuration.md#IOUT)=1 [IND_RECEPTOR](configuration.md#IND_RECEPTOR)=3 | 3D sensitivity of dry deposition receptor to emissions |
| **`grid_wetdep_nest_date_nnn`** | binary | [NESTED_OUTPUT](configuration.md#NESTED_OUTPUT)=1 [LDIRECT](configuration.md#ldirect)=-1 [IOUT](configuration.md#IOUT)=1 [IND_RECEPTOR](configuration.md#IND_RECEPTOR)=4 | 3D sensitivity of wet deposition receptor to emissions |
| **`grid_conc_nest_date.nc`** | NetCDF | [NESTED_OUTPUT](configuration.md#NESTED_OUTPUT)=1 [LDIRECT](configuration.md#ldirect)=1 [IOUT](configuration.md#IOUT)=9,10,11,13 | 3D tracer and 2D wet and dry deposition |
| **`grid_time_nest_date.nc`** | NetCDF | [NESTED_OUTPUT](configuration.md#NESTED_OUTPUT)=1 [LDIRECT](configuration.md#ldirect)=-1 [IOUT](configuration.md#IOUT)=9 | 3D sensitivity of atmospheric receptor to emissions |
| **`grid_drydep_nest_date.nc`** | NetCDF | [NESTED_OUTPUT](configuration.md#NESTED_OUTPUT)=1 [LDIRECT](configuration.md#ldirect)=-1 [IOUT](configuration.md#IOUT)=9 [IND_RECEPTOR](configuration.md#IND_RECEPTOR)=3 | 3D sensitivity of dry deposition receptor to emissions |
| **`grid_wetdep_nest_date.nc`** | NetCDF | [NESTED_OUTPUT](configuration.md#NESTED_OUTPUT)=1 [LDIRECT](configuration.md#ldirect)=-1 [IOUT](configuration.md#IOUT)=9 [IND_RECEPTOR](configuration.md#IND_RECEPTOR)=4 | 3D sensitivity of wet deposition receptor to emissions |
| ** *Particle data* ** | | | |
| **`partoutput_date.nc`** | NetCDF | [IPOUT](configuration.md#IPOUT)=1,2,3 | Data at particle level. Output fields set in [PARTOPTIONS](configuration.md#PARTOPTIONS) |
| **`partinit_date.nc`** | NetCDF | [IPOUT](configuration.md#IPOUT)=1,2,3 [IPIN](configuration.md#IPIN)=1 | Initial particle data at t=0. Output fields set in [PARTOPTIONS](configuration.md#PARTOPTIONS) |
| **`restart_date`** | binary | [LOUTRESTART](configuration.md#LOUTRESTART)>=0 | Binary restart files are written to file at each [LOUTRESTART](configuration.md#LOUTRESTART) interval, see [Restarting a simulation](configuration.md#RESTART) |