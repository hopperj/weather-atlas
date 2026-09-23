# Containers

There are two most commonly used container formats available:

1. Docker/Podman
2. Singularity/Apptainer

with FLEXPART and recipes can be found in containers folder.

Since version 11, FLEXPART is also available as a container. There is a Dockerfile and some instructions on how to build the container from scratch using for example podman/docker or singularity/apptainer:

Specifications:
- compiled using `march=core-avx2`, compatible with CPUs above AVX2 (since Haswell or Zen)
- ECCodes (from package manager or manual build a specific version)

## Building the container image

The first step is always to build the container image.

Building the docker/podman container

```sh
# build container using podman (adjust for docker)
$ ./containers/build.sh

Building flexpart v11 branch: master : 2464aef
Press any key to continue or Ctrl+C to exit...
STEP 1/16: FROM rockylinux:9-minimal
...
STEP 16/16: CMD ["FLEXPART_ETA"]
--> Using cache 200844128a6919007417f3fa905221c8dbdea4bb285895ef80e89d3df80274b6
COMMIT flexpartv11-master:2464aef
--> 200844128a69
Successfully tagged localhost/flexpartv11-master:2464aef
200844128a6919007417f3fa905221c8dbdea4bb285895ef80e89d3df80274b6
# finished
```

Building the singularity/apptainer image

```sh
# using singularity/apptainer for running FLEXPART
# there might be some warnings about EPERM (can be ignored)
$ ./containers/build.sh apptainer

Building flexpart v11 branch: master : 2464aef
Press any key to continue or Ctrl+C to exit...
INFO:    Starting build...
INFO:    Adding environment to container
INFO:    Adding startscript
INFO:    Adding runscript
INFO:    Creating SIF file...
INFO:    Build complete: flexpartv11-master-2464aef.sif
# finished
```

## Running the container image

running using podman/docker, can be used without a mount to the local directory, because docker/podmann containers have writable temporary spaces. The outputs will be only inside the container. Create a volume mount point to map the outputs, inputs to the host.

```sh
# simple run the container with default settings
podman run localhost/flexpartv11-master:2464aef
```

running using the singularity/apptainer, requires a mount (bind) point. The container image can not be changed during runtime. Outputs need to be written to the host. 

```sh
# running the container requires a writable output directory
# mounting the local directory to /output inside the container
apptainer run -B .:/output flexpartv11-master-2464aef.sif
```

it is possible to run FLEXPART (no ETA) and FLEXPART_ETA (default), because both executables are being build. To launch FLEXPART without ETA run:

```sh
# using podman
podman run localhost/flexpartv11-master:2464aef FLEXPART
# using apptainer
apptainer run -B .:/output flexpartv11-master-2464aef.sif FLEXPART
```

