#!/usr/bin/env python3
"""Run pilot SRDM source points through downstream validation hooks."""

from __future__ import annotations

import argparse
import json
import math
import subprocess
from pathlib import Path

import srdm_source_grid as grid


ME_E_EV = 5.1099894e5
MP_E_EV = 938.27208816e6


def sigma_e_to_sigma_p(sigma_e_cm2: float, mass_mev: float) -> float:
    mass_ev = mass_mev * 1.0e6
    mu_e = mass_ev * ME_E_EV / (mass_ev + ME_E_EV)
    mu_p = mass_ev * MP_E_EV / (mass_ev + MP_E_EV)
    return sigma_e_cm2 * (mu_p / mu_e) ** 2


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-root", type=Path, default=grid.DEFAULT_RESULTS_ROOT)
    parser.add_argument("--indices", nargs="*", type=int, default=None)
    parser.add_argument("--verne-root", type=Path, default=None)
    parser.add_argument("--verne-num-angles", type=int, default=6)
    parser.add_argument("--verne-depth-m", type=float, default=104.0)
    parser.add_argument("--verne-target", choices=["atmos", "earth", "full"], default="full")
    parser.add_argument("--damascus-root", type=Path, default=None)
    parser.add_argument("--run-damascus", action="store_true")
    parser.add_argument("--damascus-ranks", type=int, default=2)
    parser.add_argument("--damascus-initialruns", type=int, default=2000)
    parser.add_argument("--damascus-samplesize", type=int, default=2)
    parser.add_argument("--site-label", default="SENSEI")
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def write_damascus_config(
    path: Path,
    point: grid.GridPoint,
    flux_path: Path,
    initialruns: int,
    samplesize: int,
) -> None:
    sigma_p = sigma_e_to_sigma_p(point.sigma_e_cm2, point.mass_mev)
    text = f"""// Auto-generated SRDMBeam smoke config for DaMaSCUS pipeline validation.
simID          = "pilot_srdmbeam_{point.point_tag}";
initialruns    = {initialruns}L;
samplesize     = {samplesize};
vcutoff        = 1.0;
rings          = 4;

date           = [16,03,2016];
time           = [0,0,0];

mass           = {grid.cfg_float_literal(point.mass_mev)};
sigma          = {sigma_p:.12e};
formfactor     = "LightMediator";

halomodel      = "SRDMBeam";
srdm_flux_file = "{flux_path.resolve()}";
rho            = 0.3;

depth          = 104.0;
experiment     = "SENSEI";
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def validate_one(args: argparse.Namespace, repo_root: Path, point: grid.GridPoint) -> dict:
    root = grid.scan_root(repo_root, args.results_root)
    export_dir = grid.point_export_dir(root, point)
    flux_path = export_dir / "Differential_SRDM_Flux.txt"
    row = {
        "index": point.index,
        "point_tag": point.point_tag,
        "mDM_MeV": point.mass_mev,
        "sigma_e_cm2": point.sigma_e_cm2,
        "checks": {},
        "issues": [],
    }

    try:
        row["checks"]["source_flux"] = grid.source_flux_summary(flux_path, point.mass_mev)
    except (OSError, ValueError) as exc:
        row["issues"].append(f"source flux validation failed: {exc}")
        return row

    if args.verne_root is not None:
        verne_root = args.verne_root.resolve()
        outdir = root / "pilot_pipeline" / "verne"
        cmd = [
            "python3",
            str(verne_root / "src" / "CalcEtaDist_srdm.py"),
            "-m_x",
            f"{point.mass_mev:.12g}",
            "-sigma_e",
            f"{point.sigma_e_cm2:.12g}",
            "-flux",
            str(flux_path.resolve()),
            "-int",
            "ulm",
            "-loc",
            args.verne_target,
            "-d",
            f"{args.verne_depth_m:.12g}",
            "-n",
            str(args.verne_num_angles),
            "-out",
            str(outdir.resolve()),
            "--site_label",
            args.site_label,
            "--write_diagnostics",
        ]
        if args.overwrite:
            cmd.append("--overwrite")
        try:
            subprocess.run(cmd, cwd=verne_root / "src", check=True)
            row["checks"]["verne"] = {"status": "complete", "outdir": str(outdir.resolve())}
        except (OSError, subprocess.CalledProcessError) as exc:
            row["issues"].append(f"Verne SRDMBeam validation failed: {exc}")

    if args.damascus_root is not None:
        damascus_root = args.damascus_root.resolve()
        config_path = root / "pilot_pipeline" / "damascus_configs" / f"{point.run_id}.cfg"
        write_damascus_config(
            config_path,
            point,
            flux_path,
            args.damascus_initialruns,
            args.damascus_samplesize,
        )
        row["checks"]["damascus_config"] = {
            "status": "written",
            "config_file": str(config_path.resolve()),
            "sigma_p_cm2": sigma_e_to_sigma_p(point.sigma_e_cm2, point.mass_mev),
        }
        if args.run_damascus:
            cmd = [
                "mpirun",
                "-n",
                str(args.damascus_ranks),
                str(damascus_root / "bin" / "DaMaSCUS-Simulator"),
                str(config_path.resolve()),
            ]
            try:
                subprocess.run(cmd, cwd=damascus_root / "bin", check=True)
                row["checks"]["damascus_run"] = {"status": "complete"}
            except (OSError, subprocess.CalledProcessError) as exc:
                row["issues"].append(f"DaMaSCUS SRDMBeam smoke run failed: {exc}")

    summary = row["checks"].get("source_flux", {})
    if summary:
        total_flux = summary["total_flux_cm^-2_s^-1"]
        rho_eff = summary["rho_eff_GeV_cm^-3"]
        if not (math.isfinite(total_flux) and total_flux > 0.0):
            row["issues"].append("source total flux is not finite and positive")
        if not (math.isfinite(rho_eff) and rho_eff > 0.0):
            row["issues"].append("source rho_eff is not finite and positive")
    return row


def main() -> int:
    args = parse_args()
    repo_root = grid.repo_root_from_script()
    indices = args.indices if args.indices is not None else grid.pilot_indices()
    rows = [validate_one(args, repo_root, grid.point_by_index(index)) for index in indices]
    report = {
        "grid_name": grid.GRID_NAME,
        "indices": indices,
        "rows": rows,
        "passed": all(not row["issues"] for row in rows),
    }
    root = grid.scan_root(repo_root, args.results_root)
    report_path = root / "pilot_pipeline_report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"pipeline validation report: {report_path}")
    if not report["passed"]:
        for row in rows:
            for issue in row["issues"]:
                print(f"[index {row['index']}] {issue}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
