#!/usr/bin/env bash
# Run the isolated, deterministic R2 Compose acceptance harness.
#
# The harness never reads ignored local configuration, EPUBs, data, Codex
# credentials, or a Codex session. It builds the atomic R2 profile set with
# tracked fixture credentials and a local fake provider, proves the live
# transport/security boundaries, and writes four redacted JSON reports.
#
# Example:
#   VERIFY_PROJECT=librarian-answer-delivery-r2 \
#     ANSWER_DELIVERY_REPORT_DIR=/tmp/librarian-answer-delivery-r2 \
#     scripts/run_answer_delivery_compose.sh
set -euo pipefail

readonly report_dir="${ANSWER_DELIVERY_REPORT_DIR:?ANSWER_DELIVERY_REPORT_DIR is required}"
readonly project_name="${VERIFY_PROJECT:-librarian-answer-delivery-r2}"
readonly runtime_dir=".runtime/answer-delivery"
readonly report_names=(
  compose-summary.json
  authorization.json
  compatibility.json
  cancellation.json
)
readonly profiles=(codex-broker workers metadata-workers evaluation)
readonly config_resolver_profile=config-resolver
readonly caller_services=(api summary-worker metadata-worker)

if ! [[ "$project_name" =~ ^[a-z0-9][a-z0-9_-]*$ ]]; then
  echo "[librarian] VERIFY_PROJECT must contain only lowercase letters, digits, underscores, or hyphens." >&2
  exit 2
fi
if [[ "$report_dir" == "/" || "$report_dir" == "." ]]; then
  echo "[librarian] ANSWER_DELIVERY_REPORT_DIR must be a dedicated report directory." >&2
  exit 2
fi
if ! command -v docker >/dev/null 2>&1 || ! docker info >/dev/null 2>&1; then
  echo "[librarian] Docker must be available for R2 Compose acceptance." >&2
  exit 2
fi
if [[ -n "$(git status --porcelain)" ]]; then
  echo "[librarian] R2 Compose acceptance requires a clean release checkout." >&2
  exit 2
fi
if [[ -e "$runtime_dir" ]]; then
  echo "[librarian] Refusing to reuse existing harness runtime state: $runtime_dir" >&2
  exit 2
fi
if [[ -e "$report_dir" && -n "$(find "$report_dir" -mindepth 1 -print -quit)" ]]; then
  echo "[librarian] ANSWER_DELIVERY_REPORT_DIR must be empty before acceptance." >&2
  exit 2
fi

release_sha="$(git rev-parse HEAD)"
if ! [[ "$release_sha" =~ ^[0-9a-f]{40}$ ]]; then
  echo "[librarian] Could not resolve a clean 40-character release SHA." >&2
  exit 2
fi

created_report_dir=false
if [[ ! -e "$report_dir" ]]; then
  mkdir -p "$report_dir"
  created_report_dir=true
fi
mkdir -p "$runtime_dir"

compose=(
  docker compose
  --project-name "$project_name"
)
for profile in "${profiles[@]}"; do
  compose+=(--profile "$profile")
done
compose+=(
  -f docker-compose.yml
  -f docker-compose.r2.yml
  -f docker-compose.answer-delivery.yml
)

# The resolver is a one-shot bootstrap service. It needs its own overlay
# profile, but that internal setup profile must not appear in the four reports
# that describe the externally exercised R2 callers.
config_resolver_compose=(
  docker compose
  --project-name "$project_name"
  --profile "$config_resolver_profile"
)
for profile in "${profiles[@]}"; do
  config_resolver_compose+=(--profile "$profile")
done
config_resolver_compose+=(
  -f docker-compose.yml
  -f docker-compose.r2.yml
  -f docker-compose.answer-delivery.yml
)

cleanup() {
  local status=$?
  trap - EXIT INT TERM
  "${compose[@]}" down --volumes --remove-orphans >/dev/null 2>&1 || true
  rm -rf "$runtime_dir"
  if ((status != 0)); then
    for report_name in "${report_names[@]}"; do
      rm -f "$report_dir/$report_name"
    done
    if [[ "$created_report_dir" == true ]]; then
      rmdir "$report_dir" 2>/dev/null || true
    fi
  fi
  exit "$status"
}
trap cleanup EXIT
trap 'exit 130' INT TERM

