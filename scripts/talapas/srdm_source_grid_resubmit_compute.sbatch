#!/bin/bash

# Talapas resubmission pass for the SRDM source grid.
#
# Reruns ONLY the grid points that timed out in the first production pass
# (Slurm array job 44724793 -> master 44724793, per-task jobs 447266xx).
# All 55 failures were clean `DUE TO TIME LIMIT` timeouts at the original
# 20h wall; every other class (OOM, abort, MPI, missing-flux) was absent.
#
# This script is pinned to the SAME settings the completed 420 points were
# generated with, so the reran points are consistent with them:
#   RESULTS_ROOT           = results/srdm_fdmq2_source_grid_v1
#   SAMPLE_SIZE            = 10000
#   INTERPOLATION_POINTS   = 1000
#   ranks (--ntasks)      = 36
#
# --resume is passed, so any point already curated in v1 is skipped; combined
# with the restricted --array list below this only touches the 55 timeouts.
#
# The array list mirrors logs/srdm_rerun_indices.txt (regenerate it with
# scripts/talapas/summarize_srdm_slurm_logs.py after re-syncing logs). Slurm
# #SBATCH directives cannot read that file, so it is inlined here -- keep the
# two in sync if the completed set changes.
#
# Submit from the repository root:
#   sbatch scripts/talapas/srdm_source_grid_resubmit_compute.sbatch

#SBATCH --account=het
#SBATCH --job-name=srdm_src_grid_resub
#SBATCH --output=logs/srdm_src_grid_%A_%a.out
#SBATCH --error=logs/srdm_src_grid_%A_%a.err
#SBATCH --partition=computelong
#SBATCH --time=4-00:00:00
#SBATCH --ntasks=36
#SBATCH --ntasks-per-core=1
#SBATCH --constraint=7713
#SBATCH --array=76,95,114,133,152-153,171-172,190-191,209-210,228-229,247-249,266-268,285-287,304-306,323-325,342-344,361-363,380-383,399-402,418-421,437-440,456-459%8

set -euo pipefail

module purge
module load gcc/13.1.0
module load mpich/4.1.1
module load libconfig/1.7.3
module load eigen/3.4.0

REPO_ROOT="${SLURM_SUBMIT_DIR}"
RESULTS_ROOT="${RESULTS_ROOT:-results/srdm_fdmq2_source_grid_v1}"
SAMPLE_SIZE="${SAMPLE_SIZE:-10000}"
INTERPOLATION_POINTS="${INTERPOLATION_POINTS:-1000}"
MPI_RANKS="${SLURM_NTASKS}"

cd "${REPO_ROOT}"
mkdir -p logs

echo "host=$(hostname)"
echo "job=${SLURM_JOB_ID} task=${SLURM_ARRAY_TASK_ID}"
echo "repo=${REPO_ROOT}"
echo "sample_size=${SAMPLE_SIZE} interpolation_points=${INTERPOLATION_POINTS} ranks=${MPI_RANKS}"

python3 scripts/run_srdm_source_grid.py \
  --index "${SLURM_ARRAY_TASK_ID}" \
  --results-root "${RESULTS_ROOT}" \
  --sample-size "${SAMPLE_SIZE}" \
  --interpolation-points "${INTERPOLATION_POINTS}" \
  --mpi-ranks "${MPI_RANKS}" \
  --launcher srun \
  --resume
