#!/usr/bin/env python3
"""Shared helpers for the DaMaSCUS-SUN SRDM source production grid."""

from __future__ import annotations

import csv
import json
import math
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from convert_srdm_flux_to_eta import (
    KM_IN_CM,
    MEV_TO_GEV,
    cumulative_trapezoid_from_right,
    read_two_column_table,
    trapezoid_integral,
    write_two_column_table,
)


GRID_NAME = "srdm_fdmq2_source_v1"
DEFAULT_RESULTS_ROOT = Path("results/srdm_fdmq2_source_grid_v1")
DEFAULT_TEMPLATE = Path("scripts/templates/config_srdm_fdmq2_source.cfg")
DEFAULT_SAMPLE_SIZE = 100_000
DEFAULT_INTERPOLATION_POINTS = 1_000
DEFAULT_RHO_REF_GEV_CM3 = 0.3
MASS_MIN_MEV = 1.0e-2
MASS_MAX_MEV = 3.0
N_MASSES = 25
SIGMA_MIN_CM2 = 1.0e-42
SIGMA_MAX_CM2 = 1.0e-33
N_SIGMAS = 19
FDM_N = 2


@dataclass(frozen=True)
class GridPoint:
    index: int
    mass_mev: float
    sigma_e_cm2: float

    @property
    def point_tag(self) -> str:
        return f"mDM_{sci_tag(self.mass_mev)}_MeV_sigmaE_{sci_tag(self.sigma_e_cm2)}_cm2"

    @property
    def run_id(self) -> str:
        return f"srdm_fdmq2_source_{self.point_tag}"

    @property
    def is_boundary(self) -> bool:
        mass_i, sigma_i = divmod(self.index, N_SIGMAS)
        return mass_i in (0, N_MASSES - 1) or sigma_i in (0, N_SIGMAS - 1)

    @property
    def is_corner(self) -> bool:
        mass_i, sigma_i = divmod(self.index, N_SIGMAS)
        return mass_i in (0, N_MASSES - 1) and sigma_i in (0, N_SIGMAS - 1)


def logspace(start: float, stop: float, count: int) -> list[float]:
    if count < 2:
        raise ValueError("count must be at least 2")
    log_start = math.log10(start)
    log_stop = math.log10(stop)
    step = (log_stop - log_start) / (count - 1)
    values = [10.0 ** (log_start + i * step) for i in range(count)]
    values[0] = start
    values[-1] = stop
    return values


def masses_mev() -> list[float]:
    return logspace(MASS_MIN_MEV, MASS_MAX_MEV, N_MASSES)


def sigma_es_cm2() -> list[float]:
    return logspace(SIGMA_MIN_CM2, SIGMA_MAX_CM2, N_SIGMAS)


def iter_grid() -> Iterable[GridPoint]:
    index = 0
    for mass_mev in masses_mev():
        for sigma_e_cm2 in sigma_es_cm2():
            yield GridPoint(index=index, mass_mev=mass_mev, sigma_e_cm2=sigma_e_cm2)
            index += 1


def all_points() -> list[GridPoint]:
    return list(iter_grid())


def pilot_indices(include_high_high: bool = True) -> list[int]:
    indices = [0, N_SIGMAS - 1, (N_MASSES - 1) * N_SIGMAS]
    if include_high_high:
        indices.append(N_MASSES * N_SIGMAS - 1)
    return indices


def point_by_index(index: int) -> GridPoint:
    points = all_points()
    if index < 0 or index >= len(points):
        raise IndexError(f"Grid index {index} is outside [0, {len(points) - 1}]")
    return points[index]


def sci_tag(value: float) -> str:
    return f"{value:.8e}".replace("+", "").replace(".", "p")


def cfg_float_literal(value: float) -> str:
    text = f"{value:.12g}"
    if "e" not in text and "E" not in text and "." not in text:
        text += ".0"
    return text


