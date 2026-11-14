#!/usr/bin/env bash
# Zips the pack folder into $1, leaving out $EXCLUDE (space-separated zip patterns, e.g. 'build/*').
# Globbing is off so each pattern reaches zip as written: unquoted, the shell turned 'build/*' into the
# folder's own entries, which left everything inside them in the zip.
set -euo pipefail
set -f
rm -f "$1"
zip -q -r -X "$1" . -x $EXCLUDE
