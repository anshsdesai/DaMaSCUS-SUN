# Fig. 22 DPLM SRDM Flux Generation

This directory contains DaMaSCUS-SUN configs for generating high-statistics,
angle-averaged solar-reflected dark matter flux files for a DMeRates validation
against Fig. 22 of Emken, Essig, Xu 2024, arXiv:2404.10066.

I did not run the simulations. The files here define the intended production
runs and the post-run copy/registration steps.

## What Was Checked

- DaMaSCUS-SUN reads `DM_mass` in MeV and `DM_cross_section_electron` in cm^2.
- The dark-photon model is selected with `DM_interaction = "Dark photon"`.
- The ultralight/light-mediator model is selected with
  `DM_form_factor = "Long-Range"`. This sets the dark photon mass to zero in
  `DM_Particle_Dark_Photon::Set_FormFactor_DM`.
- `DM_cross_section_electron` is passed directly to
  `Set_Interaction_Parameter(..., "Electrons")`, so the configs use the
  requested DM-electron reference cross section rather than an independently
  chosen proton cross section.
- For dark photon runs, the code derives the displayed proton cross section
  from the same kinetic mixing. The relation is
  `sigma_p_bar / sigma_e_bar = (mu_chi_p / mu_chi_e)^2`.
- For `DM_form_factor = "Long-Range"`, `use_medium_effects` is forced on by
  the configuration loader even if a config says false. These configs set it
  explicitly to true.
- `isoreflection_rings = 1` is the angle-averaged path. It writes
  `Differential_SRDM_Flux.txt` at 1 AU. Multi-ring output writes
  `Differential_SRDM_Flux_<ring>.txt` and is directional/ring-resolved.
- The exported flux has two columns: speed in km/s and `dPhi/dv` in
  `cm^-2 s^-1 (km/s)^-1`.

The paper states that the SRDM differential flux is evaluated at 1 AU and uses
the three masses `10 keV`, `100 keV`, and `1 MeV` for the ultralight
dark-photon flux comparison. It also states the SHM density and velocity
dispersion convention as approximately `rho = 0.3 GeV/cm^3` and
`v0 = 220 km/s`. Fig. 22 is a silicon-form-factor comparison using these SRDM
fluxes as inputs; DaMaSCUS-SUN produces the flux, while the silicon recoil
spectrum/form-factor comparison is downstream in DMeRates.

Primary references checked:

- arXiv:2404.10066 abstract and setup: https://arxiv.org/abs/2404.10066
- Paper PDF, SHM setup and SRDM flux description: https://arxiv.org/pdf/2404.10066

## Configs

- `config_fig22_DPLM_mchi_10keV_sigmae_1e-35.cfg`
- `config_fig22_DPLM_mchi_100keV_sigmae_1e-35.cfg`
- `config_fig22_DPLM_mchi_1MeV_sigmae_1e-35.cfg`

Each config uses:

- `run_mode = "Parameter point"`
- `sample_size = 100000`
- `interpolation_points = 1000`
- `isoreflection_rings = 1`
- `DM_interaction = "Dark photon"`
- `DM_form_factor = "Long-Range"`
- `DM_cross_section_electron = 1.0e-35`
- `use_medium_effects = true`
- `zeta = 0.0`
- `DM_local_density = 0.3`
- `SHM_v0 = 220.0`
- `SHM_vObserver = (11.1, 232.2, 7.3)`
- `SHM_vEscape = 544.0`

Note: there are untracked local helper configs in `bin/` that use a
`v0 = 238 km/s`, `(11.1, 245.2, 7.3)` observer convention. I used the
paper/README SHM convention here for Fig. 22 validation. If the validation target
turns out to have used the newer local helper convention, change only the
three SHM lines consistently.

## Run Commands

From a built tree, run from `bin/` as the README expects. Replace `NPROC` with
the desired MPI process count.

```bash
cd /home/ansh/Projects/SENSEI/DaMaSCUS-SUN/bin
mpirun -n NPROC ./DaMaSCUS-SUN ../fig22_validation/config_fig22_DPLM_mchi_10keV_sigmae_1e-35.cfg
mpirun -n NPROC ./DaMaSCUS-SUN ../fig22_validation/config_fig22_DPLM_mchi_100keV_sigmae_1e-35.cfg
mpirun -n NPROC ./DaMaSCUS-SUN ../fig22_validation/config_fig22_DPLM_mchi_1MeV_sigmae_1e-35.cfg
```

DaMaSCUS-SUN will write:

- `results/fig22_DPLM_mchi_10keV_sigmae_1e-35_avg/Differential_SRDM_Flux.txt`
- `results/fig22_DPLM_mchi_100keV_sigmae_1e-35_avg/Differential_SRDM_Flux.txt`
- `results/fig22_DPLM_mchi_1MeV_sigmae_1e-35_avg/Differential_SRDM_Flux.txt`

Copy or register those as:

```bash
cp ../results/fig22_DPLM_mchi_10keV_sigmae_1e-35_avg/Differential_SRDM_Flux.txt ../fig22_validation/srdm_dphidv_DPLM_fig22_mchi_10keV_sigmae_1e-35.txt
cp ../results/fig22_DPLM_mchi_100keV_sigmae_1e-35_avg/Differential_SRDM_Flux.txt ../fig22_validation/srdm_dphidv_DPLM_fig22_mchi_100keV_sigmae_1e-35.txt
cp ../results/fig22_DPLM_mchi_1MeV_sigmae_1e-35_avg/Differential_SRDM_Flux.txt ../fig22_validation/srdm_dphidv_DPLM_fig22_mchi_1MeV_sigmae_1e-35.txt
```