export LIBRARIAN_STACK_RELEASE_SHA="$release_sha"

# Resolve only the tracked R2 fixture configuration. The generated documents
# live under this harness's disposable state directory, never under config/.
"${config_resolver_compose[@]}" run --rm --build config-resolver
compose+=( -f "$runtime_dir/librarian.compose.json" )

# Rendering is a release gate. The later live checks prove the container state
# rather than accepting this static representation by itself.
rendered_compose="$runtime_dir/rendered-compose.json"
"${compose[@]}" config --format json >"$rendered_compose"
python3 - "$rendered_compose" <<'PY'
import json
import sys
from pathlib import Path

compose = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
services = compose["services"]
required = {"api", "codex-broker", "summary-worker", "metadata-worker", "evaluator"}
if not required.issubset(services):
    raise SystemExit("rendered R2 Compose configuration omits a required principal")
broker = services["codex-broker"]
if broker.get("ports"):
    raise SystemExit("rendered R2 broker publishes a host port")
if set(broker["networks"]) != {
    "broker-api",
    "broker-summary-worker",
    "broker-metadata-worker",
    "broker-evaluator",
    "broker-egress",
}:
    raise SystemExit("rendered R2 broker network boundary is incorrect")
expected = {
    "api": "broker-api",
    "summary-worker": "broker-summary-worker",
    "metadata-worker": "broker-metadata-worker",
    "evaluator": "broker-evaluator",
}
for service, private_network in expected.items():
    rendered = services[service]
    if set(rendered["networks"]) != {"application", private_network}:
        raise SystemExit(f"rendered R2 network boundary is incorrect for {service}")
    secret_names = {secret["source"] for secret in rendered["secrets"]}
    if secret_names != {f"codex-broker-{service}"}:
        raise SystemExit(f"rendered R2 secret boundary is incorrect for {service}")
    config_mounts = [mount for mount in rendered["volumes"] if mount["target"] == "/config/librarian.json"]
    if len(config_mounts) != 1 or not config_mounts[0].get("read_only"):
        raise SystemExit(f"rendered R2 runtime config mount is incorrect for {service}")
    if any(mount["target"].startswith("/config/secrets") for mount in rendered["volumes"]):
        raise SystemExit(f"rendered R2 config secrets are exposed to {service}")
if any("codex-broker-session" in str(mount) for mount in broker.get("volumes", [])):
    raise SystemExit("acceptance broker must not mount a Codex session")
PY
"${compose[@]}" up --build --detach --wait codex-broker opensearch api summary-worker metadata-worker

# The evaluator is intentionally one-shot; exercise its real startup wrapper
# without invoking a corpus evaluation or any external model.
"${compose[@]}" run --rm --no-deps --entrypoint python evaluator \
  -m librarian_answer_adapters.r2_startup --principal evaluator -- python -c 'pass'

assert_client_isolation() {
  local service="$1"
  local role="$2"
  local secret="codex-broker-$role"
  "${compose[@]}" exec -T "$service" python -c '
import json
import os
import stat
import sys
from pathlib import Path

role, secret = sys.argv[1:]
secret_dir = Path("/run/secrets")
expected = secret_dir / secret
if set(path.name for path in secret_dir.iterdir()) != {secret}:
    raise SystemExit("unexpected caller secret mount")
metadata = expected.lstat()
if not stat.S_ISREG(metadata.st_mode) or expected.is_symlink():
    raise SystemExit("caller secret is not a regular non-symlink file")
if Path("/config/secrets").exists():
    raise SystemExit("caller can access recursive config secrets")
payload = json.loads(Path("/config/librarian.json").read_text(encoding="utf-8"))
encoded = json.dumps(payload, sort_keys=True)
if "api_key_file" in encoded or "/run/secrets/" in encoded:
    raise SystemExit("runtime configuration contains a credential reference")
if payload["answer_delivery"]["codex_broker"]["credential_role"] != role:
    raise SystemExit("runtime configuration role does not match service")
' "$role" "$secret"
}

for service in "${caller_services[@]}"; do
  role="${service}"
  assert_client_isolation "$service" "$role"
