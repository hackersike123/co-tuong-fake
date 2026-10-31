#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

compose_files=(
  -f compose.yaml
  -f compose.production.yaml
  -f compose.certbot.yaml
)

docker compose "${compose_files[@]}" --profile certbot run --rm certbot \
  renew --quiet
docker compose "${compose_files[@]}" exec -T nginx nginx -s reload
