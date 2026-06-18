#!/usr/bin/env python3
r"""Convert DaMaSCUS-SUN differential flux output to DarkMatterRates eta(vmin).

Input format:
    v[km/s]    dPhi/dv[(km/s)^-1 cm^-2 s^-1]

Output format:
    vmin[km/s] eta(vmin)[s/km]

Notes
-----
- By default this script writes a normalized eta(vmin) file and stores the
  effective SRDM number density / mass density in a sidecar metadata file.
- If you pass ``--fold-rho-into-eta``, the script rescales the exported eta by
  ``rho_eff / rho_reference``. That mode is useful when a downstream code
  always multiplies by its own built-in density normalization and you prefer
  not to change that value.
- For a beam-like SRDM flux, the relevant conversion is

      eta(vmin) = [int_{vmin}^\infty dv (dPhi/dv) / v^2]
                  / [int_0^\infty dv (dPhi/dv) / v]

  where v is in km/s and the resulting eta is in s/km.
- If the input file contains an entry at v = 0, the integrals above would be
  singular. The current DaMaSCUS-SUN export can do that because its KDE domain
  starts at zero. By default, this script uses the first strictly positive
  speed in the file as the integration floor. This is conservative and avoids
  amplifying the v = 0 KDE artifact.
"""

from __future__ import annotations

import argparse
import bisect
import math
from pathlib import Path
from typing import Iterable, List, Sequence, Tuple


KM_IN_CM = 1.0e5
MEV_TO_GEV = 1.0e-3


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="Input DaMaSCUS-SUN flux file.")
    parser.add_argument(
        "output",
        type=Path,
        nargs="?",
        help="Output eta(vmin) file. Defaults to '<input stem>_eta.txt'.",
    )
    parser.add_argument(
        "--mass-mev",
        type=float,
        default=None,
        help="DM mass in MeV. If given, the metadata file will include rho_eff in GeV/cm^3.",
    )
    parser.add_argument(
        "--vcut-kms",
        type=float,
        default=None,
        help=(
            "Minimum speed used in the flux->eta integrals. "
            "Defaults to the first strictly positive speed in the file."
        ),
    )
    parser.add_argument(
        "--metadata",
        type=Path,
        default=None,
        help="Optional metadata output path. Defaults to '<output stem>_metadata.txt'.",
    )
    parser.add_argument(
        "--fold-rho-into-eta",
        action="store_true",
        help=(
            "Rescale the output eta(vmin) by rho_eff / rho_reference so a downstream "
            "code can keep using its usual density value."
        ),
    )
    parser.add_argument(
        "--reference-rho-gev-cm3",
        type=float,
        default=0.3,
        help=(
            "Reference density in GeV/cm^3 used when --fold-rho-into-eta is enabled. "
            "Default: 0.3"
        ),
    )
    return parser.parse_args()


def read_two_column_table(path: Path) -> Tuple[List[float], List[float]]:
    speeds: List[float] = []
    values: List[float] = []
    with path.open("r", encoding="utf-8") as handle:
        for lineno, raw_line in enumerate(handle, start=1):
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            if len(parts) < 2:
                raise ValueError(f"{path}:{lineno}: expected at least two columns")
            speed = float(parts[0])
            value = float(parts[1])
            speeds.append(speed)
            values.append(value)
    if not speeds:
        raise ValueError(f"{path}: no data rows found")
    if len(speeds) < 2:
        raise ValueError(f"{path}: need at least two data rows for integration")
    return speeds, values


def sort_and_deduplicate(x: Sequence[float], y: Sequence[float]) -> Tuple[List[float], List[float]]:
    rows = sorted(zip(x, y), key=lambda row: row[0])
    dedup_x: List[float] = []
    dedup_y: List[float] = []
    for x_i, y_i in rows:
        if dedup_x and math.isclose(x_i, dedup_x[-1], rel_tol=0.0, abs_tol=0.0):
            dedup_y[-1] = y_i
        else:
            dedup_x.append(x_i)
            dedup_y.append(y_i)
    return dedup_x, dedup_y


def linear_interpolate(x0: float, y0: float, x1: float, y1: float, x: float) -> float:
    if math.isclose(x1, x0):
        return y0
    return y0 + (y1 - y0) * (x - x0) / (x1 - x0)