done

# The metadata service name already equals its principal; evaluator gets the
# same mount/config assertion through a disposable profile-enabled container.
"${compose[@]}" run --rm --no-deps --entrypoint python evaluator -c '
import json
import os
import stat
from pathlib import Path

secret = Path("/run/secrets/codex-broker-evaluator")
if set(path.name for path in secret.parent.iterdir()) != {secret.name}:
    raise SystemExit("unexpected evaluator secret mount")
if not stat.S_ISREG(secret.lstat().st_mode) or secret.is_symlink():
    raise SystemExit("evaluator secret is not a regular non-symlink file")
if Path("/config/secrets").exists():
    raise SystemExit("evaluator can access recursive config secrets")
payload = json.loads(Path("/config/librarian.json").read_text(encoding="utf-8"))
if payload["answer_delivery"]["codex_broker"]["credential_role"] != "evaluator":
    raise SystemExit("evaluator runtime role is incorrect")
if "api_key_file" in json.dumps(payload, sort_keys=True):
    raise SystemExit("evaluator runtime configuration contains a credential reference")
'

"${compose[@]}" exec -T codex-broker python -c '
import json
import stat
from pathlib import Path

expected = {
    "codex-broker-api",
    "codex-broker-summary-worker",
    "codex-broker-metadata-worker",
    "codex-broker-evaluator",
    "codex-broker-health",
}
secret_dir = Path("/run/secrets")
if set(path.name for path in secret_dir.iterdir()) != expected:
    raise SystemExit("broker secret mount set is incorrect")
if any(not stat.S_ISREG(path.lstat().st_mode) or path.is_symlink() for path in secret_dir.iterdir()):
    raise SystemExit("broker secret is not a regular non-symlink file")
if Path("/config/secrets").exists():
    raise SystemExit("broker can access recursive config secrets")
payload = json.loads(Path("/config/librarian.json").read_text(encoding="utf-8"))
if set(payload) != {"version", "generation"}:
    raise SystemExit("broker runtime configuration is not strict")
'

assert_networks() {
  local service="$1"
  local expected_csv="$2"
  local container_id
  container_id="$("${compose[@]}" ps -q "$service")"
  if [[ -z "$container_id" ]]; then
    echo "[librarian] Required service is not running: $service" >&2
    return 1
  fi
  local networks
  networks="$(docker inspect --format '{{json .NetworkSettings.Networks}}' "$container_id")"
  python3 -c '
import json
import sys

actual = {name.rsplit("_", 1)[-1] for name in json.loads(sys.argv[1])}
expected = set(sys.argv[2].split(","))
if actual != expected:
    raise SystemExit(f"network isolation mismatch: expected {sorted(expected)}, got {sorted(actual)}")
' "$networks" "$expected_csv"
}

assert_networks codex-broker 'broker-api,broker-summary-worker,broker-metadata-worker,broker-evaluator,broker-egress'
assert_networks api 'application,broker-api'
assert_networks summary-worker 'application,broker-summary-worker'
assert_networks metadata-worker 'application,broker-metadata-worker'

broker_id="$("${compose[@]}" ps -q codex-broker)"
broker_port_bindings="$(docker inspect --format '{{json .HostConfig.PortBindings}}' "$broker_id")"
python3 -c '
import json
import sys

if json.loads(sys.argv[1]) not in ({}, None):
    raise SystemExit("R2 broker unexpectedly publishes a host port")
' "$broker_port_bindings"
"${compose[@]}" exec -T codex-broker python -c '
import socket
with socket.socket() as probe:
    probe.settimeout(0.2)
    if probe.connect_ex(("127.0.0.1", 3000)) == 0:
        raise SystemExit("legacy HTTP broker listener is still reachable")
'

probe_output="$runtime_dir/probe.json"
"${compose[@]}" exec -T codex-broker python -m librarian_broker.compose_harness probe >"$probe_output"
python3 scripts/validate_answer_delivery_compose_reports.py \
  --probe "$probe_output" \
  --report-dir "$report_dir" \
  --release-sha "$release_sha" \
  --profiles "${profiles[@]}"

echo "[librarian] R2 Compose acceptance passed; redacted reports are in $report_dir."
