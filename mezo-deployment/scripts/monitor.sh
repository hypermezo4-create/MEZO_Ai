#!/bin/bash
echo "Monitoring running containers..."
docker ps --filter "name=mezo"
