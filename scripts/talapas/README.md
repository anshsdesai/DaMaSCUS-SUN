# Talapas SRDM Source Grid Workflow

This directory contains parameterized Slurm templates for the SRDM source grid.
Talapas account, partition, walltime, module names, and array throttles are
intentionally supplied at submit time.

## One-Time Build

```bash
module spider cmake
module spider gcc
module spider openmpi

module load <compiler-module> <mpi-module> <cmake-module>
cmake -E make_directory build
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release -DCODE_COVERAGE=OFF
cmake --build build --config Release -j
cmake --install build
python3 scripts/run_srdm_source_grid.py --prepare-only
```

## Pilot Gate

Run representative low/high mass and low/high cross-section points first:

```bash
python3 scripts/run_srdm_source_grid.py --print-pilot-indices

TALAPAS_MODULES="<compiler-module> <mpi-module> <cmake-module>" \
SAMPLE_SIZE=10000 \
sbatch --account=<account> --partition=<partition> --time=02:00:00 \
  --ntasks=4 --array=0,18,456,474 scripts/talapas/srdm_source_grid_pilot.sbatch
```

If you prefer the Talapas documentation style where the resource choices live
inside the script, edit and submit:

```bash
sbatch scripts/talapas/srdm_source_grid_pilot_compute.sbatch
```

That concrete pilot script uses the open `compute` partition, 36 MPI ranks per
pilot point, and the `0,18,456,474%4` array.  Slurm gives each array element its
own allocation, so four pilot points can run at once when resources are
available.  If queue time is long or you want to be gentler, change `%4` to `%1`
or `%2`.

After the pilot finishes, validate the source files and downstream consumers:

```bash
python3 scripts/qa_srdm_source_grid.py
python3 scripts/validate_srdm_pipeline.py \
  --verne-root ../verne \
  --damascus-root ../DaMaSCUS
```

Add `--run-damascus` to execute the DaMaSCUS SRDMBeam smoke configs instead of
only writing them.

## Production Pass 1

```bash
TALAPAS_MODULES="<compiler-module> <mpi-module> <cmake-module>" \
SAMPLE_SIZE=100000 \
sbatch --account=<account> --partition=<partition> --time=04:00:00 \
  --ntasks=8 --array=0-474%24 scripts/talapas/srdm_source_grid_array.sbatch
```

For the concrete Talapas script-style setup, submit the production array with:

```bash
sbatch scripts/talapas/srdm_source_grid_production_compute.sbatch
```

The production script uses `--array=0-474%8`, so every source-grid point is a
separate Slurm allocation with 36 MPI ranks, and at most 8 points run
concurrently.  Keep it on `compute` if pilot timings are comfortably below one
day.  Switch `--partition=compute` to `--partition=computelong` only for points
that need more than the `compute` partition walltime.

## QA And Pass 2

```bash
python3 scripts/qa_srdm_source_grid.py
```

The QA report is written to:

```text
results/srdm_fdmq2_source_grid_v1/qa_report.json
results/srdm_fdmq2_source_grid_v1/qa_report.tsv
```

Use `summary.pass2_recommended_points` from `qa_report.json` as the second-pass
array list, with a larger sample size such as `SAMPLE_SIZE=1000000`.

## Slurm Log Summary

After downloading Talapas logs, summarize completed and incomplete array tasks with:

```bash
python3 scripts/talapas/summarize_srdm_slurm_logs.py \
  --job-id <array-job-id> \
  --results-root results/srdm_fdmq2_source_grid_v1 \
  --output-dir logs
```

This writes:

```text
logs/srdm_slurm_log_summary.tsv
logs/srdm_rerun_indices.txt
logs/srdm_more_time_indices.txt
```

Use `srdm_rerun_indices.txt` as the next Slurm array list, and use
`srdm_more_time_indices.txt` for points that likely need a longer walltime or a
smaller first-pass sample size.