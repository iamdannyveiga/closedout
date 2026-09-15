# Quickstart: a Claude coder, two inspectors from other families

This file takes one small loop from an empty ledger to a closed item in about
five minutes. The coder is a Claude model. The two inspectors are from other
families, which is the part that matters: a model cannot inspect its own family's
work and call it review.

You need an Anthropic API key for the coder, and keys for two other providers for
the inspectors. Any two will do. This walkthrough uses an OpenAI-compatible
endpoint and a Google endpoint, because those two are the shortest to set up.

The verification in step 5 is a short Node script, so `node` has to be on the
path. Everything else here needs only `python3`, `curl` and POSIX `sh`.

The work in the example is a single file: `src/page.html`, a status page that
reads a JSON file and prints one line per service. Small enough to finish in one
brief, real enough to have something an inspector can check.

## 1. Set up the ledger

    cd closedout-skill
    python3 ledger/closedout.py init
    python3 ledger/closedout.py add "status page reads services.json and lists each service" \
      --owner coder --class coder --due 2026-09-20
    python3 ledger/closedout.py claim 1 --owner coder
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

    python3 ledger/closedout.py receipt 1 --kind brief --path out/loop-1-brief.md

## 3. Dispatch the coder

    export CLOSEDOUT_PROVIDER=anthropic
    export CLOSEDOUT_BASE_URL=https://api.anthropic.com
    export CLOSEDOUT_API_KEY=...
    export CLOSEDOUT_MODEL=claude-sonnet-5
    sh scripts/dispatch.sh out/loop-1-brief.md out/loop-1-worker.md

The script sends the brief to `/v1/messages` and writes the reply to
`out/loop-1-worker.md`, plus a sidecar `out/loop-1-worker.meta.json` holding the
provider, the model, the latency and the token counts. If the request fails,
it exits nonzero and prints the first part of the error body, so a bad key and a
bad model name are told apart without guessing.

File the output and what it cost:

    python3 ledger/closedout.py receipt 1 --kind worker_output \
      --path out/loop-1-worker.md --model claude-sonnet-5
    python3 ledger/closedout.py dispatch 1 --model claude-sonnet-5 --class coder \
      --latency-ms 8100 --tokens-in 1200 --tokens-out 2400 --pool main

The worker writes the file. If your dispatch was a coding CLI rather than a raw
API call, the brief still goes in as a file and the reply still comes out as one,
which is what keeps this step the same shape either way.

The reply is markdown with the file in a fenced block, so write it out to the
path the brief names before the inspectors are handed anything. That path is what
they read, and a missing file is an error, not an empty review:

    python3 - <<'PY'
    import pathlib, re, sys
    reply = pathlib.Path("out/loop-1-worker.md").read_text()
    block = re.search(r"```[a-zA-Z]*\n(.*?)```", reply, re.S)
    if block is None:
        sys.exit("no fenced block in out/loop-1-worker.md, so there is no file to write")
    pathlib.Path("src/page.html").write_text(block.group(1))
    print("wrote src/page.html")
    PY

## 4. Run the two inspectors

Two runs, two different `CLOSEDOUT_MODEL` values, and neither inspector is told
what the other said or which model wrote the file.

    CLOSEDOUT_PROVIDER=openai \
    CLOSEDOUT_BASE_URL=https://api.deepseek.com \
    CLOSEDOUT_API_KEY=... \
    CLOSEDOUT_MODEL=deepseek-chat \
      sh scripts/inspect.sh out/loop-1-brief.md src/page.html out/loop-1-insp-a.md

    CLOSEDOUT_PROVIDER=openai \
    CLOSEDOUT_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai \
    CLOSEDOUT_API_KEY=... \
    CLOSEDOUT_MODEL=gemini-2.5-pro \
      sh scripts/inspect.sh out/loop-1-brief.md src/page.html out/loop-1-insp-b.md

`inspect.sh` builds the prompt from `templates/inspector-rubric.md`, the brief and
the file, sends it through the same dispatch path, and reads the first line of
the reply. Exit 0 is PASS, exit 1 is FAIL, exit 2 means the reply was not a
verdict. Each verdict is `severity: file:line: issue` lines, and any blocker
severity is a FAIL.

    python3 ledger/closedout.py receipt 1 --kind inspection \
      --path out/loop-1-insp-a.md --model deepseek-chat --verdict PASS
    python3 ledger/closedout.py receipt 1 --kind inspection \
      --path out/loop-1-insp-b.md --model gemini-2.5-pro --verdict PASS

If either inspector fails the file, the loop goes back to the coder with the
findings attached, and both inspectors re-run on the changed file. A fix is not a
new loop.

## 5. Verify and close

The check is yours to run. Here it is a scripted check of the delivered file
against the three criteria in the brief, with the output kept as evidence. The
script is written out first so the command below it has something to run:

    cat > check-page.mjs <<'JS'
    import { readFileSync } from "node:fs";
    const page = readFileSync("src/page.html", "utf8");
    const checks = [
      ["reads services.json with fetch", /fetch\([^)]*services\.json/.test(page)],
      ["renders the name, the state and the last check time",
        ["name", "state", "checked"].every((key) => page.includes(key))],
      ["prints the raw state unchanged when the state is not a known one",
        /(default\s*:|else)[\s\S]{0,120}?\bstate\b/i.test(page)],
    ];
    let ok = true;
    for (const [label, passed] of checks) {
      process.stdout.write((passed ? "PASS " : "FAIL ") + label + "\n");
      ok = ok && passed;
    }
    process.exit(ok ? 0 : 1);
    JS
    node check-page.mjs > out/loop-1-verify.txt 2>&1

Read the evidence file before recording the result. One line per criterion, and
the script exits nonzero if any of them failed:

    python3 ledger/closedout.py verify 1 --method "checked the delivered page against the three acceptance criteria" \
      --result PASS --evidence out/loop-1-verify.txt
    python3 ledger/closedout.py done 1

To see the refusal yourself, on a second loop with no evidence filed:

    python3 ledger/closedout.py add "second loop, no evidence yet" --owner coder --class coder
    python3 ledger/closedout.py done 2

    REFUSED: a loop cannot be done without an inspection receipt with verdict PASS
    and a verification receipt
    loop 2 is missing an inspection receipt with verdict PASS and a verification receipt.
    loop 2 stays open. The four artifacts are the brief, the worker output, the
    inspector verdicts and the verification.

The trigger in `ledger/schema.sql` rejects the update and the CLI prints what is
missing. That refusal is the whole design: it does not depend on the session
remembering the rule.

Check the result:

    python3 ledger/closedout.py show 1
    python3 ledger/closedout.py list --json

`show` lists the four artifacts and the final state. `list` sorts exceptions
first, in the order `needs_you`, `blocked`, `open`, `claimed`, with everything
else after them, so the loop you just closed is the last row rather than the
first.

## 6. Keep it running

    python3 ledger/closedout.py scan

The scanner is deterministic and uses no model. It reports loops claimed and
untouched, loops open past their due date, and loops waiting on you. It exits 1
when it finds any, so a timer can turn it into a notification. Run it every few
minutes; it costs nothing.

    python3 ledger/closedout.py bakeoff-check --class coder

This one answers whether the coder lane has earned a bake-off: three blockers
charged to one model in one lane inside seven days. Exit 2 means yes. See
`doctrine/bakeoff.md` for how the race runs and how the result is written back
into `templates/routing.yaml`.
