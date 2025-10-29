#!/bin/bash
#
# Deadline Checker Script
#
# This script runs the deadline checker task to send notifications
# for approaching deadlines (submission, document requests, reviews).
#
# Usage:
#   ./scripts/check_deadlines.sh
#
# Add to crontab for automatic execution:
#   # Run every day at 9:00 AM
#   0 9 * * * /path/to/backend/scripts/check_deadlines.sh
#

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Get the backend directory (parent of scripts)
BACKEND_DIR="$(dirname "$SCRIPT_DIR")"

# Change to backend directory
cd "$BACKEND_DIR"

# Activate virtual environment if it exists
if [ -d "venv" ]; then
    source venv/bin/activate
elif [ -d "../venv" ]; then
    source ../venv/bin/activate
fi

# Run the deadline checker
echo "Running deadline checker at $(date)"
python -m app.tasks.deadline_checker

# Check exit code
if [ $? -eq 0 ]; then
    echo "Deadline checker completed successfully at $(date)"
else
    echo "Deadline checker failed at $(date)" >&2
    exit 1
fi
