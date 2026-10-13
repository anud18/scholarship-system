#!/usr/bin/env bash
# Make `docker compose` and `docker buildx` available to the rest of the job.
#
# The `testing` runner has docker engine but no CLI plugins, and its user has
# no sudo. When a plugin is missing, download a pinned, checksum-verified
# binary into a job-local DOCKER_CONFIG (under $RUNNER_TEMP) and export that
# dir through $GITHUB_ENV — nothing on the runner host is modified.
set -euo pipefail

COMPOSE_VERSION=v5.5.1
COMPOSE_SHA256=db1889184726840f75c4f9c001048430d4f25b3be3cb084d3ddd762bc0aed576
BUILDX_VERSION=v0.37.1
BUILDX_SHA256=9447199cdb435f25880548343c128a4b6650e8891ee598905d8d29d39a8e359b

if docker compose version >/dev/null 2>&1 && docker buildx version >/dev/null 2>&1; then
  docker compose version
  docker buildx version
  exit 0
fi

if [ "$(uname -m)" != "x86_64" ]; then
  echo "::error::docker compose/buildx missing and auto-install only supports x86_64 (got $(uname -m))"
  exit 1
fi

export DOCKER_CONFIG="$RUNNER_TEMP/docker-config"
mkdir -p "$DOCKER_CONFIG/cli-plugins"

install_plugin() {
  local name=$1 url=$2 sha=$3
  local dest="$DOCKER_CONFIG/cli-plugins/docker-$name"
  curl -fsSL --retry 3 -o "$dest" "$url"
  echo "$sha  $dest" | sha256sum -c -
  chmod +x "$dest"
}

# Install both even if only one is missing: the job-local DOCKER_CONFIG hides
# any plugin that lived in ~/.docker/cli-plugins.
install_plugin compose \
  "https://github.com/docker/compose/releases/download/${COMPOSE_VERSION}/docker-compose-linux-x86_64" \
  "$COMPOSE_SHA256"
install_plugin buildx \
  "https://github.com/docker/buildx/releases/download/${BUILDX_VERSION}/buildx-${BUILDX_VERSION}.linux-amd64" \
  "$BUILDX_SHA256"

echo "DOCKER_CONFIG=$DOCKER_CONFIG" >> "$GITHUB_ENV"
docker compose version
docker buildx version
