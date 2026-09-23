# Flexpart Testing

There are two different sets of Flexpart testing:

1. Testing basic functionality of different options
2. Testing quality of results


## Testing basic functionality

There are several options that can be tested with different options.

```ini
***************************************************************************************************************
*                                                                                                             *
*      Input file for the Lagrangian particle dispersion model FLEXPART                                       *
*                           Please select your options                                                        *
*                                                                                                             *
***************************************************************************************************************
&COMMAND

BINARY:
 LDIRECT=               1, ! Simulation direction in time   ; 1 (forward) or -1 (backward)


FIXED
 IBDATE=         20120101, ! Start date of the simulation   ; YYYYMMDD: YYYY=year, MM=month, DD=day  
 IBTIME=           060000, ! Start time of the simulation   ; HHMISS: HH=hours, MI=min, SS=sec; UTC
 IEDATE=         20120101, ! End date of the simulation     ; same format as IBDATE 
 IETIME=           120000, ! End  time of the simulation    ; same format as IBTIME
 LOUTSTEP=           3600, ! Interval of model output; average concentrations calculated every LOUTSTEP (s)  
 LOUTAVER=           3600, ! Interval of output averaging (s)
 LOUTSAMPLE=          900, ! Interval of output sampling  (s), higher stat. accuracy with shorter intervals
 LSYNCTIME=           900, ! All processes are synchronized to this time interval (s)
 IFINE=                 4, ! Reduction for time step in vertical transport, used only if CTL>1


BINARY -1 off
 LOUTRESTART=       86400, ! Interval of writing restart files (s)
 
BINARY 10 on
 CTL=          -5.0000000, ! CTL>1, ABL time step = (Lagrangian timescale (TL))/CTL, uses LSYNCTIME if CTL<0


OPTIONS: 0,1,2,3,4,5 (9,10,11,12,13)
 IOUT=                  1, ! Gridded output type: [0]off [1]mass 2]pptv 3]1&2 4]plume 5]1&4, +8 for NetCDF output     
OPTIONS: 0,1,2
 IPOUT=                 0, ! Particle position output: 0]off 1]every output 2]only at end
BINARY:
 LSUBGRID=              0, ! Increase of ABL heights due to sub-grid scale orographic variations;[0]off 1]on 
 LCONVECTION=           1, ! Switch for convection parameterization;0]off [1]on
 LAGESPECTRA=           0, ! Switch for calculation of age spectra (needs AGECLASSES);[0]off 1]on

OPTIONS: 0, 1 (needs a restart file), 2 (no), 3 (lucie file), 4 depends on 3 (2 files)
 IPIN=                  0, ! Warm start from particle dump; [0]no 1]from restart.bin file 2]from previous partoutput file 3]self made initial conditions 4]restart.bin and self made initial conditions
 
BINARY:
 IOUTPUTFOREACHRELEASE= 1, ! Separate output fields for each location in the RELEASE file; [0]no 1]yes 
 IFLUX=                 0, ! Output of mass fluxes through output grid box boundaries
 MDOMAINFILL=           0, ! Switch for domain-filling, if limited-area particles generated at boundary

OPTIONS: ????
 IND_SOURCE=            1, ! Unit to be used at the source; [1]mass 2]mass mixing ratio 
 IND_RECEPTOR=          1, ! Unit to be used at the receptor; [0]no receptor [1]mass 2]mass mixing ratio 3]wet depo. 4]dry depo.
 
BINARY: 
 MQUASILAG=             0, ! Quasi-Lagrangian mode to track individual numbered particles 
 NESTED_OUTPUT=         0, ! Output also for a nested domain 

OPTIONS: ???  (only with binary, option 5)
 LINIT_COND=            0, ! Output sensitivity to initial conditions (bkw mode only) [0]off 1]conc 2]mmr 

OPTIONS: (only with binary, option 5)
 SURF_ONLY=             0, ! Output only for the lowest model layer, used w/ LINIT_COND=1 or 2
 
BINRAY: (CTL > 10, IFINE > 10) ???
 CBLFLAG=               0, ! Skewed, not Gaussian turbulence in the convective ABL, need large CTL and IFINE
 
????
 OHFIELDS_PATH= "../../flexin/", ! Default path for OH file
 
OPTIONS: (depends on wind fields) ???
 NXSHIFT=             359, ! Shift of the global meteorological data. Default 359 for ECMWF and 0 for GFS if not given
 /
```