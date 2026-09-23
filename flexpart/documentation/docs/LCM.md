# Linear Chemistry Module
The Linear Chemistry Module (LCM) is based on the initial work of [Henne et al.](https://doi.org/10.5281/zenodo.1249190) who developed the FLEXPART-CTM model from FLEXPART 8, and was first described in [Groot Zwaaftink et al.](https://gmd.copernicus.org/articles/11/4469/2018/). This model was an extension of the domain-filling capability of FLEXPART and added the possibility to initialise particles' mixing ratio from pre-defined fields and to account for the influence of surface fluxes and simple linear chemistry on the particles' mass.

## How to run LCM
To run the LCM the following OPTIONS files are used and need to be edited (see also the Appendix for example OPTIONS files):

1. COMMAND: choose the following options:
	- LDIRECT= 1 (forward simulation)
	- MDOMAINFILL = 1 (domain-filling mode)
	- IND_SOURCE = 1 (releases units of mass)
	- IND_RECEPTOR = 1 (receptor units of mass)
	- LCMOUTPUT = 1 (uses the LCM initialization and output formats)

2. RELEASES: specify the following:
	- NSPEC: number of species including the mandatory species AIRTRACER
	- SPECNUM_REL: species number in the directory SPECIES (note AIRTRACER must be the first species)
	- LON1: left longitude of release box for global domain
	- LON2: right longitude of release box for global domain
	- LAT1: lower latitude of release box for global domain
	- LAT2: upper latitude of release box for global domain
	- PARTS: total number of particles to be used

- INITCONC: specifies input for initializing the mixing ratios

- OUTGRID: specifies the domain and vertical levels for the gridded output

- REAGENTS (optional): specifies chemical reagents for reactions (the corresponding rate constants are given in the SPECIES files)

- RECEPTORS (optional): specifies the locations and times of receptors where mixing ratios should be output.

- SATELLITES (optional): specifies paths and input file names of satellite retrievals for which mixing ratios should be output. Input files need to be generated from a satellite pre-processor, prep_satellite, and can be created using software obtainable from [flexinvertplus](https://git.nilu.no/flexpart/flexinvertplus).