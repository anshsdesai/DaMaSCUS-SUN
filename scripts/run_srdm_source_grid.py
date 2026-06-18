#!/usr/bin/env python3
"""Prepare or run the production SRDM source grid."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import srdm_source_grid as grid


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-root", type=Path, default=grid.DEFAULT_RESULTS_ROOT)
    parser.add_argument("--template", type=Path, default=grid.DEFAULT_TEMPLATE)
    parser.add_argument("--sample-size", type=int, default=grid.DEFAULT_SAMPLE_SIZE)
    parser.add_argument("--interpolation-points", type=int, default=grid.DEFAULT_INTERPOLATION_POINTS)
    parser.add_argument("--rho-ref-gev-cm3", type=float, default=grid.DEFAULT_RHO_REF_GEV_CM3)
    parser.add_argument("--mpi-ranks", type=int, default=4)
    parser.add_argument("--launcher", choices=["mpirun", "srun"], default="mpirun")
    parser.add_argument("--index", type=int, default=None, help="Run one grid point by manifest index.")
    parser.add_argument("--pilot", action="store_true", help="Run the 4 representative pilot indices.")
    parser.add_argument("--prepare-only", action="store_true", help="Render configs and manifests only.")
    parser.add_argument("--postprocess-only", action="store_true", help="Curate existing DaMaSCUS-SUN result output without launching the executable.")
    parser.add_argument("--resume", action="store_true", help="Skip already curated complete points.")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite curated point files when rerunning.")
    parser.add_argument("--print-pilot-indices", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = grid.repo_root_from_script()
    template = args.template if args.template.is_absolute() else repo_root / args.template

    if args.print_pilot_indices:
        print(" ".join(str(i) for i in grid.pilot_indices()))
        return 0

    if args.prepare_only:
        grid.prepare_configs(
            repo_root,
            args.results_root,
            template,
            args.sample_size,
            args.interpolation_points,
        )
        print(f"prepared {len(grid.all_points())} grid entries under {grid.scan_root(repo_root, args.results_root)}")
        return 0

    if args.pilot:
        indices = grid.pilot_indices()
    elif args.index is not None:
        indices = [args.index]
    else:
        raise SystemExit("Provide --index, --pilot, --prepare-only, or --print-pilot-indices.")

    results = []
    for index in indices:
        point = grid.point_by_index(index)
        result = grid.run_grid_point(
            repo_root=repo_root,
            results_root=args.results_root,
            template_path=template,
            point=point,
            sample_size=args.sample_size,
            interpolation_points=args.interpolation_points,
            mpi_ranks=args.mpi_ranks,
            launcher=args.launcher,
            rho_ref_gev_cm3=args.rho_ref_gev_cm3,
            resume=args.resume,
            overwrite=args.overwrite,
            postprocess_only=args.postprocess_only,
        )
        results.append(result)
        print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
