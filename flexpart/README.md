![](https://www.flexpart.eu/chrome/site/flexpart_banner.png)
# Welcome to Flexpart - The Lagrangian particle dispersion model

This is the main development site @ University of Vienna.

Other references:

- [FLEXPART.eu](https://flexpart.eu)
- [FLEXPART@NILU](https://git.nilu.no/flexpart/flexpart)

### What is this repository for?

* This repository contains versions of the Lagrangian model FLEXPART
* Development versions
* Issues on the FLEXPART model, [tickets](https://gitlab.phaidra.org/flexpart/flexpart/-/issues)/[mail](mailto:gitlab.phaidra+flexpart-flexpart-456-issue-@univie.ac.at)
* Feature requests for future versions

## Getting started with Flexpart

The model is written in Fortran. It needs to be compiled for the architecture that runs it. Please have a look at the instructions on building FLEXPART available [here](./documentation/docs/building.md) or [online](https://flexpart.img.univie.ac.at/docs). There is also a containerized version of FLEXPART available.


### Contribution guidelines

* The version contributed should compile on a reference version of the system and compiler. 
   - `FLEXPART 10.4` used as a reference gfortran 5.4 on Ubuntu 16.04
   - `FLEXPART 11` uses as a reference gfortran 8.5.0 on AlmaLinux 8/RockyLinux 8 or gfortran 11.4.1 on RockyLinux 9

* Code contribution including new features and bug fixes should be complemented with appropriate tests
   An essential test consists of a set of input files and directories that allow FLEXPART to run.
   A test can be accompanied by output files for verification
* Code review
* report issues via mail to [support](mailto:gitlab.phaidra+flexpart-flexpart-456-issue-@univie.ac.at)
* become an active developer and request a user account on gitlab.
