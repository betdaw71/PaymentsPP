#!/usr/bin/env bash
# Regenerate partner commercial offer PDF from partner-offer.html
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
HTML="$DIR/partner-offer.html"
OUT="$DIR/AvaPay-partner-offer.pdf"

CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
if [[ ! -x "$CHROME" ]]; then
  echo "Google Chrome not found at $CHROME" >&2
  exit 1
fi

"$CHROME" --headless --disable-gpu --no-pdf-header-footer \
  --print-to-pdf="$OUT" "file://$HTML"

echo "Wrote $OUT ($(wc -c <"$OUT" | tr -d ' ') bytes)"
