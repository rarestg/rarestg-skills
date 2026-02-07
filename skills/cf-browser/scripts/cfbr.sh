#!/usr/bin/env bash
# cfbr.sh — Thin wrapper around Cloudflare Browser Rendering REST API.
# Usage: cfbr.sh <endpoint> '<json_body>'
# Example: cfbr.sh markdown '{"url":"https://example.com"}'
#
# Requires CF_ACCOUNT_ID and CF_API_TOKEN env vars.

set -euo pipefail

endpoint="${1:?Usage: cfbr.sh <endpoint> '<json_body>'}"
body="${2:?Usage: cfbr.sh <endpoint> '<json_body>'}"

: "${CF_ACCOUNT_ID:?Set CF_ACCOUNT_ID env var}"
: "${CF_API_TOKEN:?Set CF_API_TOKEN env var}"

base="https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/browser-rendering"

# Binary endpoints return raw bytes; everything else returns JSON.
case "$endpoint" in
  screenshot)
    outfile="${3:-screenshot.png}"
    curl -s --fail-with-body -X POST "$base/$endpoint" \
      -H "Authorization: Bearer $CF_API_TOKEN" \
      -H "Content-Type: application/json" \
      -d "$body" \
      --output "$outfile"
    echo "$outfile"
    ;;
  *)
    curl -s -X POST "$base/$endpoint" \
      -H "Authorization: Bearer $CF_API_TOKEN" \
      -H "Content-Type: application/json" \
      -d "$body"
    ;;
esac
