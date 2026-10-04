#!/usr/bin/env bash
set -euo pipefail
cd /opt/swing-trading-bot
container_id=$(docker compose -f compose.v6.yaml ps -q bot)
if [ -n "$container_id" ] && [ "$(docker inspect --format '{{.State.Health.Status}}' "$container_id")" = unhealthy ]; then
    docker compose -f compose.v6.yaml restart bot
fi
