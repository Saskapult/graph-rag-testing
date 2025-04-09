#!/bin/bash
#SBATCH --time=00:30:00
#SBATCH --account=def-ycoady
#SBATCH --gpus=p100:1            # Request one P100 GPU
#SBATCH --mem=15G                # Necessary but could probably be lower
#SBATCH --signal=B:SIGUSR1@60    # Signal at 60 seconds before termination

echo "Moving apptainer to node local storage"
cp ollama-phi4.sif $SLURM_TMPDIR

echo "Starting apptainer"
module load apptainer
apptainer instance start \
--nv \
"$SLURM_TMPDIR/ollama-phi4.sif" ollama-phi4

echo "Running script"
srun apptainer exec instance://ollama-phi4 uv run mine_generate.py &
wait 

echo "Stopping apptainer"
apptainer instance stop ollama-phi4

echo "Done!"
exit 0
