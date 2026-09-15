#!/bin/sh
# inspect.sh: run one inspector model over one file and report its verdict.
#
# Usage: inspect.sh <brief.md> <file-to-review> <out.md>
#
# Same environment as dispatch.sh:
#   FOREMAN_PROVIDER, FOREMAN_BASE_URL, FOREMAN_API_KEY, FOREMAN_MODEL
#
# Set FOREMAN_MODEL to a model from a family other than the coder's family, and
# run the script twice with two different values. Those are the two inspector
# verdicts the doctrine requires. A third run with a state inspector model covers
# ledger schema, hooks, send paths and anything transactional.
#
# The prompt is built from templates/inspector-rubric.md, the brief the work was
# written against, and the file under review. The inspector reads all three, and
# is never handed the coder's summary of its own work.
#
# Exit 0 when the first line of <out.md> is PASS.
# Exit 1 when it is FAIL.
# Exit 2 when it is neither, or when the call never completed, which means the
# run itself is not a usable verdict.

set -eu

usage() {
  echo "usage: inspect.sh <brief.md> <file-to-review> <out.md>" >&2
  exit 2
}

[ "$#" -eq 3 ] || usage

brief=$1
target=$2
out=$3

[ -f "$brief" ] || { echo "inspect.sh: no such brief: $brief" >&2; exit 2; }
[ -f "$target" ] || { echo "inspect.sh: no such file to review: $target" >&2; exit 2; }

dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
rubric="$dir/../templates/inspector-rubric.md"
[ -f "$rubric" ] || { echo "inspect.sh: no rubric at $rubric" >&2; exit 2; }

work=$(mktemp -d "${TMPDIR:-/tmp}/foreman-inspect.XXXXXX") || exit 3
trap 'rm -rf "$work"' EXIT INT TERM

prompt="$work/prompt.md"
{
  cat "$rubric"
  echo
  echo "## The brief this work was written against"
  echo
  cat "$brief"
  echo
  echo "## The file under review: $target"
  echo
  echo '```'
  cat "$target"
  echo '```'
} > "$prompt"

# dispatch.sh writes the verdict to $out and the call metadata to $out.meta.json.
# A call that never completed is not a FAIL verdict, so it leaves here as "no
# verdict" instead of reaching the caller as curl's exit code 1.
if ! "$dir/dispatch.sh" "$prompt" "$out"; then
  echo "inspect.sh: the dispatch failed, so this run produced no verdict" >&2
  exit 2
fi

first=$(head -n 1 "$out" | tr -d '\r' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')
# The rubric asks for the word PASS or the word FAIL and nothing else on the
# line, so the match is exact. A prefix match would read PASSING and FAILURE as
# verdicts, and neither of those is one.
verdict=$(printf '%s' "$first" | tr '[:lower:]' '[:upper:]')

case "$verdict" in
  PASS)
    echo "inspect.sh: PASS" >&2
    exit 0
    ;;
  FAIL)
    echo "inspect.sh: FAIL" >&2
    exit 1
    ;;
  *)
    echo "inspect.sh: the first line was neither PASS nor FAIL: $first" >&2
    echo "inspect.sh: treat this run as no verdict and dispatch the inspection again" >&2
    exit 2
    ;;
esac
