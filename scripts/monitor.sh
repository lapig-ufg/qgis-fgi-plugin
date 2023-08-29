#!/bin/bash

# Function to get PIDs of qgis
get_qgis_pids() {
    pgrep -f qgis
}

# Loop until qgis processes are found
while true; do
    pids=$(get_qgis_pids)

    if [[ -n "$pids" ]]; then
        break
    fi

    # Sleep for a short duration and check again
    sleep 1
done

# Now run py-spy on each PID
for pid in $pids; do
    output_file="qgis-output-$pid.log"
    echo "Starting py-spy for PID $pid, output to $output_file"

    # Start py-spy in the background for each PID
    py-spy record -o $output_file --pid $pid &

    # Optionally, sleep for a short duration before checking the next PID
    sleep 0.1
done

echo "All py-spy instances started. Press any key to terminate them."

# Wait for user input to terminate the py-spies
read -n 1 -s

# Kill all py-spy processes
pkill -f 'py-spy record'
echo "Terminated all py-spy processes."
