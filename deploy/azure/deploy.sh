#!/bin/sh
set -eu
cd "$(dirname "$0")"
mode=${1:-tts}
if [ "$mode" != tts ] && [ "$mode" != scan ]; then
    echo 'Usage: sh deploy.sh tts|scan' >&2
    exit 2
fi
if [ "$mode" = scan ]; then
    # Read only the required DB fields through Compose's rendered environment.
    # Never print the resolved config, which includes passwords/service keys.
    docker compose --env-file .env.azure --profile scan config --format json | python3 -c '
import json,sys
env=json.load(sys.stdin)["services"]["scan"]["environment"]
required=["AI_SYSTEM_DB_HOST","AI_SYSTEM_DB_NAME","AI_SYSTEM_DB_USER","AI_SYSTEM_DB_PASSWORD"]
missing=[name for name in required if not env.get(name) or env[name]=="unconfigured.invalid"]
if missing:
    print("Configure existing BE database first: "+", ".join(missing),file=sys.stderr)
    sys.exit(1)
'
    docker compose --env-file .env.azure --profile scan up -d --build --wait --wait-timeout 120 scan
else
    docker compose --env-file .env.azure up -d --build --wait --wait-timeout 360 tts proxy
fi
docker compose --env-file .env.azure --profile scan ps
