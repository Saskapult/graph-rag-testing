#!/bin/bash
#SBATCH --time=00:30:00
#SBATCH --account=def-ycoady
#SBATCH --gpus=p100:1            # Request one P100 GPU
#SBATCH --mem=15G                # Necessary but could probably be lower
#SBATCH --signal=B:SIGUSR1@16   # Signal at 16 seconds before termination

# Expects a single pdf file 
INPUT=$1
# Output directory 
OUTDIR=$2

# Set up termination signal handling
function sig_handler_USR1() {
	echo "Received prophecy of impending termination"

	if [ ! -f "$OUTDIR/index.json" ]; then
		echo "Resubmitting job"
		sbatch $BASH_SOURCE "$@"
	else
		echo "Work seems done"
	fi

	exit 2
}
trap 'sig_handler_USR1' SIGUSR1

echo "Moving apptainer to node local storage"
cp ollama-phi4.sif $SLURM_TMPDIR

echo "Starting apptainer"
module load apptainer
apptainer instance start \
--nv \
"$SLURM_TMPDIR/ollama-phi4.sif" ollama-phi4

echo "Running script"
mkdir -p $OUTDIR
apptainer exec instance://ollama-phi4 uv run process.py -ai -o "$OUTDIR" "$INPUT" 

echo "Stopping apptainer"
apptainer instance stop ollama-phi4

echo "Done!"
exit 0
