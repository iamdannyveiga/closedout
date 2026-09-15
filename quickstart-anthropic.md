# Quickstart: a Claude coder, two inspectors from other families

This file takes one small loop from an empty ledger to a closed item in about
five minutes. The coder is a Claude model. The two inspectors are from other
families, which is the part that matters: a model cannot inspect its own family's
work and call it review.

You need an Anthropic API key for the coder, and keys for two other providers for
the inspectors. Any two will do. This walkthrough uses an OpenAI-compatible
endpoint and a Google endpoint, because those two are the shortest to set up.

The work in the example is a single file: `src/page.html`, a status page that
reads a JSON file and prints one line per service. Small enough to finish in one
brief, real enough to have something an inspector can check.

## 1. Set up the ledger

    cd foreman-skill
    python3 ledger/foreman.py init
    python3 ledger/foreman.py add "status page reads services.json and lists each service" \
      --owner coder --class coder --due 2026-09-20
    python3 ledger/foreman.py claim 1 --owner coder
    mkdir -p out src

`init` reads `ledger/schema.sql`, so it is safe to run again: the tables, the
indexes, the ready view and the evidence trigger are all created only if they are
missing.

## 2. Write the brief

Copy `templates/brief.md` to `out/loop-1-brief.md` and fill every section. The
sections that decide whether this loop closes cleanly are the deliverables with
exact paths and the acceptance criteria, because the inspectors check the file
against the criteria and nothing else. A criterion an inspector cannot check by
running something is not a criterion.

The brief for this loop names one deliverable, `src/page.html`, and three
criteria: it reads `services.json` with `fetch`, it renders one row per service
with the name, the state and the last check time, and it prints the raw state
string unchanged when a service has a state the page does not know.

File the brief before you dispatch it. The brief is artifact one of four, and it
has to exist as a file before the worker sees it:

    python3 ledger/foreman.py receipt 1 --kind brief --path out/loop-1-brief.md

## 3. Dispatch the coder

    export FOREMAN_PROVIDER=anthropic
    export FOREMAN_BASE_URL=https://api.anthropic.com
    export FOREMAN_API_KEY=...
    export FOREMAN_MODEL=claude-sonnet-5
    sh scripts/dispatch.sh out/loop-1-brief.md out/loop-1-worker.md

The script sends the brief to `/v1/messages` and writes the reply to
`out/loop-1-worker.md`, plus a sidecar `out/loop-1-worker.meta.json` holding the
provider, the model, the latency and the token counts. If the request fails,
it exits nonzero and prints the first part of the error body, so a bad key and a
bad model name are told apart without guessing.

File the output and what it cost:

    python3 ledger/foreman.py receipt 1 --kind worker_output \
      --path out/loop-1-worker.md --model claude-sonnet-5
    python3 ledger/foreman.py dispatch 1 --model claude-sonnet-5 --class coder \
      --latency-ms 8100 --tokens-in 1200 --tokens-out 2400 --pool main

The worker writes the file. If your dispatch was a coding CLI rather than a raw
API call, the brief still goes in as a file and the reply still comes out as one,
which is what keeps this step the same shape either way.

## 4. Run the two inspectors

Two runs, two different `FOREMAN_MODEL` values, and neither inspector is told
what the other said or which model wrote the file.

    FOREMAN_PROVIDER=openai \
    FOREMAN_BASE_URL=https://api.deepseek.com \
    FOREMAN_API_KEY=... \
    FOREMAN_MODEL=deepseek-chat \
      sh scripts/inspect.sh out/loop-1-brief.md src/page.html out/loop-1-insp-a.md

    FOREMAN_PROVIDER=openai \
    FOREMAN_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai \
    FOREMAN_API_KEY=... \
    FOREMAN_MODEL=gemini-2.5-pro \
      sh scripts/inspect.sh out/loop-1-brief.md src/page.html out/loop-1-insp-b.md

`inspect.sh` builds the prompt from `templates/inspector-rubric.md`, the brief and
the file, sends it through the same dispatch path, and reads the first line of
the reply. Exit 0 is PASS, exit 1 is FAIL, exit 2 means the reply was not a
verdict. Each verdict is `severity: file:line: issue` lines, and any blocker
severity is a FAIL.

    python3 ledger/foreman.py receipt 1 --kind inspection \
      --path out/loop-1-insp-a.md --model deepseek-chat --verdict PASS
    python3 ledger/foreman.py receipt 1 --kind inspection \
      --path out/loop-1-insp-b.md --model gemini-2.5-pro --verdict PASS

If either inspector fails the file, the loop goes back to the coder with the
findings attached, and both inspectors re-run on the changed file. A fix is not a
new loop.

## 5. Verify and close

The check is yours to run. Here it is a headless load of the page against a
fixture file, with the output kept as evidence:

    node --experimental-vm-modules check-page.mjs > out/loop-1-verify.txt 2>&1
    python3 ledger/foreman.py verify 1 --method "loaded the page headless against a three-service fixture" \
      --result PASS --evidence out/loop-1-verify.txt
    python3 ledger/foreman.py done 1

Try `done` before this step, on a fresh loop, to see the refusal. The trigger in
`ledger/schema.sql` rejects the update and the CLI prints what is missing. That
refusal is the whole design: it does not depend on the session remembering the
rule.

Check the result:

    python3 ledger/foreman.py show 1
    python3 ledger/foreman.py list --json

`show` lists the four artifacts and the final state. `list --json` puts the loop
under `done`, in that order, after `needs_you`, `blocked`, `open` and `claimed`.

## 6. Keep it running

    python3 ledger/foreman.py scan

The scanner is deterministic and uses no model. It reports loops claimed and
untouched, loops open past their due date, and loops waiting on you. It exits 1
when it finds any, so a timer can turn it into a notification. Run it every few
minutes; it costs nothing.

    python3 ledger/foreman.py bakeoff-check --class coder

This one answers whether the coder lane has earned a bake-off: three blockers
charged to one model in one lane inside seven days. Exit 2 means yes. See
`doctrine/bakeoff.md` for how the race runs and how the result is written back
into `templates/routing.yaml`.
