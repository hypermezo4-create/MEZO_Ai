#!/bin/bash
echo "Backing up MEZO Platform data and checkpoints..."
tar -czvf mezo_backup_$(date +%Y%m%d).tar.gz mezo-database/ mezo-ai-engine/models/
