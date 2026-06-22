#!/usr/bin/env python3
"""Summarize DaMaSCUS-SUN SRDM Slurm array logs and write rerun lists."""

from __future__ import annotations

import argparse
import csv
import json
import re
from dataclasses import dataclass, field
from pathlib import Path


LOG_RE = re.compile(r"srdm_src_(?P<kind>grid|pilot)_(?P<job_id>\d+)_(?P<index>\d+)\.(?P<stream>out|err)$")


@dataclass
class TaskSummary:
    job_id: str
    index: int
    kind: str
    out_file: Path | None = None
    err_file: Path | None = None
    sample_size: str = ""
    interpolation_points: str = ""
    ranks: str = ""
    mass_mev: str = ""
    sigma_e_cm2: str = ""
    run_id: str = ""
    started: bool = False
    interpolated: bool = False
    generated: bool = False
    simulator_finished: bool = False
    wrapper_complete: bool = False
    wrapper_skipped: bool = False
    curated_flux_exists: bool = False
    flags: set[str] = field(default_factory=set)

    @property
    def complete(self) -> bool:
        return (self.wrapper_complete or self.wrapper_skipped) and not self.flags

    @property
    def needs_rerun(self) -> bool:
        if self.flags:
            return True
        if self.curated_flux_exists:
            return False
        return not (self.wrapper_complete or self.wrapper_skipped)

    @property
    def needs_more_time(self) -> bool:
        return "TIMEOUT" in self.flags or (self.generated and not self.complete)

    def issue_text(self) -> str:
        issues = sorted(self.flags)
        if not self.started:
            issues.append("NO_START")
        elif not self.interpolated:
            issues.append("NO_INTERPOLATION")
        elif not self.generated and not self.wrapper_complete:
            issues.append("NO_GENERATION")
        elif self.generated and not self.wrapper_complete:
            issues.append("NO_WRAPPER_COMPLETE")
        if self.curated_flux_exists and not self.wrapper_complete:
            issues.append("CURATED_FLUX_EXISTS")
        return ",".join(dict.fromkeys(issues))


def read_text(path: Path | None) -> str:
    if path is None or not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="ignore")


def first_match(pattern: str, text: str, default: str = "") -> str:
    match = re.search(pattern, text, flags=re.MULTILINE)
    return match.group(1).strip() if match else default


def parse_json_status(text: str) -> tuple[bool, bool]:
    json_objects = re.findall(r"\{[^{}]*\"status\"\s*:\s*\"(?:complete|skipped)\"[^{}]*\}", text)
    for line in reversed(json_objects):
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        status = payload.get("status")
        if status == "complete":
            return True, False
        if status == "skipped":
            return False, True
    return False, False


def discover_tasks(logs_dir: Path, job_id: str | None) -> dict[tuple[str, int], TaskSummary]:
    tasks: dict[tuple[str, int], TaskSummary] = {}
    for path in logs_dir.glob("srdm_src_*_*.*"):
        match = LOG_RE.match(path.name)
        if not match:
            continue
        if job_id and match.group("job_id") != job_id:
            continue
        key = (match.group("job_id"), int(match.group("index")))
        task = tasks.setdefault(
            key,
            TaskSummary(
                job_id=match.group("job_id"),
                index=int(match.group("index")),
                kind=match.group("kind"),
            ),
        )
        if match.group("stream") == "out":
            task.out_file = path
        else:
            task.err_file = path
    return tasks


def update_from_logs(task: TaskSummary, results_root: Path | None) -> None:
    out_text = read_text(task.out_file)
    err_text = read_text(task.err_file)

    setting = re.search(r"sample_size=(\d+)\s+interpolation_points=(\d+)\s+ranks=(\d+)", out_text)
    if setting:
        task.sample_size, task.interpolation_points, task.ranks = setting.groups()
    task.mass_mev = first_match(r"m_DM \[MeV\]:\s*([^\n\r]+)", out_text)
    task.sigma_e_cm2 = first_match(r"sigma_e \[cm2\]:\s*([^\n\r]+)", out_text)
    task.run_id = first_match(r"ID:\s*(srdm_fdmq2_source_[^\n\r]+)", out_text)

    task.started = "[Started on" in out_text
    task.interpolated = "Interpolate total DM scattering rate" in out_text
    task.generated = "Generate data with" in out_text
    task.simulator_finished = "Simulation time:" in out_text or "[Finished in" in out_text
    task.wrapper_complete, task.wrapper_skipped = parse_json_status(out_text)

    if "DUE TO TIME LIMIT" in err_text:
        task.flags.add("TIMEOUT")
    if "Out Of Memory" in err_text or "oom_kill" in err_text or "OOM Killed" in err_text:
        task.flags.add("OOM")
    if "Signal: Aborted" in err_text or "Aborted (core dumped)" in err_text:
        task.flags.add("ABORT")
    if "CANCELLED AT" in err_text and "DUE TO TIME LIMIT" not in err_text:
        task.flags.add("CANCELLED")
    if "Traceback" in out_text or "Traceback" in err_text:
        task.flags.add("TRACEBACK")
    if "Expected source flux is missing" in out_text or "Expected source flux is missing" in err_text:
        task.flags.add("MISSING_SOURCE_FLUX")
    fatal_transport = "libuct_ib" in err_text or ("ucx" in err_text.lower() and ("error" in err_text.lower() or "fatal" in err_text.lower()))
    if fatal_transport:
        task.flags.add("MPI_TRANSPORT")

    if results_root is not None and task.run_id:
        point_tag = task.run_id.replace("srdm_fdmq2_source_", "", 1)
        task.curated_flux_exists = (results_root / "points" / point_tag / "Differential_SRDM_Flux.txt").exists()


