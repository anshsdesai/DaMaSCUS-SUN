#!/usr/bin/env bash
#SBATCH --job-name=srdm-src-grid
#SBATCH --output=logs/srdm-src-grid_%A_%a.out
#SBATCH --error=logs/srdm-src-grid_%A_%a.err
#
# Submit with site-specific resources, for example:
#   sbatch --account=<account> --partition=<partition> --time=04:00:00 \
#     --ntasks=8 --array=0-474%24 scripts/talapas/srdm_source_grid_array.sbatch

set -euo pipefail

REPO_ROOT="${REPO_ROOT:-${SLURM_SUBMIT_DIR}}"
RESULTS_ROOT="${RESULTS_ROOT:-results/srdm_fdmq2_source_grid_v1}"
SAMPLE_SIZE="${SAMPLE_SIZE:-100000}"
INTERPOLATION_POINTS="${INTERPOLATION_POINTS:-1000}"
LAUNCHER="${LAUNCHER:-srun}"
MPI_RANKS="${SLURM_NTASKS:-${MPI_RANKS:-4}}"

cd "${REPO_ROOT}"
mkdir -p logs

if command -v module >/dev/null 2>&1; then
  module purge
  if [[ -n "${TALAPAS_MODULES:-}" ]]; then
    for mod in ${TALAPAS_MODULES}; do
      module load "${mod}"
    done
  fi
fi

python3 scripts/run_srdm_source_grid.py \
  --index "${SLURM_ARRAY_TASK_ID}" \
  --results-root "${RESULTS_ROOT}" \
  --sample-size "${SAMPLE_SIZE}" \
  --interpolation-points "${INTERPOLATION_POINTS}" \
  --mpi-ranks "${MPI_RANKS}" \
  --launcher "${LAUNCHER}" \
  --resume
