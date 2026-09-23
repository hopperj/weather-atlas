# Examples

Since its inception, FLEXPART has proven to be a valuable tool for studying a wide range of environmental problems both for the research community as well as in operational settings. Some examples where FLEXPART was used in the literature are: 

- Studying the transport of heat and water in the atmosphere: [Baier et al. 2022](https://doi.org/10.1029/2022GL100906), [Peng et al. 2022](https://doi.org/10.1175/JCLI-D-21-0289.1).
- Volcanic and wildfire plumes: [Stohl et al. 2006](https://doi.org/10.1029/2006JD007216), [Stohl et al. 2011](https://doi.org/10.5194/acpd-11-5541-2011), [Moxnes et al. 2014](https://doi.org/10.1002/2013JD021129).
- Transport and fall-out after nuclear accidents or explosions: [Stohl et al. 2012](https://doi.org/10.5194/acp-12-2313-2012), [Arnold et al. 2015](https://doi.org/10.1016/j.jenvrad.2014.02.013).
- Transport of aerosols such as dust: [Zwaaftink et al. 2017](https://doi.org/10.5194/acp-17-10865-2017), [Ryder et al. 2019](https://doi.org/10.5194/acp-19-15353-2019).
- The interpretation of biogenic secondary organic aerosol compound measurements: [Martinsson et al. 2017](https://doi.org/10.5194/acp-17-11025-2017).
- Transport of pollutants into remote regions like the Arctic: [Dada et al. 2022](https://doi.org/10.1038/s41467-022-32872-2), [Zhu et al. 2020](https://doi.org/10.5194/acp-20-1641-2020).
- The interpretation of ice cores: [Eckhardt et al. 2023](https://doi.org/10.1038/s41467-022-35660-0).
- Modelling emission sensitivities of greenhouse gases: [Vojta et al. 2022](https://doi.org/10.5194/gmd-15-8295-2022).

## <a name="cases"></a>Example cases
The range of FLEXPART capabilities comes with a complicated set of option files (see [**option files**](configuration.md#options)), which can be overwhelming to new users. Therefore, we have outlined the settings of three common groups of simulations below, which correspond to the test cases used in the publication of FLEXPART 11.

Each set of option files can be found in the repository in the 'examples' directory. The `IGBP_int1.dat`, `sfcdata.t`, `sfcdepo.t` files are not present here, but can be found in the 'options' directory in the repository.

### Case Tracer
This case is useful for studying transport of heat and water through the global atmosphere. It is a domain-filling simulation, with 10 million particles representing a passive air tracer distributed across the globe following air density. Every hour, all particle information but no gridded output is written to NetCDF files. The example runs for only 5 hours, using 10 minute time-steps, and the turbulence options are set to CTL=10 and IFINE=10.

### Case Aerosol
This case serves as a template for option files using aerosol particles, i.e. tracing pollutants. Case Aerosol simulations generally take much longer than Case Tracer simulations, on one hand because of the extra computations in the wet and dry deposition and gravitational settling routines and on the other hand because of all particles starting within the ABL, where solving the Langevin equations of the turbulence parameterisation requires very short time steps. 

This is a very general example, where 1 million particles representing spherical aerosols with a diameter of 50 micrometer are initially homogeneously distributed in the bottom 100 meters across the globe. Every hour, gridded properties are printed to NetCDF files on the same horizontal resolution as the input data (0.5° by 0.5° global grid), and four vertical levels. The example runs for only 5 hours, using 15 minute time-steps, and turbulence options CTL=10 and IFINE=4. 
MAXTHREADGRID is set to 16, meaning that the gridded computations are using a maximum of 16 threads. The efficiency of this setting should be carefully checked when changing the dimensions of the grid and the number of particles.

### Case Nuclear
This example includes a nested input and output grid over Europe with 0.25° by 0.25°. Using the RELEASES file, 1 million particles representing xenon-133 are released at a single location, using the CBL option for skewed turbulence in the ABL and CTL=40 and IFINE=5. MAXTHREADGRID is set to 1, meaning that gridded computations are conducted on a single thread.