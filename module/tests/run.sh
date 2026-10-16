#!/usr/bin/env bash
# Runs the strixec I/O loop regression test against the real module source.
# Extracts strixec_read/strixec_write verbatim from ../strixec.c; no kernel needed.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
sed -n '/^static ssize_t strixec_read/,/^static const struct file_operations/p' \
    "$HERE/../strixec.c" | sed '$d' | sed '/SEEK_END/,/^}/d' > "$WORK/io_under_test.inc"
cc -Wall -Wextra -Wno-unused-parameter -std=gnu11 -I"$WORK" -o "$WORK/io_test" "$HERE/io_test.c"
"$WORK/io_test"
