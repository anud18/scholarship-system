#!/usr/bin/env bash
# Three-way (technically four-way) diff over the *-vm.alloy files. Surfaces
# unintentional drift between staging/prod and ap/db variants.
set -euo pipefail
OUT=${AUDIT_OUT_DIR:-docs/superpowers/audits/working}
DIR=monitoring/config/alloy
mkdir -p "$OUT/api-responses/alloy-crossvm"

# pairwise diffs
for a in staging-ap-vm staging-db-vm prod-ap-vm prod-db-vm; do
  for b in staging-ap-vm staging-db-vm prod-ap-vm prod-db-vm; do
    [ "$a" \< "$b" ] || continue
    diff -u "$DIR/$a.alloy" "$DIR/$b.alloy" \
      > "$OUT/api-responses/alloy-crossvm/diff-${a}-vs-${b}.txt" || true
  done
done

# block summary: count blocks per file
for f in "$DIR"/*.alloy; do
  base=$(basename "$f" .alloy)
  echo "=== $base ==="
  grep -E '^[a-z_.]+ "[^"]*"' "$f" | sort | uniq -c
done > "$OUT/api-responses/alloy-crossvm/block-summary.txt"

echo "alloy diffs written under $OUT/api-responses/alloy-crossvm/"
