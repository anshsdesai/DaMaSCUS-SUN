#!/bin/bash

# Talapas pilot validation for the SRDM source grid.
#
# Submit from the repository root with:
#   sbatch scripts/talapas/srdm_source_grid_pilot_compute.sbatch
#
# Each Slurm array element runs one representative grid point.  Each element
# receives its own allocation of --ntasks ranks.

#SBATCH --account=het
#SBATCH --job-name=srdm_src_pilot
#SBATCH --output=logs/srdm_src_pilot_%A_%a.out
#SBATCH --error=logs/srdm_src_pilot_%A_%a.err
#SBATCH --partition=compute
#SBATCH --time=0-20:00:00
#SBATCH --ntasks=36
#SBATCH --ntasks-per-core=1
#SBATCH --constraint=7713
#SBATCH --array=0,18,456,474%4

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
