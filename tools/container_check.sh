#!/usr/bin/env bash
# Check an image without external networking, credentials or a saved TV selection.
set -euo pipefail
image="${1:?Usage: bash tools/container_check.sh IMAGE}"
base="beoremote-release-check-$$"
options_dir="$(mktemp -d)"
cleanup() {
  docker rm -f "$base-disabled" "$base-auto" "$base-defaults" >/dev/null 2>&1 || true
  rm -f "$options_dir/disabled.json" "$options_dir/auto.json" "$options_dir/defaults.json"
  rmdir "$options_dir"
}
trap cleanup EXIT
for mode in disabled auto defaults; do
  container="$base-$mode"
  if [ "$mode" = defaults ]; then
    echo '{}' > "$options_dir/$mode.json"
  else
    echo "{\"mode\":\"$mode\"}" > "$options_dir/$mode.json"
  fi
  docker run --name "$container" --network none --init \
    --mount "type=bind,src=$options_dir/$mode.json,dst=/data/options.json,readonly" \
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
  docker exec "$container" python -c 'import json;from pathlib import Path;s=json.loads(Path("/tmp/beoremote-gateway-health.json").read_text());assert not s["listener"] and not s["discovery"] and s["ha"]["delivery"]=="disabled"'
  docker exec "$container" python -c 'import urllib.request,urllib.error
try:
 urllib.request.urlopen("http://127.0.0.1:8099/api/status",timeout=2)
except urllib.error.HTTPError as error:
 assert error.code==403
else:
 raise AssertionError("Setup UI accepted a direct connection")'
  docker stop --timeout 10 "$container" >/dev/null
  test "$(docker inspect --format '{{.State.ExitCode}}' "$container")" = 0
  echo "Container passed: $mode startup, ingress restriction, heartbeat and graceful shutdown."
done
