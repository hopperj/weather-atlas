# Evolution of particle properties
In FLEXPART, the modeling of particle movement involves a combination of interpolating properties from meteorological input data and computing properties that are intrinsic to each particle. This hybrid approach allows for a more comprehensive and realistic representation of particle behavior in the atmosphere.

In [**Particle transport**](transport.md), you can find how particles are advanced, using parameterisation schemes and meteorological data interpolated to the particle position. This interpolated meteorological data is necessary for computing the trajectories of particles, but such information can also be a valuable diagnostic tool on itself. For this reason, interpolated meteorological data along the trajectories of each particle, can be written to file setting the option [IPOUT](configuration.md#IPOUT) to a non-zero value in the [COMMAND](configuration.md#command) file.

In addition, FLEXPART goes beyond simple interpolation and incorporates intrinsic properties that are directly related to each individual particle. The main intrinsic property considered in the model is the mass of the particles. The mass of a particle can significantly impact its behavior in the atmosphere, affecting its movement and interactions with the environment (see [**Settling**](transport.md#settling). During the simulation, FLEXPART takes into account various processes that can modify the mass of particles over time. For instance, particles can undergo deposition ([**Dry deposition**](evolution.md#drydepo) and [**Wet deposition**](evolution.md#wetdepo), where they are partially removed from the atmosphere by settling onto surfaces (e.g., ground or vegetation). Additionally, for particles resulting from nuclear disasters or radioactive emissions, radioactive decay is another important process that leads to a reduction in particle mass over time (see [**Radioactive decay**](evolution.md#decay) and [**OH reaction**](evolution.md#ohreact)).

By considering these intrinsic properties, particularly the evolving mass of the particles, FLEXPART can simulate the transport, dispersion, and fate of pollutants, aerosols, and other substances in a more realistic manner. It allows the model to account for the varying lifetimes of different particles based on their specific properties and the environmental conditions they encounter.


## <a name="drydepo"></a>Dry deposition
In FLEXPART, the dry deposition module is used to calculate the dry deposition velocities of gases and particulate matter within the layer from 0 to 15 metres above ground (Eq. 48 in [Stohl et al. 2005](https://acp.copernicus.org/articles/5/2461/2005/)). Here, dry deposition is treated in a same way as in previous versions and can be found in `drydepo_mod.f90`. However, now the module considers different particle shapes as it is in the settling module (for details see [**Shape factor**](transport.md#settling)).

The limitation here is that the Stokes' number, which is used to calculate the deposition layer resistance, is not resolved for non-spherical particles and remains to be investigated. Therefore, in FLEXPART 11 the Stokes' number for particles of any shape is assumed to be similar to that for perfect spheres.

## <a name="wetdepo"></a>Wet deposition
The wet-deposition scheme in FLEXPART distinguishes between aerosols and gases and between in-cloud and below-cloud scavenging. In FLEXPART 11, cloud parameters and precipitation are interpolated to the particle position, and the scheme for below-cloud scavenging of aerosols has been replaced. Routines related to wet deposition are now collected in the `wetdepo_mod.f90` module. The revised wet-deposition scheme includes three changes with respect to the previous version:

1. **New below-cloud scavenging scheme for aerosols**: For below-cloud scavenging, the scheme of [Wang et al. 2014](https://doi.org/10.5194/gmd-7-799-2014) is used, which covers particles from 1 nm (nucleation mode) to 100 µm (coarse mode). This is important especially for larger particles like dust, sea salt, or pollen.

2. **Improved interpolation scheme for precipitation**: The interpolation scheme by [Hittmeir et al. 2018](https://doi.org/10.5194/gmd-11-2503-2018) is used for precipitation fields, which ensures the conservation of integral precipitation within each time interval, maintains continuity at interval boundaries, and conserves non-negativity.

3. **New cloud layer identification scheme**: To prevent unrealistic combinations of instantaneous cloud fields and accumulated precipitation fields, new steps are taken to identify clouds, including a threshold of relative humidity and minimum cloud thickness.

## <a name="decay"></a>Radioactive decay
FLEXPART can account for radioactive and/or chemical decay of particles by defining a half life $T_{1/2}$ (parameter [PDECAY](configuration.md#PDECAY) > 0 in the corresponding [SPECIES](configuration.md#species) file; off if [PDECAY](configuration.md#PDECAY) < 0). The decay affects the particle mass while traveling through the atmosphere as well as the deposited mass following:
$m(t + \Delta t) = m(t) e^{−\Delta t/\beta}$
with
$\beta = \frac{T_{1/2}}{ln(2)}$
The treatment of radioactive and/or chemical decay remains unchanged compared to v10.4 and we refer to [Pisso et al. 2019](https://gmd.copernicus.org/articles/12/4955/2019/) for a comparison with observations.

## <a name="ohreact"></a>OH reaction
Loss processes related to reactions with hydroxyl (OH) radicals are represented as a first-order, linear approximation in FLEXPART 11 --- identical to v10.4 and therefore only shortly summarized here; for a detailed description see [Pisso et al. 2019](https://gmd.copernicus.org/articles/12/4955/2019/).

The OH radical is the most important oxidant in the troposphere and although reactions with atmospheric gases can be highly non-linear (e.g., CH$_4$), a first-order, linear loss approximation using prescribed OH fields is possible (for FLEXPART 11: monthly averaged 3$^\circ$ x 5$^\circ$ OH fields with 17 vertical layers; following GEOS-Chem model by [Bey et al. 2001](https://agupubs.onlinelibrary.wiley.com/doi/abs/10.1029/2001JD000807) and read in from **OH\_variables.bin**). Hourly OH variations are accounted for by modifying the monthly fields with the hourly photolysis rate of ozone $j$ based on a simple could-free parameterization depending on the solar zenith angle:

$OH = \frac{j}{j^*} OH^*$

where $j^*$ and $OH^*$ are the monthly mean photolysis rate and OH concentration taken from **OH\_variables.bin**, respectively.

The OH reaction can be turned on by providing positive reaction rates in the corresponding [SPECIES](configuration.md#species) file (parameters [PCCONST](configuration.md#PCCONST), [PDCONST](configuration.md#PDCONST), and [PNCONST](configuration.md#PNCONST); turned off with negative values). The temperature-dependent OH reaction rate $\kappa$ (s$^{-1}$) is then calculated as:

$\kappa = C T^N e^{\frac{-D}{T}} OH$

where C, N and D are the species-specific constants defined in the [SPECIES](configuration.md#species) file. T is the absolute temperature, and $OH$ the OH concentration ([Atkinson 1997](https://pubs.aip.org/aip/jpr/article-abstract/26/2/215/241782/Gas-Phase-Tropospheric-Chemistry-of-Volatile)). The OH-related mass loss is then calculated as:

$m(t + \Delta t') = m(t) e^{−\kappa \Delta t'}$

with $\Delta t'$ being the reaction time step given by [LSYNCTIME](configuration.md#LSYNCTIME).

In order to be able to use higher spatially and temporally resolved OH fields, the user has to modify the OH-related FLEXPART subroutines (`readOHfield`, `gethourlyOH`, `ohreaction`, located in the **ohr\_mod.f90** module) to be able to read in and process these other OH fields.