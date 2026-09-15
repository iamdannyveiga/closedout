#!/bin/sh
# harness-codex.sh: dispatch a brief through the Codex CLI instead of a raw API call.
#
# Usage: harness-codex.sh <brief.md> <out.md>
#
# The codex CLI must be installed and authenticated on the machine that runs
# this script. FOREMAN_API_KEY is not used on this path; the CLI carries its own
# credentials.
#
# FOREMAN_MODEL names the worker model, for example gpt-5. Leave it unset to use
# the default below.
#
# exec runs one non-interactive turn. -m sets the model and -o writes the final
# message to a file, which is the shape the ledger wants for a worker output
# receipt. Flag names have moved between releases, so check `codex exec --help`
# against your version if this fails.

set -eu

usage() {
  echo "usage: harness-codex.sh <brief.md> <out.md>" >&2
  exit 2
}

[ "$#" -eq 2 ] || usage

brief=$1
out=$2

[ -f "$brief" ] || { echo "harness-codex.sh: no such brief: $brief" >&2; exit 2; }

: "${FOREMAN_MODEL:=gpt-5}"

command -v codex >/dev/null 2>&1 || {
  echo "harness-codex.sh: the codex CLI is not on PATH. Install it and sign in first." >&2
  exit 3
}

prompt=$(cat "$brief")

codex exec -m "$FOREMAN_MODEL" -o "$out" "$prompt"
