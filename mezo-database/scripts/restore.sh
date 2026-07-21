#!/bin/bash
if [ -z "$1" ]; then
    echo "Usage: ./restore.sh <backup_file.sql>"
    exit 1
fi
echo "Restoring MEZO Database from $1..."
psql -U mezo_user -d mezo_db < "$1"
echo "Restore complete!"
