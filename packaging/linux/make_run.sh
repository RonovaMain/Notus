#!/usr/bin/env bash
# Build a self-extracting .run from a tar.gz that contains a single top-level folder.
# Usage: make_run.sh <version> <path/to/Notus-<version>-linux-x86_64.tar.gz> <output.run>
set -euo pipefail
VERSION="$1"; TARBALL="$2"; OUT="$3"
HERE="$(cd "$(dirname "$0")" && pwd)"
sed "s/@VERSION@/${VERSION}/g" "$HERE/stub.sh" > "$OUT"
cat "$TARBALL" >> "$OUT"
chmod +x "$OUT"
echo "Created $OUT"
