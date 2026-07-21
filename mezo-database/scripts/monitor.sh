#!/bin/bash
echo "MEZO Database Health Monitoring..."
psql -U mezo_user -d mezo_db -c "SELECT count(*) FROM pg_stat_activity;"
