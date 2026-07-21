#!/bin/bash
echo "Initializing MEZO Local AI Platform Dependencies..."
cd mezo-frontend && npm install && cd ..
cd mezo-backend && npm install && cd ..
echo "Setup completed successfully!"
