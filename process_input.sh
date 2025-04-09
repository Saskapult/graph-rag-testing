#!/bin/bash
#SBATCH --time=00:30:00
#SBATCH --account=def-ycoady
#SBATCH --gpus=p100:1            # Request one P100 GPU
#SBATCH --mem=15G                # Necessary but could probably be lower
#SBATCH --signal=B:SIGUSR1@60    # Signal at 60 seconds before termination

echo "executed with arguments $@"
echo "resubmit with sbatch $BASH_SOURCE $@"
exit 0

# Expects a single pdf file 
INPUT=$1
# Output directory 
OUTDIR=$2

# Set up termination signal handling
function sig_handler_USR1() {
	echo "Received prophecy of impending termination"

	if [ ! -f "$OUTDIR/index.json" ]; then
		echo "Work is not done"
		if [ $(ls $OUTDIR | wc -l) == $NOUTPUTS ]; then
			echo "No progress was made, skipping resubmission"
		else
			echo "Resubmitting job"
			# Sleep so we have a chance to cancel 
			sleep 15
			echo "sbatch $BASH_SOURCE $@"
			sbatch $BASH_SOURCE $@
		fi
	else
		echo "Work seems done"
	fi

	exit 2
}
trap 'sig_handler_USR1' SIGUSR1

mkdir -p $OUTDIR
NOUTPUTS=$(ls $OUTDIR | wc -l)

echo "Moving apptainer to node local storage"
cp ollama-phi4.sif $SLURM_TMPDIR

echo "Starting apptainer"
module load apptainer
apptainer instance start \
--nv \
"$SLURM_TMPDIR/ollama-phi4.sif" ollama-phi4

echo "Running script"
# Execute in background so that the signal interrupt works
srun apptainer exec instance://ollama-phi4 uv run process.py -ai --skiperrors -o "$OUTDIR" "$INPUT" &
wait 

echo "Stopping apptainer"
apptainer instance stop ollama-phi4

echo "Done!"
exit 0
