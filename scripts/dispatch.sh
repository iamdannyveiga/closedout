#!/bin/sh
# dispatch.sh: send a brief file to a worker model over a plain API key and record the reply.
#
# Usage: dispatch.sh <brief.md> <out.md>
#
# Environment:
#   CLOSEDOUT_PROVIDER  anthropic or openai (default: anthropic)
#   CLOSEDOUT_BASE_URL  provider base URL, no trailing slash
#   CLOSEDOUT_API_KEY   provider API key
#   CLOSEDOUT_MODEL     model id to run
#
# Provider shapes:
#   anthropic  POST $CLOSEDOUT_BASE_URL/v1/messages with the x-api-key header
#   openai     POST $CLOSEDOUT_BASE_URL/chat/completions with a bearer token
#
# The openai branch covers every OpenAI-compatible endpoint: OpenAI, DeepSeek,
# Zhipu, xAI, OpenRouter and a server on your own machine.
#
# Writes the model's text reply to the output path, and a sidecar next to it with
# the model, the latency in milliseconds and the token counts when the provider
# returns them. The sidecar is named after the output: out.md gets out.meta.json,
# and any other path gets <out>.meta.json. Read the numbers from the sidecar
# rather than from memory, and put them into the ledger with:
#   python3 ledger/closedout.py dispatch <loop> --model "$CLOSEDOUT_MODEL" --class <lane>
#
# Exits nonzero on an HTTP error and prints the status and the head of the body.

set -eu

usage() {
  echo "usage: dispatch.sh <brief.md> <out.md>" >&2
  exit 2
}

[ "$#" -eq 2 ] || usage

brief=$1
out=$2

[ -f "$brief" ] || { echo "dispatch.sh: no such brief: $brief" >&2; exit 2; }

: "${CLOSEDOUT_PROVIDER:=anthropic}"

# Checked with :- rather than with ${VAR:?word}, because the shell prints its own
# name and line number with that form, which is noise in a dispatch log. All the
# missing names are reported at once, so one run tells you everything to set.
missing=
[ -n "${CLOSEDOUT_MODEL:-}" ]    || missing="$missing CLOSEDOUT_MODEL"
[ -n "${CLOSEDOUT_API_KEY:-}" ]  || missing="$missing CLOSEDOUT_API_KEY"
[ -n "${CLOSEDOUT_BASE_URL:-}" ] || missing="$missing CLOSEDOUT_BASE_URL"
if [ -n "$missing" ]; then
  echo "dispatch.sh: set these before dispatching:$missing" >&2
  exit 2
fi

base=${CLOSEDOUT_BASE_URL%/}

work=$(mktemp -d "${TMPDIR:-/tmp}/closedout.XXXXXX") || exit 3
trap 'rm -rf "$work"' EXIT INT TERM

case "$CLOSEDOUT_PROVIDER" in
  anthropic)
    url="$base/v1/messages"
    python3 - "$brief" "$CLOSEDOUT_MODEL" > "$work/req.json" <<'PY'
import json, sys
brief_path, model = sys.argv[1], sys.argv[2]
with open(brief_path, "r", encoding="utf-8") as handle:
    text = handle.read()
print(json.dumps({
    "model": model,
    "max_tokens": 8000,
    "messages": [{"role": "user", "content": text}],
}))
PY
    ;;
  openai)
    url="$base/chat/completions"
    python3 - "$brief" "$CLOSEDOUT_MODEL" > "$work/req.json" <<'PY'
import json, sys
brief_path, model = sys.argv[1], sys.argv[2]
with open(brief_path, "r", encoding="utf-8") as handle:
    text = handle.read()
print(json.dumps({
    "model": model,
    "messages": [{"role": "user", "content": text}],
}))
PY
    ;;
  *)
    echo "dispatch.sh: CLOSEDOUT_PROVIDER must be anthropic or openai, got '$CLOSEDOUT_PROVIDER'" >&2
    exit 2
    ;;
esac

# curl is allowed to fail here so the exit code can be reported with the body.
set +e
if [ "$CLOSEDOUT_PROVIDER" = "anthropic" ]; then
  metrics=$(curl -sS -o "$work/body.json" -w '%{http_code} %{time_total}' -X POST "$url" \
    -H 'content-type: application/json' \
    -H "x-api-key: $CLOSEDOUT_API_KEY" \
    -H 'anthropic-version: 2023-06-01' \
    --data @"$work/req.json")
  rc=$?
else
  metrics=$(curl -sS -o "$work/body.json" -w '%{http_code} %{time_total}' -X POST "$url" \
    -H 'content-type: application/json' \
    -H "Authorization: Bearer $CLOSEDOUT_API_KEY" \
    --data @"$work/req.json")
  rc=$?
fi
set -e

if [ "$rc" -ne 0 ]; then
  echo "dispatch.sh: the request to $url failed with exit $rc" >&2
  exit "$rc"
fi

code=${metrics%% *}
seconds=${metrics##* }

if [ "$code" -lt 200 ] || [ "$code" -ge 300 ]; then
  echo "dispatch.sh: HTTP $code from $url" >&2
  # dd rather than head -c, because the byte count is a GNU and BSD extension of
  # head and this script is POSIX sh everywhere else.
  dd if="$work/body.json" bs=400 count=1 >&2 2>/dev/null
  echo >&2
  exit 4
fi

case "$out" in
  *.md) meta="${out%.md}.meta.json" ;;
  *)    meta="$out.meta.json" ;;
esac

python3 - "$work/body.json" "$out" "$meta" "$CLOSEDOUT_PROVIDER" "$CLOSEDOUT_MODEL" "$seconds" <<'PY'
import json, sys

body_path, out_path, meta_path, provider, model, seconds = sys.argv[1:7]

with open(body_path, "r", encoding="utf-8") as handle:
    raw = handle.read()

try:
    data = json.loads(raw)
except ValueError:
    sys.stderr.write("dispatch.sh: the reply was not JSON\n")
    sys.stderr.write(raw[:400] + "\n")
    raise SystemExit(5)

tokens_in = None
tokens_out = None
text = ""

if provider == "anthropic":
    parts = []
    for block in data.get("content") or []:
        if isinstance(block, dict) and block.get("type") == "text":
            parts.append(block.get("text") or "")
    text = "".join(parts)
    usage = data.get("usage") or {}
    tokens_in = usage.get("input_tokens")
    tokens_out = usage.get("output_tokens")
else:
    choices = data.get("choices") or []
    if choices:
        text = ((choices[0].get("message") or {}).get("content")) or ""
    usage = data.get("usage") or {}
    tokens_in = usage.get("prompt_tokens")
    tokens_out = usage.get("completion_tokens")

if not text.strip():
    sys.stderr.write("dispatch.sh: the reply carried no text\n")
    raise SystemExit(6)

if not text.endswith("\n"):
    text += "\n"
with open(out_path, "w", encoding="utf-8") as handle:
    handle.write(text)

meta = {
    "provider": provider,
    "model": model,
    "latency_ms": int(round(float(seconds) * 1000)),
    "tokens_in": tokens_in,
    "tokens_out": tokens_out,
}
with open(meta_path, "w", encoding="utf-8") as handle:
    handle.write(json.dumps(meta, indent=2) + "\n")

print("wrote %s using %s in %d ms" % (out_path, model, meta["latency_ms"]))
PY
