# DMeRates Metadata For Fig. 22 Fluxes

After running the three DaMaSCUS-SUN configs, copy each
`results/<ID>/Differential_SRDM_Flux.txt` to the corresponding validation
filename and register it with metadata like the entries below.

## Required Parser Metadata

```yaml
- family: DPLM
  m_chi_eV: 10000.0
  sigma_e_cm2: 1.0e-35
  path: fig22_validation/srdm_dphidv_DPLM_fig22_mchi_10keV_sigmae_1e-35.txt
  columns: [v_km_s, dPhi_dv_cm-2_s-1_km_s-1]
  velocity_units: km/s
  flux_units: cm^-2 s^-1 (km/s)^-1
  flux_type: isotropic_angle_averaged
  loader_conversion: convert dPhi/dv to dPhi/d(v/c)

- family: DPLM
  m_chi_eV: 100000.0
  sigma_e_cm2: 1.0e-35
  path: fig22_validation/srdm_dphidv_DPLM_fig22_mchi_100keV_sigmae_1e-35.txt
  columns: [v_km_s, dPhi_dv_cm-2_s-1_km_s-1]
  velocity_units: km/s
  flux_units: cm^-2 s^-1 (km/s)^-1
  flux_type: isotropic_angle_averaged
  loader_conversion: convert dPhi/dv to dPhi/d(v/c)

- family: DPLM
  m_chi_eV: 1000000.0
  sigma_e_cm2: 1.0e-35
  path: fig22_validation/srdm_dphidv_DPLM_fig22_mchi_1MeV_sigmae_1e-35.txt
  columns: [v_km_s, dPhi_dv_cm-2_s-1_km_s-1]
  velocity_units: km/s
  flux_units: cm^-2 s^-1 (km/s)^-1
  flux_type: isotropic_angle_averaged
  loader_conversion: convert dPhi/dv to dPhi/d(v/c)
```

The loader mainly needs `family`, `m_chi_eV`, `sigma_e_cm2`, `path`, column
order, and units. The other fields make the convention explicit.

## Provenance Metadata

Keep this with the generated files or in a sidecar JSON/YAML file:

```yaml
source: DaMaSCUS-SUN
damascus_sun_commit: fd6900fc1ae88d0888d4762befea0afcd0f3b14a
mediator: dark_photon
DM_interaction: "Dark photon"
DM_form_factor: "Long-Range"
dark_photon_mass: 0
sigma_convention: sigma_e_bar
sigma_e_cm2: 1.0e-35
use_medium_effects: true
zeta: 0.0
sample_size: 100000
interpolation_points: 1000
isoreflection_rings: 1
distance: 1 AU
velocity_binning: 300 linear points from run-dependent minimum speed to 1.05 * max sampled outgoing speed
random_seed: not fixed; std::random_device per MPI worker
flux_type: isotropic_angle_averaged
output_columns:
  - v in km/s
  - dPhi/dv in cm^-2 s^-1 (km/s)^-1
```

This provenance is what confirms the files are DPLM/light-mediator,
`sigma_e_bar = 1.0e-35 cm^2`, angle-averaged fluxes rather than DPC/contact or
isoreflection-ring outputs.
