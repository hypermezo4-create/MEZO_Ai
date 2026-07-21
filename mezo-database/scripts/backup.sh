#!/bin/bash
echo "Starting MEZO Database Backup..."
pg_dump -U mezo_user -d mezo_db > backup_$(date +%Y%m%d_%H%M%S).sql
echo "Backup complete!"
