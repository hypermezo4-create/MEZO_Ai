#!/bin/bash
echo "Deploying MEZO Platform to Fly.io..."
fly deploy --config fly/fly.toml
