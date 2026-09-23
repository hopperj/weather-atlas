# FLEXPART documentation and primary papers

## Mechanics documentation

The complete FLEXPART 11 manual source is bundled with the release at:

[`../documentation/docs/`](../documentation/docs/)

Start with:

1. [`../documentation/docs/index.md`](../documentation/docs/index.md)
2. [`../documentation/docs/building.md`](../documentation/docs/building.md)
3. [`../documentation/docs/configuration.md`](../documentation/docs/configuration.md)
4. [`../documentation/docs/transport.md`](../documentation/docs/transport.md)
5. [`../documentation/docs/evolution.md`](../documentation/docs/evolution.md)
6. [`../documentation/docs/LCM.md`](../documentation/docs/LCM.md)
7. [`../documentation/docs/output.md`](../documentation/docs/output.md)

The live version is <https://flexpart.img.univie.ac.at/docs/>.

## Recommended paper order

### Core model

1. [`papers/2024_Bakels_FLEXPART_v11.pdf`](papers/2024_Bakels_FLEXPART_v11.pdf) —
   current model architecture, η-coordinate transport, wet scavenging,
   settling, OpenMP, restart/initial-condition support, and validation.
2. [`papers/2019_Pisso_FLEXPART_v10.4.pdf`](papers/2019_Pisso_FLEXPART_v10.4.pdf) —
   the most complete pre-v11 description of turbulence, convection,
   deposition, forward/backward calculations, and model configuration.
3. [`papers/2005_Stohl_FLEXPART_v6.2.pdf`](papers/2005_Stohl_FLEXPART_v6.2.pdf) —
   foundational technical description of the model formulation.
4. [`papers/2004_Seibert_Frank_backward_source_receptor.pdf`](papers/2004_Seibert_Frank_backward_source_receptor.pdf) —
   mathematical basis for backward simulations and source–receptor matrices.

### Numerical and physical methods

- [`papers/2018_Hittmeir_conservative_interpolation.pdf`](papers/2018_Hittmeir_conservative_interpolation.pdf) —
  conservative interpolation of extensive quantities.
- [`papers/2017_Eckhardt_backward_deposition.pdf`](papers/2017_Eckhardt_backward_deposition.pdf) —
  backward sensitivities for deposited mass.
- [`papers/2014_Thompson_Stohl_FLEXINVERT.pdf`](papers/2014_Thompson_Stohl_FLEXINVERT.pdf) —
  Bayesian flux inversion based on FLEXPART sensitivities.

### Meteorological-driver variants

- [`papers/2013_Brioude_FLEXPART_WRF_v3.1.pdf`](papers/2013_Brioude_FLEXPART_WRF_v3.1.pdf)
- [`papers/2016_Cassiani_FLEXPART_NorESM_CAM.pdf`](papers/2016_Cassiani_FLEXPART_NorESM_CAM.pdf)
- [`papers/2019_Verreyken_FLEXPART_AROME.pdf`](papers/2019_Verreyken_FLEXPART_AROME.pdf)

## Additional bibliography

[`literature_title_matches.csv`](literature_title_matches.csv) contains 292
OpenAlex records that name FLEXPART in the title. It includes model papers,
extensions, comparisons, and named applications; it is broader than the
curated material above.

