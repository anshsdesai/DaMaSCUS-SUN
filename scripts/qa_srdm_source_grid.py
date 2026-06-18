#!/usr/bin/env python3
"""Validate and summarize a curated SRDM source-grid archive."""

from __future__ import annotations

import argparse
from pathlib import Path

import srdm_source_grid as grid


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-root", type=Path, default=grid.DEFAULT_RESULTS_ROOT)
    parser.add_argument(
        "--recommend-boundary",
        action="store_true",
        help="Mark all boundary points, not only corners, for high-stat pass-2 reruns.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = grid.repo_root_from_script()
    report = grid.write_qa_report(
        repo_root,
        args.results_root,
        recommend_boundary=args.recommend_boundary,
    )
    summary = report["summary"]
    print(
        "QA complete: "
        f"{summary['complete_points']}/{summary['total_points']} complete, "
        f"{summary['invalid_points']} invalid, "
        f"{len(summary['pass2_recommended_points'])} pass-2 recommendations"
    )
    return 0 if summary["invalid_points"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