## Metadata Template

DaMaSCUS-SUN commit inspected:

- `fd6900fc1ae88d0888d4762befea0afcd0f3b14a`

Worktree note:

- The repo contains untracked local `bin/`, `results/`, `scripts/`, `.codex`,
  and log artifacts. The configs in this directory are new for this task.

Common metadata for all three flux files:

- flux family: `DPLM`
- mediator model: dark photon, `DM_interaction = "Dark photon"`
- form factor: `DM_form_factor = "Long-Range"`, i.e. `F_DM(q) = (alpha m_e / q)^2`
- dark photon mass: `0` internally for `Long-Range`
- sigma convention: `sigma_e_bar`, via `DM_cross_section_electron`
- sigma_e_bar: `1.0e-35 cm^2`
- solar in-medium effects: enabled, `use_medium_effects = true`
- long-range q cutoff: `zeta = 0.0`, so `qMin = 0`
- Monte Carlo target: `sample_size = 100000` accepted data points above threshold
- interpolation grid: `1000 x 1000`
- flux type: isotropic/angle-averaged speed flux at `1 AU`
- isoreflection setting: `isoreflection_rings = 1`
- output columns: `v [km/s]`, `dPhi/dv [cm^-2 s^-1 (km/s)^-1]`
- velocity binning: 300 linearly spaced export points from `0 km/s` to
  `1.05 * max(sampled outgoing speed)` for each run
- random seeds: not fixed or recorded by the current config interface; each MPI
  worker seeds `std::mt19937` from `std::random_device`

Per-file metadata:

| output file | config | m_chi | DMeRates manifest mass | sigma_e_bar | approximate derived sigma_p_bar |
| --- | --- | --- | --- | --- | --- |
| `srdm_dphidv_DPLM_fig22_mchi_10keV_sigmae_1e-35.txt` | `config_fig22_DPLM_mchi_10keV_sigmae_1e-35.cfg` | `10 keV = 0.01 MeV = 1.0e4 eV` | `10000.0` | `1.0e-35 cm^2` | `1.04e-35 cm^2` |
| `srdm_dphidv_DPLM_fig22_mchi_100keV_sigmae_1e-35.txt` | `config_fig22_DPLM_mchi_100keV_sigmae_1e-35.cfg` | `100 keV = 0.1 MeV = 1.0e5 eV` | `100000.0` | `1.0e-35 cm^2` | `1.43e-35 cm^2` |
| `srdm_dphidv_DPLM_fig22_mchi_1MeV_sigmae_1e-35.txt` | `config_fig22_DPLM_mchi_1MeV_sigmae_1e-35.cfg` | `1 MeV = 1.0e6 eV` | `1000000.0` | `1.0e-35 cm^2` | `8.71e-35 cm^2` |

The approximate derived proton cross sections above are not input parameters;
they are what the dark-photon class would report after setting the electron
reference cross section.

## DMeRates Registration Notes

Use dedicated validation manifest entries, separate from the public low-stat
archive. Suggested internal keys:

```yaml
- family: DPLM
  m_chi_eV: 10000.0
  sigma_e_cm2: 1.0e-35
  path: fig22_validation/srdm_dphidv_DPLM_fig22_mchi_10keV_sigmae_1e-35.txt
  columns: [v_km_s, dPhi_dv_cm2_s_km_s]
  source: DaMaSCUS-SUN fig22 validation rerun

- family: DPLM
  m_chi_eV: 100000.0
  sigma_e_cm2: 1.0e-35
  path: fig22_validation/srdm_dphidv_DPLM_fig22_mchi_100keV_sigmae_1e-35.txt
  columns: [v_km_s, dPhi_dv_cm2_s_km_s]
  source: DaMaSCUS-SUN fig22 validation rerun

- family: DPLM
  m_chi_eV: 1000000.0
  sigma_e_cm2: 1.0e-35
  path: fig22_validation/srdm_dphidv_DPLM_fig22_mchi_1MeV_sigmae_1e-35.txt
  columns: [v_km_s, dPhi_dv_cm2_s_km_s]
  source: DaMaSCUS-SUN fig22 validation rerun
```

DMeRates should load velocity in km/s and raw `dPhi/dv` in
`cm^-2 s^-1 (km/s)^-1`, then convert to `dPhi/d(v/c)` internally.

## Limitations

- The current DaMaSCUS-SUN parameter-point mode cannot choose output filenames;
  it always writes `Differential_SRDM_Flux.txt` under `results/<ID>/`.
- The current config format cannot fix or record random seeds. Reproducible
  seeds would require a small source change to pass a config seed into
  `Simulation_Data::Generate_Data(..., fixed_seed)`.
- The actual number of simulated trajectories is not `sample_size`; it is
  printed in the run log and is normally larger. `sample_size` is the stopping
  target for accepted data points.
- DaMaSCUS-SUN produces the SRDM flux. Fig. 22 itself is a downstream silicon
  electron-recoil spectrum/form-factor comparison, so DMeRates still needs to
  apply the intended silicon response/form factor settings.
