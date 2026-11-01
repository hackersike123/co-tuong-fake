#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

if [[ ! -f .env ]]; then
  printf 'Missing required .env configuration.\n' >&2
  exit 1
fi

compose_files=(
  -f compose.yaml
  -f compose.production.yaml
  -f compose.certbot.yaml
)

compose_env_files=(--env-file .env)
if ! docker compose "${compose_env_files[@]}" "${compose_files[@]}" config --quiet; then
  if [[ ! -f .env.compose.local ]]; then
    printf 'Compose configuration failed and .env.compose.local is not present.\n' >&2
    exit 1
  fi
  compose_env_files+=(--env-file .env.compose.local)
  docker compose "${compose_env_files[@]}" "${compose_files[@]}" config --quiet
fi

docker compose "${compose_env_files[@]}" "${compose_files[@]}" --profile certbot run --rm certbot \
  renew --quiet
docker compose "${compose_env_files[@]}" "${compose_files[@]}" exec -T nginx nginx -s reload