def insert_point(x: Sequence[float], y: Sequence[float], x_new: float) -> Tuple[List[float], List[float]]:
    if x_new <= x[0]:
        return [x_new, *x], [y[0], *y]
    if x_new >= x[-1]:
        return [*x, x_new], [*y, y[-1]]
    idx = bisect.bisect_left(x, x_new)
    if idx < len(x) and math.isclose(x[idx], x_new):
        return list(x), list(y)
    y_new = linear_interpolate(x[idx - 1], y[idx - 1], x[idx], y[idx], x_new)
    return [*x[:idx], x_new, *x[idx:]], [*y[:idx], y_new, *y[idx:]]


def trapezoid_integral(x: Sequence[float], y: Sequence[float]) -> float:
    total = 0.0
    for i in range(len(x) - 1):
        dx = x[i + 1] - x[i]
        total += 0.5 * (y[i] + y[i + 1]) * dx
    return total


def cumulative_trapezoid_from_right(x: Sequence[float], y: Sequence[float]) -> List[float]:
    result = [0.0] * len(x)
    total = 0.0
    for i in range(len(x) - 2, -1, -1):
        dx = x[i + 1] - x[i]
        total += 0.5 * (y[i] + y[i + 1]) * dx
        result[i] = total
    return result


def interpolate_on_grid(x: Sequence[float], y: Sequence[float], x_new: float) -> float:
    if x_new <= x[0]:
        return y[0]
    if x_new >= x[-1]:
        return 0.0 if math.isclose(x_new, x[-1]) or x_new > x[-1] else y[-1]
    idx = bisect.bisect_left(x, x_new)
    if idx < len(x) and math.isclose(x[idx], x_new):
        return y[idx]
    return linear_interpolate(x[idx - 1], y[idx - 1], x[idx], y[idx], x_new)


def choose_vcut(speeds: Sequence[float], user_vcut: float | None) -> float:
    if user_vcut is not None:
        return user_vcut
    for speed in speeds:
        if speed > 0.0:
            return speed
    raise ValueError("Could not determine a positive integration floor from the input file")


def compute_eta_table(
    speeds: Sequence[float],
    fluxes: Sequence[float],
    vcut: float,
) -> Tuple[List[float], List[float], float, float]:
    if vcut <= 0.0:
        raise ValueError("vcut must be strictly positive")

    work_speeds, work_fluxes = sort_and_deduplicate(speeds, fluxes)
    if vcut > work_speeds[-1]:
        raise ValueError(f"vcut = {vcut} km/s is above the largest speed in the file")

    work_speeds, work_fluxes = insert_point(work_speeds, work_fluxes, vcut)
    start_idx = bisect.bisect_left(work_speeds, vcut)
    work_speeds = work_speeds[start_idx:]
    work_fluxes = work_fluxes[start_idx:]

    if len(work_speeds) < 2:
        raise ValueError("Need at least two support points above vcut to build eta(vmin)")

    integrand_n = [flux / speed for speed, flux in zip(work_speeds, work_fluxes)]
    normalization = trapezoid_integral(work_speeds, integrand_n)
    if normalization <= 0.0:
        raise ValueError("Non-positive normalization encountered in flux/v integral")

    integrand_eta = [flux / (speed * speed) for speed, flux in zip(work_speeds, work_fluxes)]
    numerator_cumulative = cumulative_trapezoid_from_right(work_speeds, integrand_eta)

    eta_out: List[float] = []
    for vmin in speeds:
        lower = max(vmin, vcut)
        numerator = interpolate_on_grid(work_speeds, numerator_cumulative, lower)
        eta_out.append(numerator / normalization)

    flux_total = trapezoid_integral(speeds, fluxes)
    n_eff_cm3 = normalization / KM_IN_CM
    return list(speeds), eta_out, flux_total, n_eff_cm3


