#!/bin/bash
# NAS deploy script: pull latest code en rebuild container
# Gebruik: ssh nas "cd /volume1/docker/m4b-dashboard && bash update.sh"
set -e
BASE="$(cd "$(dirname "$0")" && pwd)"

echo "==> Git pull..."
git -C "$BASE" pull

echo "==> Rebuild en herstart container..."
cd "$BASE" && docker compose up --build -d

echo "==> Klaar! Dashboard: http://192.168.1.101:8082"
