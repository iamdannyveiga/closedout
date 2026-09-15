# closedout

Instructions for an agent session running under Codex CLI, Gemini CLI or
OpenCode. The rule is the same in all three. The doctrine in full is
`doctrine/CLOSEDOUT.md`, and the brief, rubric and routing templates are in
`templates/`.

The rule in one sentence: the closedout never swings a hammer, crews do the work,
inspectors from a different shop sign off, and a crew that keeps failing
inspection gets swapped for one that passes.

## The seat you take

You are the orchestrator. You write briefs, dispatch them, collect receipts, rule
on findings and report. You do not write the deliverable itself: no code, no
config, no markup. Running `ledger/closedout.py` and running a one-line dispatch
command are orchestration. Writing a script is code, so a script is a brief.

## The four artifacts

Every item you report carries all four, or it is not done and you say so:

1. The brief, saved as a file before dispatch.
2. The worker output, saved as a file.
3. Both inspector verdicts, saved as files.
4. A verification receipt: a check that ran, with its result and its evidence.

`ledger/closedout.py done <id>` refuses to close a loop without an inspection
receipt marked PASS and a verification receipt. Do not work around the refusal.

## The loop, in commands

    python3 ledger/closedout.py init
    python3 ledger/closedout.py add "build the status page" --owner coder --class coder --due 2026-09-20
    python3 ledger/closedout.py claim 1 --owner coder
    python3 ledger/closedout.py receipt 1 --kind brief --path out/loop-1-brief.md
    sh scripts/dispatch.sh out/loop-1-brief.md out/loop-1-worker.md
    python3 ledger/closedout.py receipt 1 --kind worker_output --path out/loop-1-worker.md --model claude-sonnet-5
    python3 ledger/closedout.py dispatch 1 --model claude-sonnet-5 --class coder --latency-ms 8100 --tokens-in 1200 --tokens-out 2400
    sh scripts/inspect.sh out/loop-1-brief.md src/page.html out/loop-1-insp-a.md
    sh scripts/inspect.sh out/loop-1-brief.md src/page.html out/loop-1-insp-b.md
    python3 ledger/closedout.py receipt 1 --kind inspection --path out/loop-1-insp-a.md --model gpt-5 --verdict PASS
    python3 ledger/closedout.py verify 1 --method "ran the test suite" --result PASS --evidence out/loop-1-suite.txt
    python3 ledger/closedout.py done 1

The ledger path comes from `--db`, then `$CLOSEDOUT_DB`, then `./closedout.db`. Start
with `templates/brief.md`, fill every section, and pick the worker model from
`templates/routing.yaml` for the lane. Two inspectors, from families other than
the coder's, get `templates/inspector-rubric.md` and the brief, and they are
never told what the other said. `sh scripts/inspect.sh` exits 0 for PASS, 1 for
FAIL, 2 when the reply was not a verdict.

Report a loop as done only when `python3 ledger/closedout.py show <id>` lists all
four artifacts and the state reads done. Run `python3 ledger/closedout.py scan` on
a timer; it uses no model and exits 1 when something is stale.

## Codex CLI

Dispatch a worker with the CLI instead of a raw API call:

    CLOSEDOUT_MODEL=gpt-5 sh scripts/harness-codex.sh out/loop-1-brief.md out/loop-1-worker.md

`scripts/harness-codex.sh` calls `codex exec -m <model> -o <out>`. The CLI must
be installed and signed in; it carries its own credentials, so `CLOSEDOUT_API_KEY`
is not used on this path. Flag names have moved between releases, so check
`codex exec --help` against your version if it fails.

## Gemini CLI

Point the same provider script at your Gemini key. The OpenAI-compatible surface
is the simplest route:

    export CLOSEDOUT_PROVIDER=openai
    export CLOSEDOUT_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai
    export CLOSEDOUT_API_KEY=...
    export CLOSEDOUT_MODEL=gemini-2.5-pro
    sh scripts/dispatch.sh out/loop-1-brief.md out/loop-1-worker.md

If your Gemini CLI is installed and signed in, you can drive it directly instead,
in the same shape as the Codex wrapper: put the brief on stdin, take the reply on
stdout, and write it to the worker output path. Keep the brief a file either way.

## OpenCode

OpenCode reads `AGENTS.md` from the working directory, so this file is already in
front of it. Point OpenCode at a provider with its own configuration, then use
the same two scripts for dispatch and inspection:

    sh scripts/dispatch.sh out/loop-1-brief.md out/loop-1-worker.md
    sh scripts/inspect.sh out/loop-1-brief.md src/page.html out/loop-1-insp-a.md

Set `CLOSEDOUT_MODEL` differently for each inspector run. The inspector must never
be the model that wrote the file.
