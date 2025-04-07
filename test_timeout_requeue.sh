#!/bin/bash
#SBATCH --time=00:00:60
#SBATCH --account=def-ycoady
#SBATCH --signal=B:SIGUSR1@15

function sig_handler_USR1() {
	echo "Received prophecy of impending termination"

	if [ ! -f "timeout_requeue_marker" ]; then
		echo "Mark and resubmit"
		touch "timeout_requeue_marker"
		sbatch $BASH_SOURCE "$@"
	else
		echo "Unreachable 2"
	fi

	exit 2
}
trap 'sig_handler_USR1' SIGUSR1

if [ -f "timeout_requeue_marker" ]; then
	echo "Marker exists"
else
	echo "Marker not exists, sleep"
	sleep 120
	echo "Unreachable 1"
fi

echo "Done!"
exit 0