def repo_root_from_script() -> Path:
    return Path(__file__).resolve().parents[1]


def git_commit(repo_root: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=repo_root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return result.stdout.strip() or None


def render_config(
    template_path: Path,
    output_path: Path,
    point: GridPoint,
    sample_size: int,
    interpolation_points: int,
) -> None:
    text = template_path.read_text(encoding="utf-8")
    replacements = {
        "__ID__": point.run_id,
        "__SAMPLE_SIZE__": str(sample_size),
        "__INTERPOLATION_POINTS__": str(interpolation_points),
        "__DM_MASS_MEV__": cfg_float_literal(point.mass_mev),
        "__SIGMA_E_CM2__": cfg_float_literal(point.sigma_e_cm2),
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    missing = [key for key in replacements if key in text]
    if missing:
        raise ValueError(f"Unreplaced template markers remain: {missing}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(text, encoding="utf-8")


def scan_root(repo_root: Path, results_root: Path) -> Path:
    return results_root if results_root.is_absolute() else repo_root / results_root


def generated_configs_dir(root: Path) -> Path:
    return root / "generated_configs"


def points_dir(root: Path) -> Path:
    return root / "points"


def point_export_dir(root: Path, point: GridPoint) -> Path:
    return points_dir(root) / point.point_tag


def manifest_entries(repo_root: Path, results_root: Path) -> list[dict]:
    root = scan_root(repo_root, results_root).resolve()
    entries = []
    for point in all_points():
        export_dir = point_export_dir(root, point)
        config_path = generated_configs_dir(root) / f"{point.run_id}.cfg"
        entries.append(
            {
                "grid_name": GRID_NAME,
                "index": point.index,
                "mDM_MeV": point.mass_mev,
                "sigma_e_cm2": point.sigma_e_cm2,
                "FDMn": FDM_N,
                "point_tag": point.point_tag,
                "run_id": point.run_id,
                "is_boundary": point.is_boundary,
                "is_corner": point.is_corner,
                "config_file": str(config_path.resolve()),
                "point_export_dir": str(export_dir.resolve()),
                "source_flux_file": str((export_dir / "Differential_SRDM_Flux.txt").resolve()),
                "metadata_file": str((export_dir / "metadata.json").resolve()),
            }
        )
    return entries


def write_manifest(repo_root: Path, results_root: Path) -> None:
    root = scan_root(repo_root, results_root)
    root.mkdir(parents=True, exist_ok=True)
    entries = manifest_entries(repo_root, results_root)
    (root / "scan_manifest.json").write_text(
        json.dumps(entries, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    with (root / "scan_manifest.tsv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "index",
                "mDM_MeV",
                "sigma_e_cm2",
                "FDMn",
                "point_tag",
                "run_id",
                "is_boundary",
                "is_corner",
                "config_file",
                "point_export_dir",
                "source_flux_file",
                "metadata_file",
            ],
            delimiter="\t",
            extrasaction="ignore",
        )
        writer.writeheader()
        writer.writerows(entries)


def prepare_configs(
    repo_root: Path,
    results_root: Path,
    template_path: Path,
    sample_size: int,
    interpolation_points: int,
) -> None:
    root = scan_root(repo_root, results_root)
    for point in all_points():
        render_config(
            template_path,
            generated_configs_dir(root) / f"{point.run_id}.cfg",
            point,
            sample_size,
            interpolation_points,
        )
    write_manifest(repo_root, results_root)


def _positive_flux_rows(flux_path: Path) -> tuple[list[float], list[float], int]:
    speeds, fluxes = read_two_column_table(flux_path)
    if any(not math.isfinite(v) for v in speeds) or any(not math.isfinite(f) for f in fluxes):
        raise ValueError("Flux table contains non-finite values")
    if any(v < 0.0 for v in speeds):
        raise ValueError("Flux table contains negative speeds")
    if any(f < 0.0 for f in fluxes):
        raise ValueError("Flux table contains negative flux values")
    dropped = sum(1 for v in speeds if v <= 0.0)
    positive = [(v, f) for v, f in zip(speeds, fluxes) if v > 0.0]
    if len(positive) < 2:
        raise ValueError("Flux table needs at least two positive speed rows")
    p_speeds = [v for v, _ in positive]
    p_fluxes = [f for _, f in positive]
    if any(b <= a for a, b in zip(p_speeds, p_speeds[1:])):
        raise ValueError("Positive speed grid must be strictly increasing")
    if sum(p_fluxes) <= 0.0:
        raise ValueError("Flux table is all zero after positive-speed filtering")
    return p_speeds, p_fluxes, dropped


def source_flux_summary(flux_path: Path, mass_mev: float) -> dict:
    speeds, fluxes, dropped = _positive_flux_rows(flux_path)
    total_flux = trapezoid_integral(speeds, fluxes)
    n_eff_cm3 = trapezoid_integral(speeds, [f / v for v, f in zip(speeds, fluxes)]) / KM_IN_CM
    if total_flux <= 0.0:
        raise ValueError("Integrated source flux is non-positive")
    if n_eff_cm3 <= 0.0:
        raise ValueError("Effective source number density is non-positive")
    return {
        "speed_rows": len(speeds),
        "dropped_nonpositive_speed_rows": dropped,
        "v_grid_min_km_s": speeds[0],
        "v_grid_max_km_s": speeds[-1],
        "total_flux_cm^-2_s^-1": total_flux,
        "n_eff_cm^-3": n_eff_cm3,
        "rho_eff_GeV_cm^-3": n_eff_cm3 * mass_mev * MEV_TO_GEV,
        "minimum_supported_vmin_km_s": speeds[0],
    }


def write_reference_eta_diagnostic(
    flux_path: Path,
    output_path: Path,
    mass_mev: float,
    rho_ref_gev_cm3: float,
) -> dict:
    speeds, fluxes, _ = _positive_flux_rows(flux_path)
    n_ref_cm3 = rho_ref_gev_cm3 / (mass_mev * MEV_TO_GEV)
    terminal_step = max(speeds[-1] - speeds[-2], 1.0)
    work_speeds = [*speeds, speeds[-1] + terminal_step]
    work_fluxes = [*fluxes, 0.0]
    integrand = [
        flux / (KM_IN_CM * n_ref_cm3 * speed * speed)
        for speed, flux in zip(work_speeds, work_fluxes)
    ]
    etas = cumulative_trapezoid_from_right(work_speeds, integrand)
    if work_speeds[0] > 0.0:
        work_speeds = [0.0, *work_speeds]
        etas = [etas[0], *etas]
    write_two_column_table(output_path, work_speeds, etas)
    return {
        "eta_file": str(output_path.resolve()),
        "eta_definition": "reference-normalized int_vmin^inf dPhi/dv / (1e5*n_ref*v^2) dv",
        "rho_ref_GeV_cm^-3": rho_ref_gev_cm3,
        "n_ref_cm^-3": n_ref_cm3,
    }


def write_point_metadata(
    metadata_path: Path,
    repo_root: Path,
    point: GridPoint,
    sample_size: int,
    interpolation_points: int,
    config_path: Path,
    run_results_dir: Path,
    export_dir: Path,
    runtime_seconds: float | None,
    source_summary: dict,
    eta_summary: dict,
    status: str,
) -> None:
    payload = {
        "schema": "damascus_sun_srdm_source_grid_v1",
        "grid_name": GRID_NAME,
        "status": status,
        "git_commit": git_commit(repo_root),
        "source_type": "SRDM",
        "source_flux_contract": {
            "filename": "Differential_SRDM_Flux.txt",
            "columns": ["v_km_s", "dPhi_dv_cm^-2_s^-1_(km/s)^-1"],
            "primary_downstream_consumers": ["Verne SRDMBeam", "DaMaSCUS SRDMBeam"],
        },
        "angle_averaged": True,
        "isoreflection_rings": 1,
        "mDM_MeV": point.mass_mev,
        "sigma_e_cm2": point.sigma_e_cm2,
        "FDMn": FDM_N,
        "form_factor_label": "FDMq2",
        "sample_size": sample_size,
        "interpolation_points": interpolation_points,
        "scan_point_index": point.index,
        "point_tag": point.point_tag,
        "run_id": point.run_id,
        "is_boundary": point.is_boundary,
        "is_corner": point.is_corner,
        "config_file": str(config_path.resolve()),
        "run_results_dir": str(run_results_dir.resolve()),
        "scan_export_dir": str(export_dir.resolve()),
        "source_flux_file": str((export_dir / "Differential_SRDM_Flux.txt").resolve()),
        "source_energy_spectrum_file": str((export_dir / "Differential_Energy_Spectrum.txt").resolve()),
        "runtime_seconds": runtime_seconds,
        "source_summary": source_summary,
        "eta_diagnostic": eta_summary,
    }
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def run_grid_point(
    repo_root: Path,
    results_root: Path,
    template_path: Path,
    point: GridPoint,
    sample_size: int,
    interpolation_points: int,
    mpi_ranks: int,
    launcher: str,
    rho_ref_gev_cm3: float,
    resume: bool,
    overwrite: bool,
    postprocess_only: bool = False,
) -> dict:
    root = scan_root(repo_root, results_root)
    config_path = generated_configs_dir(root) / f"{point.run_id}.cfg"
    export_dir = point_export_dir(root, point)
    metadata_path = export_dir / "metadata.json"
    final_flux_path = export_dir / "Differential_SRDM_Flux.txt"
    if resume and metadata_path.exists() and final_flux_path.exists() and not overwrite:
        return {"status": "skipped", "reason": "existing complete point", "index": point.index}

    render_config(template_path, config_path, point, sample_size, interpolation_points)
    write_manifest(repo_root, results_root)

    bin_dir = repo_root / "bin"
    executable = bin_dir / "DaMaSCUS-SUN"
    run_results_dir = repo_root / "results" / point.run_id
    start = time.monotonic()
    if not postprocess_only:
        subprocess.run(
            [launcher, "-n", str(mpi_ranks), str(executable), str(config_path.resolve())],
            cwd=bin_dir,
            check=True,
        )
    runtime = time.monotonic() - start if not postprocess_only else None

    source_flux = run_results_dir / "Differential_SRDM_Flux.txt"
    source_energy = run_results_dir / "Differential_Energy_Spectrum.txt"
    if not source_flux.exists():
        raise FileNotFoundError(f"Expected source flux is missing: {source_flux}")

    export_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(config_path, export_dir / "run_config.cfg")
    shutil.copy2(source_flux, final_flux_path)
    if source_energy.exists():
        shutil.copy2(source_energy, export_dir / "Differential_Energy_Spectrum.txt")

    summary = source_flux_summary(final_flux_path, point.mass_mev)
    eta_summary = write_reference_eta_diagnostic(
        final_flux_path,
        export_dir / "diagnostic_eta_rhoRef0.3.txt",
        point.mass_mev,
        rho_ref_gev_cm3,
    )
    write_point_metadata(
        metadata_path,
        repo_root,
        point,
        sample_size,
        interpolation_points,
        export_dir / "run_config.cfg",
        run_results_dir,
        export_dir,
        runtime,
        summary,
        eta_summary,
        "complete",
    )
    return {"status": "complete", "index": point.index, "metadata_file": str(metadata_path)}


def load_point_metadata(export_dir: Path) -> dict | None:
    path = export_dir / "metadata.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def qa_rows(repo_root: Path, results_root: Path, recommend_boundary: bool = False) -> list[dict]:
    root = scan_root(repo_root, results_root)
    rows = []
    flux_by_index: dict[int, float] = {}
    for point in all_points():
        export_dir = point_export_dir(root, point)
        metadata = load_point_metadata(export_dir)
        flux_path = export_dir / "Differential_SRDM_Flux.txt"
        row = {
            "index": point.index,
            "mDM_MeV": point.mass_mev,
            "sigma_e_cm2": point.sigma_e_cm2,
            "point_tag": point.point_tag,
            "status": "missing",
            "is_boundary": point.is_boundary,
            "is_corner": point.is_corner,
            "pass2_recommended": False,
            "issues": [],
        }
        if metadata is None:
            row["issues"].append("missing metadata.json")
        if not flux_path.exists():
            row["issues"].append("missing Differential_SRDM_Flux.txt")
        if flux_path.exists():
            try:
                summary = source_flux_summary(flux_path, point.mass_mev)
                row.update(summary)
                flux_by_index[point.index] = summary["total_flux_cm^-2_s^-1"]
            except ValueError as exc:
                row["issues"].append(str(exc))
        if row["issues"]:
            row["status"] = "invalid"
            row["pass2_recommended"] = True
        else:
            row["status"] = "complete"
            if point.is_corner or (recommend_boundary and point.is_boundary):
                row["pass2_recommended"] = True
        rows.append(row)

    for row in rows:
        if row["status"] != "complete" or row["index"] not in flux_by_index:
            continue
        point = point_by_index(row["index"])
        mass_i, sigma_i = divmod(point.index, N_SIGMAS)
        neighbor_indices = []
        for dm, ds in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            mi = mass_i + dm
            si = sigma_i + ds
            if 0 <= mi < N_MASSES and 0 <= si < N_SIGMAS:
                idx = mi * N_SIGMAS + si
                if idx in flux_by_index and flux_by_index[idx] > 0.0:
                    neighbor_indices.append(idx)
        if len(neighbor_indices) >= 2 and flux_by_index[point.index] > 0.0:
            log_self = math.log10(flux_by_index[point.index])
            log_neighbors = sorted(math.log10(flux_by_index[idx]) for idx in neighbor_indices)
            median = log_neighbors[len(log_neighbors) // 2]
            residual = abs(log_self - median)
            row["neighbor_log10_flux_residual"] = residual
            if residual > 1.0:
                row["issues"].append(f"log10 flux differs from neighbor median by {residual:.3g} dex")
                row["pass2_recommended"] = True
    return rows


def write_qa_report(repo_root: Path, results_root: Path, recommend_boundary: bool = False) -> dict:
    root = scan_root(repo_root, results_root)
    rows = qa_rows(repo_root, results_root, recommend_boundary=recommend_boundary)
    summary = {
        "grid_name": GRID_NAME,
        "total_points": len(rows),
        "complete_points": sum(1 for row in rows if row["status"] == "complete"),
        "invalid_points": sum(1 for row in rows if row["status"] == "invalid"),
        "pass2_recommended_points": [row["index"] for row in rows if row["pass2_recommended"]],
    }
    report = {"summary": summary, "rows": rows}
    root.mkdir(parents=True, exist_ok=True)
    (root / "qa_report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    with (root / "qa_report.tsv").open("w", encoding="utf-8", newline="") as handle:
        fieldnames = [
            "index",
            "mDM_MeV",
            "sigma_e_cm2",
            "status",
            "is_boundary",
            "is_corner",
            "pass2_recommended",
            "total_flux_cm^-2_s^-1",
            "n_eff_cm^-3",
            "rho_eff_GeV_cm^-3",
            "neighbor_log10_flux_residual",
            "issues",
        ]
        writer = csv.DictWriter(handle, fieldnames=fieldnames, delimiter="\t", extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            out = dict(row)
            out["issues"] = "; ".join(row["issues"])
            writer.writerow(out)
    return report
