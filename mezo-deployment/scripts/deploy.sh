#!/bin/bash
echo "Launching all 10 MEZO Services via Docker Compose..."
docker-compose -f docker/docker-compose.yml up -d --build
