# Quickstart: any OpenAI-compatible endpoint, with a DeepSeek coder

This file takes one loop from an empty ledger to a closed item using nothing but
the `/chat/completions` shape. That shape is offered by most providers now, so
the same three commands work against a different base URL each time, which is the
point of keeping the router provider-agnostic.

You need one API key per family you use. This walkthrough uses three: a DeepSeek
key for the coder, an Anthropic key for the first inspector and a Google key for
the second, so all three seats are in different families. The coder goes through
the OpenAI shape, the first inspector through the Anthropic shape and the second
through an OpenAI-compatible Google gateway, which is what makes the point that
the seat is a lane and not a vendor.

The work is a small Python function with a real edge case: `src/parse_window.py`,
which turns a duration string like `"15m"` or `"2h30m"` into seconds. Small
enough for one brief, and the edge case is what the inspectors will find.

## 1. Set up the ledger

    cd foreman-skill
    python3 ledger/foreman.py init
    python3 ledger/foreman.py add "parse duration strings into seconds" \
      --owner coder --class coder --due 2026-09-20
    python3 ledger/foreman.py claim 1 --owner coder
    mkdir -p out src

Keep one loop to one brief. If you find yourself adding a second deliverable to
the same brief, add a second loop instead, because the evidence trail is per
loop and a mixed brief produces a mixed verdict that closes neither.

## 2. Write the brief

Copy `templates/brief.md` to `out/loop-1-brief.md` and fill every section. For
this loop the deliverable is `src/parse_window.py` with one function,
`parse_window(text)`, and the acceptance criteria are the edge cases: empty
string raises `ValueError`, a bare number means seconds, `"2h30m"` is 9000, a
repeated unit is rejected, and the input is not modified.

Write down the exclusions too. The brief carries a hard exclusions section, and
it is where you say what the worker must not touch: no changes outside the named
file, no new dependencies, no edits to the ledger.

File the brief before dispatch:

    python3 ledger/foreman.py receipt 1 --kind brief --path out/loop-1-brief.md

## 3. Dispatch the coder

Every provider below is reached through the same script and the same request
shape. Only the three environment variables change.

    export FOREMAN_PROVIDER=openai
    export FOREMAN_BASE_URL=https://api.deepseek.com
    export FOREMAN_API_KEY=...
    export FOREMAN_MODEL=deepseek-chat
    sh scripts/dispatch.sh out/loop-1-brief.md out/loop-1-worker.md

The request goes to `<base>/chat/completions` with the brief as the user message.
The reply is written to `out/loop-1-worker.md`, and the sidecar
`out/loop-1-worker.meta.json` records the provider, the model, the latency in
milliseconds and the token counts, so the ledger row is filled from the file
rather than from memory.

    python3 ledger/foreman.py receipt 1 --kind worker_output \
      --path out/loop-1-worker.md --model deepseek-chat
    python3 ledger/foreman.py dispatch 1 --model deepseek-chat --class coder \
      --latency-ms 6400 --tokens-in 900 --tokens-out 1500 --pool main

The reply is markdown with the function in a fenced block. Write it out to the
path the brief names, because that path is the file the inspectors read, and a
missing file is an error rather than an empty review:

    python3 - <<'PY'
    import pathlib, re
    reply = pathlib.Path("out/loop-1-worker.md").read_text()
    block = re.search(r"```[a-zA-Z]*\n(.*?)```", reply, re.S)
    pathlib.Path("src/parse_window.py").write_text(block.group(1))
    print("wrote src/parse_window.py")
    PY

A base URL that ends in `/v1` is what most of these gateways expect. The script
uses the base URL as you give it and appends the path it needs, so include the
version segment your provider documents; a trailing slash is stripped for you
either way. If the request fails, the script prints the first part of the error
body and exits nonzero, so a rate limit, an expired key and a wrong model name
read differently.

## 4. Run the two inspectors