def write_two_column_table(path: Path, x: Sequence[float], y: Sequence[float]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for x_i, y_i in zip(x, y):
            handle.write(f"{x_i:.12g}\t{y_i:.12g}\n")


def write_metadata(
    path: Path,
    input_path: Path,
    output_path: Path,
    mass_mev: float | None,
    vcut: float,
    flux_total: float,
    n_eff_cm3: float,
    fold_rho_into_eta: bool,
    reference_rho_gev_cm3: float,
    rho_fold_scale: float | None,
) -> None:
    rho_eff_gev_cm3 = None
    if mass_mev is not None:
        rho_eff_gev_cm3 = n_eff_cm3 * mass_mev * MEV_TO_GEV

    lines = [
        "# SRDM flux -> eta(vmin) conversion metadata",
        f"input_flux_file = {input_path}",
        f"output_eta_file = {output_path}",
        f"vcut_km_per_s = {vcut:.12g}",
        f"total_flux_cm^-2_s^-1 = {flux_total:.12g}",
        f"n_eff_cm^-3 = {n_eff_cm3:.12g}",
        (
            "eta_definition = "
            "[int_(vmin->inf) dv (dPhi/dv)/v^2] / [int_(vcut->inf) dv (dPhi/dv)/v]"
        ),
        f"fold_rho_into_eta = {str(fold_rho_into_eta).lower()}",
        f"reference_rho_GeV_cm^-3 = {reference_rho_gev_cm3:.12g}",
    ]
    if mass_mev is not None:
        lines.append(f"mass_MeV = {mass_mev:.12g}")
    if rho_eff_gev_cm3 is not None:
        lines.append(f"rho_eff_GeV_cm^-3 = {rho_eff_gev_cm3:.12g}")
    if rho_fold_scale is not None:
        lines.append(f"rho_fold_scale = {rho_fold_scale:.12g}")
    if fold_rho_into_eta:
        lines.append(
            "note = The exported eta has been rescaled by rho_eff / reference_rho. "
            "Use it with the downstream code's usual reference density."
        )
    else:
        lines.append(
            "note = The eta file is normalized independently of density. "
            "Use rho_eff_GeV_cm^-3 with DarkMatterRates if you want the absolute SRDM normalization."
        )

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        handle.write("\n".join(lines))
        handle.write("\n")


def main() -> int:
    args = parse_args()
    input_path = args.input.resolve()
    output_path = args.output.resolve() if args.output else input_path.with_name(f"{input_path.stem}_eta.txt")
    metadata_path = args.metadata.resolve() if args.metadata else output_path.with_name(f"{output_path.stem}_metadata.txt")

    speeds, fluxes = read_two_column_table(input_path)
    speeds, fluxes = sort_and_deduplicate(speeds, fluxes)
    vcut = choose_vcut(speeds, args.vcut_kms)

    eta_vmins, etas, flux_total, n_eff_cm3 = compute_eta_table(speeds, fluxes, vcut)

    rho_fold_scale = None
    rho_eff_gev_cm3 = None
    if args.mass_mev is not None:
        rho_eff_gev_cm3 = n_eff_cm3 * args.mass_mev * MEV_TO_GEV

    if args.fold_rho_into_eta:
        if rho_eff_gev_cm3 is None:
            raise ValueError("--fold-rho-into-eta requires --mass-mev so rho_eff can be computed")
        if args.reference_rho_gev_cm3 <= 0.0:
            raise ValueError("--reference-rho-gev-cm3 must be positive")
        rho_fold_scale = rho_eff_gev_cm3 / args.reference_rho_gev_cm3
        etas = [eta * rho_fold_scale for eta in etas]

    write_two_column_table(output_path, eta_vmins, etas)
    write_metadata(
        metadata_path,
        input_path,
        output_path,
        args.mass_mev,
        vcut,
        flux_total,
        n_eff_cm3,
        args.fold_rho_into_eta,
        args.reference_rho_gev_cm3,
        rho_fold_scale,
    )

    print(f"Wrote eta(vmin) file: {output_path}")
    print(f"Wrote metadata file: {metadata_path}")
    print(f"Integration floor vcut = {vcut:.6g} km/s")
    print(f"Total SRDM flux = {flux_total:.6g} cm^-2 s^-1")
    print(f"Effective SRDM number density = {n_eff_cm3:.6g} cm^-3")
    if args.mass_mev is not None:
        print(f"Effective SRDM mass density = {rho_eff_gev_cm3:.6g} GeV/cm^3")
    if rho_fold_scale is not None:
        print(f"Applied rho-fold scale = {rho_fold_scale:.6g} relative to rho_ref = {args.reference_rho_gev_cm3:.6g} GeV/cm^3")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
