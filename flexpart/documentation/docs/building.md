# Building

## <a name="download"></a>Download FLEXPART
There are two options to download _FLEXPART_:

  - **tar ball**

    You can download a tar ball with the latest release from the [_FLEXPART_ page](https://www.flexpart.eu/roadmap.html) and then untar the file:

        $ tar -xvf <flexpart_vX.X.tar>

  - **git repository**

    If you have git installed, you can clone the latest version from our git repository:

        $ git clone --single-branch --branch master https://gitlab.phaidra.org/flexpart/flexpart.git

### Compiler
_FLEXPART_ 11 is written in Fortran 2018. The following compilers can be used to compile _FLEXPART_:

  - GNU Fortran compiler version 8+ (`gfortran`)
  - Intel Fortran compiler (`ifort`)

For running _FLEXPART_ in parallel mode, a compiler supporting [OpenMP](https://www.openmp.org/) is required. In addition, libraries (in particular hdf5) should be compiled threadsafe.

### Libraries
_FLEXPART_ uses the following libraries:

  - [ecCodes](https://confluence.ecmwf.int/display/ECC)
  - [netCDF](https://docs.unidata.ucar.edu/netcdf-fortran/current/)

These libraries are usually available as packages in most Linux distributions and MacOS package managers. For example:

  - In Debian/Ubuntu: `sudo apt install libeccodes-dev libnetcdff` 
  - In MacOS + Homebrew: `brew install eccodes netcdf`

## <a name="compiling"></a>Compiling FLEXPART
_FLEXPART_ is compiled with [make](https://www.gnu.org/software/make/), which uses the makefile in the `src` subdirectory. Starting from the root directory, you can then compile _FLEXPART_ with the following steps:

    $ cd src/
    $ make -j -f <prefered_makefile>

This will create the executable `FLEXPART_ETA`. Note that this executable can only be used on ECMWF data.

### Parameters
Before compiling FLEXPART, you might want to change parameters defined in par_mod.f90

- `dp`, `sp`, `dep_prec`: Setting the precision of the simulation.
- `lusekerneloutput`: Switch for using a kernel for calculating concentrations/deposition. Default: **True**.
- `lparticlecountoutput`: Switch to set output units to number of particles per grid cell. Default: **False**.
- `numpf`: Number of precipitation fields read by the executable. This should correspond with the number of precipitation fields present in the meteorological data. Default: **1**.
- `lpartoutputperfield`: When using particle output (IPOUT=1), this switch sets if all selected fields are written to one netcdf file or a separate one for each field.
- Many parameters that govern the different parameter schemes within FLEXPART.

### Compiling FLEXPART without eta coordinates

    $ make -j -f <prefered_makefile> eta=no

This will create the executable `FLEXPART`

### Compiling FLEXPART without NetCDF libraries

    $ make -j -f <prefered_makefile> eta=<yes/no> ncf=no

This will create the executable `FLEXPART_BIN`, or `FLEXPART_ETA_BIN` for `eta=yes`.
### <a name="paths"></a>Paths
the makefile provided uses a predefined `CPATH` and `LIBRARY_PATH`, the default on most servers. If these paths are not available, you will need to edit the makefile, adding the correct paths manually.

### <a name="optimisation"></a>Optimisation
The default and recommended optimisation flags in the makefile are `-O3 -march=native -mtune=native -fopenmp`. If not requiring a parallelised version, the `-fopenmp` can be switched off without consequence.

### <a name="dependency"></a>Dependencies
At the bottom of the default makefile, one can find the list of modules an how they depend on each other in ascending order.