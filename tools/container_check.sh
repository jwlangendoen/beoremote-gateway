#!/usr/bin/env bash
# Check an already built image with no external networking or HA credentials.
set -euo pipefail
image="${1:?Usage: bash tools/container_check.sh IMAGE}"
container="beoremote-release-check-$$"
options_dir="$(mktemp -d)"
cleanup() {
  docker rm -f "$container" >/dev/null 2>&1 || true
  # Only remove the exact temporary file/directory created by this script.
  rm -f "$options_dir/options.json"
  rmdir "$options_dir"
}
trap cleanup EXIT
echo '{}' > "$options_dir/options.json"
docker run --name "$container" --network none --init \
  --mount "type=bind,src=$options_dir/options.json,dst=/data/options.json,readonly" \
  -d "$image" >/dev/null
state=starting
for attempt in $(seq 1 45); do
  state=$(docker inspect --format '{{.State.Health.Status}}' "$container")
  if [ "$state" = healthy ]; then break; fi
  sleep 1
done
docker logs "$container"
test "$state" = healthy
docker exec "$container" python -m gateway.health --check
docker stop --timeout 10 "$container" >/dev/null
test "$(docker inspect --format '{{.State.ExitCode}}' "$container")" = 0
echo 'Container passed: disabled startup, heartbeat, graceful shutdown; external networking disabled.'
