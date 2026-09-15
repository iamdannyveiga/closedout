#!/bin/sh
# harness-claude-code.sh: dispatch a brief through Claude Code instead of a raw API call.
#
# Usage: harness-claude-code.sh <brief.md> <out.md>
#
# This is an example wrapper for people who use Claude Code as the worker
# harness. The claude CLI must be installed and authenticated on the machine
# that runs this script. FOREMAN_API_KEY is not used on this path; the CLI
# carries its own credentials.
#
# FOREMAN_MODEL names the worker model, for example claude-sonnet-5. Leave it
# unset to use the default below.
#
# Add the flags your own setup needs to let the worker read files and run
# commands. The prompt goes in on stdin and the reply comes out on stdout, so
# the brief stays the contract exactly as it does with dispatch.sh.

set -eu

usage() {
  echo "usage: harness-claude-code.sh <brief.md> <out.md>" >&2
  exit 2
}

[ "$#" -eq 2 ] || usage

brief=$1
out=$2

[ -f "$brief" ] || { echo "harness-claude-code.sh: no such brief: $brief" >&2; exit 2; }

: "${FOREMAN_MODEL:=claude-sonnet-5}"

command -v claude >/dev/null 2>&1 || {
  echo "harness-claude-code.sh: the claude CLI is not on PATH. Install it and sign in first." >&2
  exit 3
}

claude -p --model "$FOREMAN_MODEL" < "$brief" > "$out"
