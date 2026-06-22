#!/usr/bin/env python3
r"""Prepare and optionally run an angle-averaged SRDM source-side FDMq2 grid.

This script generates one DaMaSCUS-SUN parameter-point config per (mX, sigma_e)
point, optionally runs the executable, and converts each resulting
`Differential_SRDM_Flux.txt` into a rho-folded `eta(vmin)` table suitable for
downstream Earth-scattering / daily-modulation studies.

The scan is intentionally angle-averaged (`isoreflection_rings = 1`), since the
current downstream daily-modulation work treats the incoming SRDM as a solar beam
with a non-Maxwellian speed distribution and postpones annual anisotropy.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from convert_srdm_flux_to_eta import (
    MEV_TO_GEV,
    choose_vcut,
    compute_eta_table,
    read_two_column_table,
    sort_and_deduplicate,
    write_metadata,
    write_two_column_table,
)


MASSES_MEV = [
    0.01,
    0.0139866,
    0.0195626,
    0.0273614,
    0.0382694,
    0.053526,
    0.0748649,
    0.104711,
    0.146455,
    0.204841,
    0.286504,
    0.400722,
    0.560475,
    0.783915,
    1.09643,
    1.53354,
    2.14491,
    3.0,
]

SIGMA_ES_CM2 = [
    6.0e-36,
    9.18978e-36,
    1.40754e-35,
    2.15582e-35,
    3.30193e-35,
    5.05733e-35,
    7.74597e-35,
    1.18640e-34,
    1.81712e-34,
    2.78316e-34,
    4.26277e-34,
    6.52899e-34,
    1.0e-33,
]


@dataclass(frozen=True)
class GridPoint:
    index: int
    mass_mev: float
    sigma_e_cm2: float


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--sample-size",
        type=int,
        default=100000,
        help="DaMaSCUS-SUN sample_size per angle-averaged point. Default: 100000",
    )
    parser.add_argument(
        "--interpolation-points",
        type=int,
        default=1000,
        help="DaMaSCUS-SUN interpolation_points setting. Default: 1000",
    )
    parser.add_argument(
        "--rho-ref-gev-cm3",
        type=float,
        default=0.3,
        help="Reference density folded into eta(vmin). Default: 0.3",
    )
    parser.add_argument(
        "--mpirun-n",
        type=int,
        default=4,
        help="MPI worker count for each DaMaSCUS-SUN run. Default: 4",
    )
    parser.add_argument(
        "--offset",
        type=int,
        default=0,
        help="Skip the first N grid points in row-major order. Default: 0",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Run at most this many points after offset. Default: all",
    )
    parser.add_argument(
        "--prepare-only",
        action="store_true",
        help="Only generate configs and the scan manifest. Do not run DaMaSCUS-SUN.",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Skip points whose final eta file already exists in the scan export tree.",
    )
    parser.add_argument(
        "--results-root",
        type=Path,
        default=Path("results/srdm_fdmq2_rectangular_grid"),
        help="Top-level scan export directory. Default: results/srdm_fdmq2_rectangular_grid",
    )
    return parser.parse_args()


def sci_tag(value: float) -> str:
    return f"{value:.8e}".replace("+", "").replace(".", "p")


def cfg_float_literal(value: float) -> str:
    """Format a float for libconfig while preserving float type for whole numbers."""
    text = f"{value:.12g}"
    if "e" not in text and "E" not in text and "." not in text:
        text += ".0"
    return text


def point_tag(point: GridPoint) -> str:
    return f"mDM_{sci_tag(point.mass_mev)}_MeV_sigmaE_{sci_tag(point.sigma_e_cm2)}_cm2"


def run_id(point: GridPoint) -> str:
    return f"srdm_fdmq2_avg_{point_tag(point)}"


def iter_grid() -> Iterable[GridPoint]:
    index = 0
    for mass_mev in MASSES_MEV:
        for sigma_e_cm2 in SIGMA_ES_CM2:
            yield GridPoint(index=index, mass_mev=mass_mev, sigma_e_cm2=sigma_e_cm2)
            index += 1


def write_config_from_template(
    template_path: Path,
    output_path: Path,
    point: GridPoint,
    sample_size: int,
    interpolation_points: int,
) -> None:
    text = template_path.read_text(encoding="utf-8")
    replacements = {
        "__ID__": run_id(point),
        "__SAMPLE_SIZE__": str(sample_size),
        "__INTERPOLATION_POINTS__": str(interpolation_points),
        "__DM_MASS_MEV__": cfg_float_literal(point.mass_mev),
        "__SIGMA_E_CM2__": cfg_float_literal(point.sigma_e_cm2),
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(text, encoding="utf-8")


def convert_flux_to_eta(
    flux_path: Path,
    eta_path: Path,
    metadata_path: Path,
    mass_mev: float,
    rho_ref_gev_cm3: float,
) -> dict:
    speeds, fluxes = read_two_column_table(flux_path)
    speeds, fluxes = sort_and_deduplicate(speeds, fluxes)
    vcut = choose_vcut(speeds, None)
    eta_vmins, etas, flux_total, n_eff_cm3 = compute_eta_table(speeds, fluxes, vcut)
    rho_eff_gev_cm3 = n_eff_cm3 * mass_mev * MEV_TO_GEV
    rho_fold_scale = rho_eff_gev_cm3 / rho_ref_gev_cm3
    etas = [eta * rho_fold_scale for eta in etas]

    write_two_column_table(eta_path, eta_vmins, etas)
    write_metadata(
        metadata_path,
        flux_path.resolve(),
        eta_path.resolve(),
        mass_mev,
        vcut,
        flux_total,
        n_eff_cm3,
        True,
        rho_ref_gev_cm3,
        rho_fold_scale,
    )
    return {
        "vcut_km_per_s": vcut,
        "total_flux_cm^-2_s^-1": flux_total,
        "n_eff_cm^-3": n_eff_cm3,
        "rho_eff_GeV_cm^-3": rho_eff_gev_cm3,
        "rho_fold_scale": rho_fold_scale,
    }


def write_point_metadata_json(
    path: Path,
    point: GridPoint,
    point_dir: Path,
    run_results_dir: Path,
    config_path: Path,
    flux_path: Path,
    eta_path: Path,
    eta_metadata_path: Path,
    sample_size: int,
    interpolation_points: int,
    rho_ref_gev_cm3: float,
    conversion_summary: dict,
) -> None:
    payload = {
        "source_type": "SRDM",
        "angle_averaged": True,
        "isoreflection_rings": 1,
        "mX_MeV": point.mass_mev,
        "sigma_e_cm2": point.sigma_e_cm2,
        "FDMn": 2,
        "form_factor_label": "FDMq2",
        "rho_ref_GeV_cm3": rho_ref_gev_cm3,
        "sample_size": sample_size,
        "interpolation_points": interpolation_points,
        "halo_convention": {
            "DM_local_density_GeV_cm3": 0.3,
            "SHM_v0_km_s": 238.0,
            "SHM_vObserver_km_s": [11.1, 245.2, 7.3],
            "SHM_vEscape_km_s": 544.0,
            "note": "Sun-frame observer velocity using 233 km/s LSR + solar peculiar velocity.",
        },
        "scan_point_index": point.index,
        "point_tag": point_tag(point),
        "run_id": run_id(point),
        "scan_export_dir": str(point_dir.resolve()),
        "run_results_dir": str(run_results_dir.resolve()),
        "config_file": str(config_path.resolve()),
        "flux_file": str(flux_path.resolve()),
        "eta_file": str(eta_path.resolve()),
        "eta_metadata_text_file": str(eta_metadata_path.resolve()),
        "conversion_summary": conversion_summary,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_scan_manifest(scan_root: Path, entries: list[dict]) -> None:
    manifest_json = scan_root / "scan_manifest.json"
    manifest_tsv = scan_root / "scan_manifest.tsv"
    scan_root.mkdir(parents=True, exist_ok=True)
    manifest_json.write_text(json.dumps(entries, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    with manifest_tsv.open("w", encoding="utf-8") as handle:
        handle.write(
            "\t".join(
                [
                    "index",
                    "mX_MeV",
                    "sigma_e_cm2",
                    "point_tag",
                    "run_id",
                    "config_file",
                    "point_export_dir",
                ]
            )
            + "\n"
        )
        for entry in entries:
            handle.write(
                "\t".join(
                    [
                        str(entry["index"]),
                        f'{entry["mX_MeV"]:.12g}',
                        f'{entry["sigma_e_cm2"]:.12g}',
                        entry["point_tag"],
                        entry["run_id"],
                        entry["config_file"],
                        entry["point_export_dir"],
                    ]
                )
                + "\n"
            )


def main() -> int:
    args = parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    bin_dir = repo_root / "bin"
    executable = bin_dir / "DaMaSCUS-SUN"
    template_path = bin_dir / "config_srdm_fdmq2_scan_template.cfg"
    scan_root = (repo_root / args.results_root).resolve()
    generated_configs_dir = scan_root / "generated_configs"
    points_export_dir = scan_root / "points"
    top_level_results_dir = repo_root / "results"

    all_points = list(iter_grid())
    selected_points = all_points[args.offset :]
    if args.limit is not None:
        selected_points = selected_points[: args.limit]

    manifest_entries = []
    for point in all_points:
        point_export_dir = points_export_dir / point_tag(point)
        config_path = generated_configs_dir / f"{run_id(point)}.cfg"
        manifest_entries.append(
            {
                "index": point.index,
                "mX_MeV": point.mass_mev,
                "sigma_e_cm2": point.sigma_e_cm2,
                "point_tag": point_tag(point),
                "run_id": run_id(point),
                "config_file": str(config_path.resolve()),
                "point_export_dir": str(point_export_dir.resolve()),
            }
        )
    write_scan_manifest(scan_root, manifest_entries)

    for point in selected_points:
        point_export_dir = points_export_dir / point_tag(point)
        config_path = generated_configs_dir / f"{run_id(point)}.cfg"
        eta_path = point_export_dir / "srdm_avg_eta_rhoRef0.3.txt"
        eta_metadata_text_path = point_export_dir / "srdm_avg_eta_rhoRef0.3_metadata.txt"
        eta_metadata_json_path = point_export_dir / "srdm_avg_eta_rhoRef0.3_metadata.json"
        flux_copy_path = point_export_dir / "srdm_avg_flux.txt"
        energy_copy_path = point_export_dir / "srdm_avg_dRdE.txt"
        config_copy_path = point_export_dir / "run_config.cfg"
        run_results_dir = top_level_results_dir / run_id(point)
        source_flux_path = run_results_dir / "Differential_SRDM_Flux.txt"
        source_energy_path = run_results_dir / "Differential_Energy_Spectrum.txt"

        write_config_from_template(
            template_path,
            config_path,
            point,
            args.sample_size,
            args.interpolation_points,
        )

        if args.prepare_only:
            continue

        if args.resume and eta_path.exists() and eta_metadata_json_path.exists():
            print(f"[resume] Skip existing point {point.index}: {point_tag(point)}")
            continue

        print(
            f"[run] index={point.index} mX={point.mass_mev:.12g} MeV "
            f"sigma_e={point.sigma_e_cm2:.12g} cm^2"
        )
        subprocess.run(
            ["mpirun", "-n", str(args.mpirun_n), str(executable), str(config_path.resolve())],
            cwd=bin_dir,
            check=True,
        )

        if not source_flux_path.exists():
            raise FileNotFoundError(f"Expected flux file missing after run: {source_flux_path}")

        point_export_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(config_path, config_copy_path)
        shutil.copy2(source_flux_path, flux_copy_path)
        if source_energy_path.exists():
            shutil.copy2(source_energy_path, energy_copy_path)

        conversion_summary = convert_flux_to_eta(
            flux_copy_path,
            eta_path,
            eta_metadata_text_path,
            point.mass_mev,
            args.rho_ref_gev_cm3,
        )
        write_point_metadata_json(
            eta_metadata_json_path,
            point,
            point_export_dir,
            run_results_dir,
            config_copy_path,
            flux_copy_path,
            eta_path,
            eta_metadata_text_path,
            args.sample_size,
            args.interpolation_points,
            args.rho_ref_gev_cm3,
            conversion_summary,
        )

    mode = "prepared" if args.prepare_only else "completed"
    print(f"{mode} scan entries under {scan_root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
