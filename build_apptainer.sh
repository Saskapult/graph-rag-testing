#!/bin/bash
#SBATCH --time=00:30:00
#SBATCH --account=def-ycoady

# Doesn't need to be a job, executes fine otherwise

module load apptainer
time APPTAINER_NO_MOUNT=tmp apptainer build -F ollama-phi4.sif ollama-phi4.def