def compress_indices(indices: list[int]) -> str:
    if not indices:
        return ""
    ranges: list[str] = []
    start = prev = indices[0]
    for index in indices[1:]:
        if index == prev + 1:
            prev = index
            continue
        ranges.append(f"{start}-{prev}" if start != prev else str(start))
        start = prev = index
    ranges.append(f"{start}-{prev}" if start != prev else str(start))
    return ",".join(ranges)


def write_outputs(tasks: list[TaskSummary], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    summary_path = output_dir / "srdm_slurm_log_summary.tsv"
    rerun_path = output_dir / "srdm_rerun_indices.txt"
    more_time_path = output_dir / "srdm_more_time_indices.txt"

    fields = [
        "job_id",
        "index",
        "kind",
        "sample_size",
        "interpolation_points",
        "ranks",
        "mDM_MeV",
        "sigma_e_cm2",
        "started",
        "interpolated",
        "generated",
        "simulator_finished",
        "wrapper_complete",
        "wrapper_skipped",
        "curated_flux_exists",
        "complete",
        "needs_rerun",
        "needs_more_time",
        "issues",
        "out_file",
        "err_file",
    ]
    with summary_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t")
        writer.writeheader()
        for task in tasks:
            writer.writerow(
                {
                    "job_id": task.job_id,
                    "index": task.index,
                    "kind": task.kind,
                    "sample_size": task.sample_size,
                    "interpolation_points": task.interpolation_points,
                    "ranks": task.ranks,
                    "mDM_MeV": task.mass_mev,
                    "sigma_e_cm2": task.sigma_e_cm2,
                    "started": task.started,
                    "interpolated": task.interpolated,
                    "generated": task.generated,
                    "simulator_finished": task.simulator_finished,
                    "wrapper_complete": task.wrapper_complete,
                    "wrapper_skipped": task.wrapper_skipped,
                    "curated_flux_exists": task.curated_flux_exists,
                    "complete": task.complete,
                    "needs_rerun": task.needs_rerun,
                    "needs_more_time": task.needs_more_time,
                    "issues": task.issue_text(),
                    "out_file": str(task.out_file or ""),
                    "err_file": str(task.err_file or ""),
                }
            )

    rerun_indices = sorted(task.index for task in tasks if task.needs_rerun)
    more_time_indices = sorted(task.index for task in tasks if task.needs_more_time)
    rerun_path.write_text(compress_indices(rerun_indices) + "\n", encoding="utf-8")
    more_time_path.write_text(compress_indices(more_time_indices) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--logs-dir", type=Path, default=Path("logs"))
    parser.add_argument("--job-id", default=None, help="Only summarize one Slurm array job id.")
    parser.add_argument("--results-root", type=Path, default=None, help="Optional curated grid directory to check for flux files.")
    parser.add_argument("--output-dir", type=Path, default=Path("logs"))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    tasks_by_key = discover_tasks(args.logs_dir, args.job_id)
    tasks = [tasks_by_key[key] for key in sorted(tasks_by_key, key=lambda item: (item[0], item[1]))]
    for task in tasks:
        update_from_logs(task, args.results_root)
    write_outputs(tasks, args.output_dir)

    rerun = [task.index for task in tasks if task.needs_rerun]
    more_time = [task.index for task in tasks if task.needs_more_time]
    complete = [task.index for task in tasks if task.complete]
    print(f"summarized {len(tasks)} tasks")
    print(f"complete: {len(complete)}")
    print(f"needs rerun: {len(rerun)} ({compress_indices(sorted(rerun))})")
    print(f"needs more time: {len(more_time)} ({compress_indices(sorted(more_time))})")
    print(f"wrote {args.output_dir / 'srdm_slurm_log_summary.tsv'}")
    print(f"wrote {args.output_dir / 'srdm_rerun_indices.txt'}")
    print(f"wrote {args.output_dir / 'srdm_more_time_indices.txt'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
