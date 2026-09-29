#!/usr/bin/env bash
# Generate and verify the checked-in Python stubs for Librarian's protobuf API.
#
# Usage:
#   scripts/generate_contracts.sh
#   scripts/generate_contracts.sh --check
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: scripts/generate_contracts.sh [--check]

Generate the canonical answer-delivery descriptor and Python gRPC stubs.
--check verifies that checked-in generated files match the pinned protobuf/gRPC toolchain.
EOF
}

check_only=false
if (($# == 1)); then
  case "$1" in
    --check) check_only=true ;;
    -h|--help) usage; exit 0 ;;
    *) usage >&2; exit 2 ;;
  esac
elif (($# != 0)); then
  usage >&2
  exit 2
fi

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
proto_root="$repo_root/proto"
proto_file="librarian/answer/v1/answer_delivery.proto"
contracts_root="$repo_root/packages/librarian_contracts"
descriptor_path="$proto_root/librarian/answer/v1/answer_delivery.pb"
expected_tools_version="1.80.0"
expected_protobuf_version="6.33.6"

installed_tools_version="$(python3 -c 'from importlib.metadata import version; print(version("grpcio-tools"))' 2>/dev/null || true)"
if [[ "$installed_tools_version" != "$expected_tools_version" ]]; then
  printf 'grpcio-tools %s is required; found %s\n' "$expected_tools_version" "${installed_tools_version:-missing}" >&2
  exit 1
fi

installed_protobuf_version="$(python3 -c 'from importlib.metadata import version; print(version("protobuf"))' 2>/dev/null || true)"
if [[ "$installed_protobuf_version" != "$expected_protobuf_version" ]]; then
  printf 'protobuf %s is required; found %s\n' "$expected_protobuf_version" "${installed_protobuf_version:-missing}" >&2
  exit 1
fi

temporary_directory="$(mktemp -d)"
cleanup() {
  rm -rf "$temporary_directory"
}
trap cleanup EXIT

temporary_generated_root="$temporary_directory/librarian_contracts/generated"
temporary_descriptor="$temporary_directory/answer_delivery.pb"
mkdir -p "$temporary_generated_root"
python3 -m grpc_tools.protoc \
  --proto_path="$proto_root" \
  --python_out="$temporary_generated_root" \
  --grpc_python_out="$temporary_generated_root" \
  --descriptor_set_out="$temporary_descriptor" \
  --include_imports \
  "$proto_root/$proto_file"

for package_directory in \
  "$temporary_generated_root" \
  "$temporary_generated_root/librarian" \
  "$temporary_generated_root/librarian/answer" \
  "$temporary_generated_root/librarian/answer/v1"; do
  touch "$package_directory/__init__.py"
done

temporary_grpc_stub="$temporary_generated_root/librarian/answer/v1/answer_delivery_pb2_grpc.py"
python3 -c '
from pathlib import Path
path = Path(__import__("sys").argv[1])
path.write_text(
    path.read_text(encoding="utf-8").replace(
        "from librarian.answer.v1 import",
        "from librarian_contracts.generated.librarian.answer.v1 import",
    ),
    encoding="utf-8",
)
' "$temporary_grpc_stub"

generated_files=(
  "generated/__init__.py"
  "generated/librarian/__init__.py"
  "generated/librarian/answer/__init__.py"
  "generated/librarian/answer/v1/__init__.py"
  "generated/librarian/answer/v1/answer_delivery_pb2.py"
  "generated/librarian/answer/v1/answer_delivery_pb2_grpc.py"
)

if [[ "$check_only" == "true" ]]; then
  for generated_file in "${generated_files[@]}"; do
    diff -u "$contracts_root/$generated_file" "$temporary_directory/librarian_contracts/$generated_file"
  done
  cmp "$descriptor_path" "$temporary_descriptor"
  printf 'Generated contracts are current.\n'
  exit 0
fi

for generated_file in "${generated_files[@]}"; do
  mkdir -p "$(dirname "$contracts_root/$generated_file")"
  cp "$temporary_directory/librarian_contracts/$generated_file" "$contracts_root/$generated_file"
done
cp "$temporary_descriptor" "$descriptor_path"
printf 'Generated answer-delivery contracts.\n'