<details>
<summary>podman/docker flexpart run log</summary>
<pre><code class="shell">
Welcome, running FLEXPART 
Using defaults (/pathnames)
/options/
/output/
/inputs/
/inputs/AVAILABLE
Mount volumes to change inputs
Git: c5bdd94 HEAD -> master, origin/master, origin/HEAD Tue Nov 21 16:15:27 2023 +0100
EXECUTING FLEXPART
trying to execute: /src/FLEXPART_ETA
Executing: /src/FLEXPART_ETA
 Welcome to FLEXPART Version 11
 Git: undefined
 FLEXPART is free software released under the GNU General Public License.
 FLEXPART is running with ETA coordinates.
              ----------------               
  INFORMATION: SUBGRIDSCALE TERRAIN EFFECT IS
  NOT PARAMETERIZED DURING THIS SIMULATION.  
              ----------------               

 *********** WARNING  **********************************
 * FLEXPART running in parallel mode                   *
 * Number of uncertainty classes in                    *
 * set to number of threads:                1          *
 * All other computations are done with     8 threads. *
 *******************************************************

 FLEXPART WARNING: TIME DIFFERENCE BETWEEN TWO
 WIND FIELDS IS BIG. THIS MAY CAUSE A DEGRADATION
 OF SIMULATION QUALITY.
 ECMWF metdata detected
 NXSHIFT is set to           0
 grid dim:         181          91          92          92          91          92
 Vertical levels in ECMWF data:      92     92

 Mother domain:
  Longitude range: -178.00000 to  182.00000   Grid distance:    2.00000
  Latitude range :  -90.00000 to   90.00000   Grid distance:    2.00000

 Number of receptors:            2
 Releasepoints :            1
 reading SPECIES          24
 Particle shape SPHERE for particle          24
  
 SPECIES:  24  AIRTRACER   (GAS) 
   Wet removal for gases      is turned: OFF 
   Dry deposition for gases   is turned: OFF 
   Below-cloud scavenging: OFF
   In-cloud scavenging: OFF
 Particles released (numpartmax):        10000
 Total mass released: 1.0000000E+00
 Allocating fields for global output (x,y):           85          65
 Concentrations are calculated using kernel
 WARNING: turbulence switched off.
 Simulated     0.0 hours (            0 s),             0 particles
 Time:            0 seconds. Total spawned:           0 alive:           0 terminated:           0
 Allocating        10000  particles           0           0           0
 Finished allocation
 Time:          900 seconds. Total spawned:       10000 alive:       10000 terminated:           0
 Time:         1800 seconds. Total spawned:       10000 alive:       10000 terminated:           0
 Time:         2700 seconds. Total spawned:       10000 alive:       10000 terminated:           0
 Time:         3600 seconds. Total spawned:       10000 alive:       10000 terminated:           0
         3600 Seconds simulated:         10000 Particles:    Uncertainty:   0.000  0.000  0.000
 Time:         4500 seconds. Total spawned:       10000 alive:       10000 terminated:           0
 Time:         5400 seconds. Total spawned:       10000 alive:       10000 terminated:           0
 Time:         6300 seconds. Total spawned:       10000 alive:       10000 terminated:           0
 Time:         7200 seconds. Total spawned:       10000 alive:       10000 terminated:           0
         7200 Seconds simulated:         10000 Particles:    Uncertainty:   0.000  0.000  0.000
 Time:         8100 seconds. Total spawned:       10000 alive:       10000 terminated:           0
 Time:         9000 seconds. Total spawned:       10000 alive:       10000 terminated:           0
 Time:         9900 seconds. Total spawned:       10000 alive:       10000 terminated:           0
 Time:        10800 seconds. Total spawned:       10000 alive:       10000 terminated:           0
        10800 Seconds simulated:         10000 Particles:    Uncertainty:   0.000  0.000  0.000
 Read wind fields:   0.609375000      seconds
 Timemanager:    1.17187500      seconds,first timestep:    1.09375000     seconds
 Write particle files:    4.68750000E-02  seconds
 Total running time:    1.81250000      seconds
 tps,io,tot:    1.95312500E-02  0.131249994       1.81250000    
 CONGRATULATIONS: YOU HAVE SUCCESSFULLY COMPLETED A FLEXPART MODEL RUN!
FINISHED
</code></pre>
</details>


<details>
<summary>singularity/apptainer flexpart run log</summary>
<pre>
<code class="language-shell">
INFO:    gocryptfs not found, will not be able to use gocryptfs
Welcome, running FLEXPART 
Using defaults (/pathnames)
/options/
/output/
/inputs/
/inputs/AVAILABLE
Mount volumes to change inputs
Git: c5bdd94 HEAD -> master, origin/master, origin/HEAD Tue Nov 21 16:15:27 2023 +0100
EXECUTING FLEXPART
trying to execute: /src/FLEXPART_ETA
Executing: /src/FLEXPART_ETA
 Welcome to FLEXPART Version 11
 Git: undefined
 FLEXPART is free software released under the GNU General Public License.
 FLEXPART is running with ETA coordinates.
              ----------------               
  INFORMATION: SUBGRIDSCALE TERRAIN EFFECT IS
  NOT PARAMETERIZED DURING THIS SIMULATION.  
              ----------------               

 *********** WARNING  **********************************
 * FLEXPART running in parallel mode                   *
 * Number of uncertainty classes in                    *
 * set to number of threads:                1          *
 * All other computations are done with     8 threads. *
 *******************************************************

 FLEXPART WARNING: TIME DIFFERENCE BETWEEN TWO
 WIND FIELDS IS BIG. THIS MAY CAUSE A DEGRADATION
 OF SIMULATION QUALITY.
 ECMWF metdata detected
 NXSHIFT is set to           0
 grid dim:         181          91          92          92          91          92
 Vertical levels in ECMWF data:      92     92

 Mother domain:
  Longitude range: -178.00000 to  182.00000   Grid distance:    2.00000
  Latitude range :  -90.00000 to   90.00000   Grid distance:    2.00000

 Number of receptors:            2
 Releasepoints :            1
 reading SPECIES          24
 Particle shape SPHERE for particle          24
  
 SPECIES:  24  AIRTRACER   (GAS) 
   Wet removal for gases      is turned: OFF 
   Dry deposition for gases   is turned: OFF 
   Below-cloud scavenging: OFF
   In-cloud scavenging: OFF
 Particles released (numpartmax):        10000
 Total mass released: 1.0000000E+00
 Allocating fields for global output (x,y):           85          65
 Concentrations are calculated using kernel
 WARNING: turbulence switched off.
 Simulated     0.0 hours (            0 s),             0 particles
 Time:            0 seconds. Total spawned:           0 alive:           0 terminated:           0
 Allocating        10000  particles           0           0           0
 Finished allocation
 Time:          900 seconds. Total spawned:       10000 alive:       10000 terminated:           0
 Time:         1800 seconds. Total spawned:       10000 alive:       10000 terminated:           0
 Time:         2700 seconds. Total spawned:       10000 alive:       10000 terminated:           0
 Time:         3600 seconds. Total spawned:       10000 alive:       10000 terminated:           0
         3600 Seconds simulated:         10000 Particles:    Uncertainty:   0.000  0.000  0.000
 Time:         4500 seconds. Total spawned:       10000 alive:       10000 terminated:           0
 Time:         5400 seconds. Total spawned:       10000 alive:       10000 terminated:           0
 Time:         6300 seconds. Total spawned:       10000 alive:       10000 terminated:           0
 Time:         7200 seconds. Total spawned:       10000 alive:       10000 terminated:           0
         7200 Seconds simulated:         10000 Particles:    Uncertainty:   0.000  0.000  0.000
 Time:         8100 seconds. Total spawned:       10000 alive:       10000 terminated:           0
 Time:         9000 seconds. Total spawned:       10000 alive:       10000 terminated:           0
 Time:         9900 seconds. Total spawned:       10000 alive:       10000 terminated:           0
 Time:        10800 seconds. Total spawned:       10000 alive:       10000 terminated:           0
        10800 Seconds simulated:         10000 Particles:    Uncertainty:   0.000  0.000  0.000
 Read wind fields:   0.703125000      seconds
 Timemanager:    1.25000000      seconds,first timestep:    1.15625000     seconds
 Write particle files:    1.56250000E-02  seconds
 Total running time:    2.00000000      seconds
 tps,io,tot:    2.34375000E-02  0.143749997       2.00000000    
 CONGRATULATIONS: YOU HAVE SUCCESSFULLY COMPLETED A FLEXPART MODEL RUN!