Same script, two different `FOREMAN_MODEL` values, and the two inspectors are in
families that are not the coder's. The first inspector runs the Anthropic shape
and the second runs an OpenAI-compatible gateway, because the inspector seat is a
lane and not a vendor:

    FOREMAN_PROVIDER=anthropic \
    FOREMAN_BASE_URL=https://api.anthropic.com \
    FOREMAN_API_KEY=$ANTHROPIC_API_KEY \
    FOREMAN_MODEL=claude-sonnet-5 \
      sh scripts/inspect.sh out/loop-1-brief.md src/parse_window.py out/loop-1-insp-a.md

    FOREMAN_PROVIDER=openai \
    FOREMAN_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai \
    FOREMAN_API_KEY=$GOOGLE_API_KEY \
    FOREMAN_MODEL=gemini-2.5-pro \
      sh scripts/inspect.sh out/loop-1-brief.md src/parse_window.py out/loop-1-insp-b.md

The prompt is the rubric from `templates/inspector-rubric.md`, the brief, and the
file. The first line of the reply is PASS or FAIL, and the findings below it are
`severity: file:line: issue`. The script's exit code is 0, 1 or 2, so a shell
`if` can branch on it directly.

    python3 ledger/foreman.py receipt 1 --kind inspection \
      --path out/loop-1-insp-a.md --model claude-sonnet-5 --verdict PASS
    python3 ledger/foreman.py receipt 1 --kind inspection \
      --path out/loop-1-insp-b.md --model gemini-2.5-pro --verdict PASS

A FAIL with a blocker goes back to the coder with the findings attached, and both
inspectors re-run on the changed file. Charge the blocker to the model that
caused it, on the dispatch row for that run. That count is what feeds the
bake-off trigger later.

## 5. Verify and close

Run the check yourself. For this loop that is the edge cases from the brief, run
against the delivered function, with the raw output kept as evidence. It uses the
standard library only, so no test file and no test runner have to exist first:

    python3 - <<'PY' > out/loop-1-verify.txt 2>&1
    import importlib.util
    spec = importlib.util.spec_from_file_location("parse_window", "src/parse_window.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    ok = True
    for text, want in [("45", 45), ("15m", 900), ("2h30m", 9000)]:
        got = module.parse_window(text)
        print(("PASS " if got == want else "FAIL ") + "%r -> %r, wanted %r" % (text, got, want))
        ok = ok and got == want
    try:
        module.parse_window("")
    except ValueError:
        print("PASS empty string raises ValueError")
    else:
        print("FAIL empty string did not raise ValueError")
        ok = False
    raise SystemExit(0 if ok else 1)
    PY

Read the evidence file before recording the result. One line per case, and the
script exits nonzero if any of them failed:

    python3 ledger/foreman.py verify 1 --method "ran the brief's edge cases against the delivered function" \
      --result PASS --evidence out/loop-1-verify.txt
    python3 ledger/foreman.py done 1

If you skip the inspection or the verification, `done` refuses and tells you
which artifact is missing. To see that on a second loop with no evidence filed:

    python3 ledger/foreman.py add "second loop, no evidence yet" --owner coder --class coder
    python3 ledger/foreman.py done 2

    REFUSED: a loop cannot be done without an inspection receipt with verdict PASS
    and a verification receipt
    loop 2 is missing an inspection receipt with verdict PASS and a verification receipt.
    loop 2 stays open. The four artifacts are the brief, the worker output, the
    inspector verdicts and the verification.

That refusal comes from a trigger in the schema, not from the CLI being careful,
so it holds for any other tool that writes to the same database.

    python3 ledger/foreman.py show 1
    python3 ledger/foreman.py list --json

## 6. Adding a provider

A provider is three environment variables. If it speaks the OpenAI shape, there
is nothing to write:

    export FOREMAN_PROVIDER=openai
    export FOREMAN_BASE_URL=https://your-endpoint.example/v1
    export FOREMAN_API_KEY=...

Put it in `templates/routing.yaml` as the lane's `primary` with a `receipt:` line
naming the date and the reason, and it will be picked up by the next dispatch in
that lane. Providers with their own request shape get a branch in
`scripts/dispatch.sh`; the Anthropic shape is already there as the worked
example.

## 7. Keep it running

    python3 ledger/foreman.py scan
    python3 ledger/foreman.py bakeoff-check --class coder

`scan` uses no model and exits 1 when something is stale or overdue, so a timer
can turn it into a notification. `bakeoff-check` exits 2 when one model has
collected three blockers in one lane inside seven days, which is when the lane
has earned a race. `doctrine/bakeoff.md` has the run and the promotion.
