---
name: closedout
description: Run work through the closedout loop, where the session writes briefs instead of code, crews implement, inspectors from another model family sign off, and every claim carries a receipt in a SQLite ledger.
---

# closedout

Read this file, then take the orchestrator seat. `doctrine/CLOSEDOUT.md` holds the
same rule in full, and `templates/` holds the three files you will use most.

The rule in one sentence: the closedout never swings a hammer, crews do the work,
inspectors from a different shop sign off, and a crew that keeps failing
inspection gets swapped for one that passes.

## What you do and do not do in this mode

You write briefs, dispatch them, collect receipts, rule on findings and report.
You do not write the code, the config, the markup or the hook files that the work
produces. If you catch yourself about to write the deliverable, stop and write
the brief instead.

Two things you may do yourself: run the ledger commands in `ledger/closedout.py`,
and run a shell one-liner that dispatches a worker. A script is code, so a script
is a brief.

## The four artifacts

Every item you report carries all four. If one is missing, the item is not done,
and you say so instead of reporting it.

1. The brief, saved as a file before anything is dispatched.
2. The worker output, saved as a file.
3. Both inspector verdicts, saved as files.
4. A verification receipt: a check that ran, with its result and its evidence.

The ledger refuses to close a loop without the inspection receipt marked PASS and
the verification receipt. That refusal is the point of the ledger. Do not work
around it.

## Setting up

    python3 ledger/closedout.py init
    python3 ledger/closedout.py add "build the status page" --owner coder --class coder --due 2026-09-20
    python3 ledger/closedout.py claim 1 --owner coder

The database path comes from `--db`, then `$CLOSEDOUT_DB`, then `./closedout.db`.
Keep loops small enough that one brief covers one loop.

## Writing the brief

Copy `templates/brief.md` and fill every section: owner, sources to read, hard
exclusions, deliverables with exact paths, acceptance criteria that an inspector
can check by running something, what to print on finish, and what to do when
blocked. A worker reads the brief and nothing else. It never reads this
conversation.

Save the brief, file it, and only then dispatch:

    python3 ledger/closedout.py receipt 1 --kind brief --path out/loop-1-brief.md

## Dispatching a worker

The model per lane is set in `templates/routing.yaml`. Ask the ledger what the
lane has been scoring before you pick:

    python3 ledger/closedout.py bakeoff-check --class coder

Send the brief through the provider script:

    export CLOSEDOUT_PROVIDER=anthropic
    export CLOSEDOUT_BASE_URL=https://api.anthropic.com
    export CLOSEDOUT_API_KEY=...
    export CLOSEDOUT_MODEL=claude-sonnet-5
    sh scripts/dispatch.sh out/loop-1-brief.md out/loop-1-worker.md

Then file the result, including what it cost:

    python3 ledger/closedout.py receipt 1 --kind worker_output --path out/loop-1-worker.md --model claude-sonnet-5
    python3 ledger/closedout.py dispatch 1 --model claude-sonnet-5 --class coder --latency-ms 8100 --tokens-in 1200 --tokens-out 2400 --pool main

If your session runs inside a coding CLI instead of a raw API call, use the
wrapper that matches it: `scripts/harness-claude-code.sh` or
`scripts/harness-codex.sh`. The brief stays the contract either way.

## Running the inspectors

Two inspectors, from model families other than the coder's. Run the same script
twice with two different `CLOSEDOUT_MODEL` values, and never tell either inspector
what the other said. Each run sets its own provider, base URL and key, because
one coder export does not carry the other providers' credentials:

    CLOSEDOUT_PROVIDER=openai CLOSEDOUT_BASE_URL=https://api.openai.com/v1 \
    CLOSEDOUT_API_KEY=$OPENAI_API_KEY CLOSEDOUT_MODEL=gpt-5 \
      sh scripts/inspect.sh out/loop-1-brief.md src/page.html out/loop-1-insp-a.md

    CLOSEDOUT_PROVIDER=openai CLOSEDOUT_BASE_URL=https://api.deepseek.com \
    CLOSEDOUT_API_KEY=$DEEPSEEK_API_KEY CLOSEDOUT_MODEL=deepseek-chat \
      sh scripts/inspect.sh out/loop-1-brief.md src/page.html out/loop-1-insp-b.md

The script exits 0 for PASS, 1 for FAIL and 2 when the reply was not a verdict at
all. File each verdict as a receipt. A blocker sends the work back to the coder,
and the re-review runs after the fix, on the changed file.

State-critical paths, meaning the ledger schema, hooks, send paths and anything
transactional, get a third inspector from a third family.

## Verifying and closing

Run the check yourself, or have a verifier run it, and record what it returned:

    python3 ledger/closedout.py verify 1 --method "ran the test suite" --result PASS --evidence out/loop-1-suite.txt
    python3 ledger/closedout.py done 1

Close the loop only after that. If the ledger refuses, read the refusal out loud
and go and get the missing artifact.

## Where the receipts go

Under `out/` in the working directory, one file per artifact, named for the loop:
`out/loop-<id>-brief.md`, `-worker.md`, `-insp-a.md`, `-insp-b.md`, `-verify.txt`.
The ledger stores the path, the model and the verdict for each one. `out/` is
ignored by git, so the files stay local; the ledger row is what makes them
evidence.

## Reporting

Report a loop as done only when `python3 ledger/closedout.py show <id>` lists a
brief, a worker output, an inspection with verdict PASS, and a verification, and
the loop state reads done. Otherwise report what is missing.

Run the scanner on a timer. It uses no model, so it costs nothing:

    python3 ledger/closedout.py scan

It exits 1 when something is stale. Report those items before anything else.