FINISHED
</code></pre>
</details>

<details>
<summary>ncdump of default run output</summary>
<pre><code class="language-shell">
# check the output
ncdump -h grid_conc_20090101000000.nc
netcdf grid_conc_20090101000000 {
dimensions:
	time = UNLIMITED ; // (3 currently)
	longitude = 85 ;
	latitude = 65 ;
	height = 4 ;
	numspec = 1 ;
	pointspec = 1 ;
	nageclass = 1 ;
	nchar = 45 ;
	ncharrec = 16 ;
	numpoint = 1 ;
	receptor = UNLIMITED ; // (2 currently)
variables:
	int time(time) ;
		time:units = "seconds since 2009-01-01 00:00" ;
		time:calendar = "proleptic_gregorian" ;
	float longitude(longitude) ;
		longitude:long_name = "longitude in degree east" ;
		longitude:axis = "Lon" ;
		longitude:units = "degrees_east" ;
		longitude:standard_name = "grid_longitude" ;
		longitude:description = "grid cell centers" ;
	float latitude(latitude) ;
		latitude:long_name = "latitude in degree north" ;
		latitude:axis = "Lat" ;
		latitude:units = "degrees_north" ;
		latitude:standard_name = "grid_latitude" ;
		latitude:description = "grid cell centers" ;
	float height(height) ;
		height:units = "meters" ;
		height:positive = "up" ;
		height:standard_name = "height" ;
		height:long_name = "height above ground" ;
	char RELCOM(numpoint, nchar) ;
		RELCOM:long_name = "release point name" ;
	float RELLNG1(numpoint) ;
		RELLNG1:units = "degrees_east" ;
		RELLNG1:long_name = "release longitude lower left corner" ;
	float RELLNG2(numpoint) ;
		RELLNG2:units = "degrees_east" ;
		RELLNG2:long_name = "release longitude upper right corner" ;
	float RELLAT1(numpoint) ;
		RELLAT1:units = "degrees_north" ;
		RELLAT1:long_name = "release latitude lower left corner" ;
	float RELLAT2(numpoint) ;
		RELLAT2:units = "degrees_north" ;
		RELLAT2:long_name = "release latitude upper right corner" ;
	float RELZZ1(numpoint) ;
		RELZZ1:units = "meters" ;
		RELZZ1:long_name = "release height bottom" ;
	float RELZZ2(numpoint) ;
		RELZZ2:units = "meters" ;
		RELZZ2:long_name = "release height top" ;
	int RELKINDZ(numpoint) ;
		RELKINDZ:long_name = "release kind" ;
	int RELSTART(numpoint) ;
		RELSTART:units = "seconds" ;
		RELSTART:long_name = "release start relative to simulation start" ;
	int RELEND(numpoint) ;
		RELEND:units = "seconds" ;
		RELEND:long_name = "release end relative to simulation start" ;
	int RELPART(numpoint) ;
		RELPART:long_name = "number of release particles" ;
	float RELXMASS(numspec, numpoint) ;
		RELXMASS:long_name = "total release particle mass" ;
	int LAGE(nageclass) ;
		LAGE:units = "seconds" ;
		LAGE:long_name = "age class" ;
	int ORO(latitude, longitude) ;
		ORO:standard_name = "surface altitude" ;
		ORO:long_name = "outgrid surface altitude" ;
		ORO:units = "m" ;
	char receptor(receptor, ncharrec) ;
		receptor:long_name = "receptor name" ;
	float spec001_mr(nageclass, pointspec, time, height, latitude, longitude) ;
		spec001_mr:units = "ng m-3" ;
		spec001_mr:long_name = "AIRTRACER" ;
		spec001_mr:decay = -0.07001485f ;
		spec001_mr:weightmolar = 29.f ;
		spec001_mr:ohcconst = -9.e-10f ;
		spec001_mr:ohdconst = -9.9f ;
		spec001_mr:vsetaver = 0.f ;
	float receptor_conc001(receptor, time) ;
		receptor_conc001:units = "ng m-3" ;
		receptor_conc001:_FillValue = -1.f ;
		receptor_conc001:positive = "up" ;
		receptor_conc001:standard_name = "receptor_conc" ;
		receptor_conc001:long_name = "receptor_concentration" ;

// global attributes:
		:Conventions = "CF-1.6" ;
		:title = "FLEXPART model output" ;
		:git = "undefined" ;
		:source = "Version 11 model output" ;
		:history = "2023-11-21 16:22 +0100  created by mblaschek on NB513" ;
		:references = "Stohl et al., Atmos. Chem. Phys., 2005, doi:10.5194/acp-5-2461-200" ;
		:outlon0 = -25.f ;
		:outlat0 = 10.f ;
		:dxout = 1.f ;
		:dyout = 1.f ;
		:ldirect = 1 ;
		:ibdate = "20090101" ;
		:ibtime = "000000" ;
		:iedate = "20090101" ;
		:ietime = "030000" ;
		:loutstep = 3600 ;
		:loutaver = 3600 ;
		:loutsample = 900 ;
		:loutrestart = -1 ;
		:lsynctime = 900 ;
		:ctl = -0.2f ;
		:ifine = 1 ;
		:iout = 1 ;
		:ipout = 0 ;
		:lsubgrid = 0 ;
		:lconvection = 0 ;
		:lagespectra = 0 ;
		:ipin = 0 ;
		:ioutputforeachrelease = 0 ;
		:iflux = 0 ;
		:mdomainfill = 0 ;
		:ind_source = 1 ;
		:ind_receptor = 1 ;
		:mquasilag = 0 ;
		:nested_output = 0 ;
		:sfc_only = 0 ;
		:linit_cond = 0 ;
}
</code>
</pre>
</details>

