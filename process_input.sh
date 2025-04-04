#!/bin/bash
#SBATCH --time=00:15:00
#SBATCH --account=def-ycoady
#SBATCH --gpus=p100:1            # Request one P100 GPU
#SBATCH --mem=15G                # Necessary but could probably be lower
#SBATCH --signal=B:SIGUSR1@120   # Signal at 120 seconds before termination

# Expects a single pdf file 
INPUT=$1
# Output directory 
OUTDIR=$2

# Set up termination signal handling
function sig_handler_USR1() {
	echo "Received prophecy of impending termination"

	touch "$OUTDIR/this_was_interrupted"
	
	exit 2
}
trap 'sig_handler_USR1' SIGUSR1

# Should be very fast becuase we've already installed everything 
# Profile perfromance impact of this versus node-local storage
# echo "Syncing uv dependencies"
# uv sync 

# echo "Moving input to node-local storage"
# cp $INPUT $SLURM_TMPDIR

echo "Moving apptainer to node local storage"
cp ollama-phi4.sif $SLURM_TMPDIR

echo "Starting apptainer"
module load apptainer
apptainer instance start \
--nv \
"$SLURM_TMPDIR/ollama-phi4.sif" ollama-phi4

# I'm assuming it's fine to leave these in the home storage
# TODO: the checkpoints should be written to network storage 
# Add a checkpoints directory option to the script 
echo "Running script"
mkdir -p $OUTDIR
apptainer exec instance://ollama-phi4 uv run process.py -ai --only 3 -o "$OUTDIR" "$INPUT" 
#apptainer exec instance://ollama-phi4 bash sky_command.sh

echo "Stopping apptainer"
apptainer instance stop ollama-phi4

echo "Done!"
exit 0
