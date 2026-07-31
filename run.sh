#!/bin/bash
# Terminal Launcher for Autonomous Rover & Clover Drone Hardware Mission Control
# Usage: ./run.sh [start_cell] [target_cell]
# Example: ./run.sh D1 F3

START=${1:-"D1"}
TARGET=${2:-"F3"}

echo "----------------------------------------------------"
echo "  Launching Rover & Clover Drone Hardware Control..."
echo "  Start Cell: $START | Target Cell: $TARGET"
echo "----------------------------------------------------"

python3 main.py --start "$START" --target "$TARGET" "$@"