## interactive shells

Interactive shells can be launched into containers, to have a look at configurations and to better understand what might go wrong. Podman/Docker allows to alter files inside of the container and save these changes. Singularity/Apptainer containers are not writeable, but acts like a normal executable with access to host files.

using the podman image with an interactive shell:

```sh
# using podman 
$ podman run -it localhost/flexpartv11-master:2464aef /bin/bash
Welcome, running FLEXPART 
Using defaults (/pathnames)                                         [        OK]
/options/
/output/
/inputs/
/inputs/AVAILABLE
Mount volumes to change inputs
Git: 2464aef
EXECUTING FLEXPART
Executing: /src//bin/bash                                           [    FAILED]
Executing: /bin/bash                                                [        OK]
bash-5.1# 
# now you are inside the container
bash-5.1# pwd
/src
# important directories are /input, /output, /src, /options
# it is possible to make changes in the podman container using
# podman commit 
bash-5.1# ./FLEXPART /pathnames
```

using the apptainer image with an interactive shell:

```sh
#
# using singularity/apptainer
$ apptainer run -B .:/output flexpartv11-master-2464aef.sif /bin/bash
# Check the directory, where you are and notice that FLEXPART and FLEXPART_ETA are available
$ pwd
/src
# run the example again
$ ./FLEXPART /pathnames

# or use (but this does not put you into /src)
$ apptainer shell -B .:/output flexpartv11-master-2464aef.sif
# check the directory, and notice that you are in the same directory as you where on your host.
$ pwd
/home/user/flexpart/or/so
# run the example again
$ /src/FLEXPART /pathnames
```

