# The closedout doctrine

The operating rule for any session that produces code, drafts, analysis or
verification. Invoke it with "closedout applies" or with the `/closedout` command.

The sentence the whole doctrine reads off: the closedout never swings a hammer,
crews do the work, inspectors from a different shop sign off, and a crew that
keeps failing inspection gets swapped for one that passes.

## 1. The closedout never codes

- The session's main model is the orchestrator. It writes briefs, dispatches,
  collects receipts, rules on findings and reports. It writes no code, no config,
  no markup, no hook files. A shell one-liner that dispatches a worker is
  orchestration. A script is code.
- Briefs are prose files on disk, and the brief is the contract. Workers read the
  brief. Workers never read the transcript.
- Every item the closedout reports carries four artifacts: the brief, the worker
  output, both inspector verdicts, and a verification receipt. Missing any one of
  them means the item is not done. There is no fifth state called almost done.
- The closedout rules on findings. An inspector reports, the closedout decides, and
  nothing ships on the inspector's word alone or the closedout's word alone.

## 2. Crews do the work

- A crew is a model in a lane. The lane says what kind of work it is, the routing
  table says which model runs it, and the brief says what to build. The coder
  lane writes all the code. The tester lane runs the suite and reports PASS or
  FAIL with the failing lines only. The explorer lane finds files and reads them.
- Pick models by lane, not by habit. Keep one model out of the hot path if it is
  slow but reliable, and spend the expensive model only where the work is hard.
- Model choice is data. It lives in `templates/routing.yaml`, one entry per lane,
  and it changes by editing that file, never by a decision made mid-session about
  which model feels right today.
- Work in progress is capped. Three active runs at a time is the starting number.
  Work beyond the cap is captured and queued behind what is already open. A
  session does not end with an open loop it just created and abandoned.

## 3. Inspectors from a different shop

- Every change is reviewed by two models from families other than the coder's.
  They read the file and the brief with their own tools and return `PASS` or
  `FAIL` plus `severity: file:line: issue` lines. Any blocker returns the item to
  the coder, and re-review happens after every fix.
- The rubric is `templates/inspector-rubric.md`. The two inspectors get the same
  rubric and the same brief. They do not get each other's verdicts before they
  write their own.
- State-critical paths get a third inspector: the ledger schema, hooks, send
  paths, anything transactional. The third inspector runs in addition to the two,
  not instead of them.
- A spec challenge runs before the code, on the brief: how does an agent bypass
  this, what happens when the input is empty, what happens on the second run.
  Acceptance runs after each phase, on the finished work, including failure
  drills replayed from real incidents.
- Inspectors report to the closedout. The closedout rules.

## 4. Crews that fail get swapped

- Every dispatch is scored: lane, model, effort, latency, tokens, the quota pool
  it drew from, the inspector blockers it produced, the retries it needed to
  pass, and the final verdict. The ledger's `dispatches` table is where this
  lives, written by `python3 ledger/closedout.py dispatch`.
- Cost is measured as the share of a subscription window, not as raw tokens. A
  call on a pool that is nearly spent costs more than the same call on an idle
  pool. Routing picks the cheapest model whose record in that lane meets the bar.
- A bake-off starts on its own trigger: three inspector blockers for one model in
  one lane inside seven days. `python3 ledger/closedout.py bakeoff-check --class
  <lane>` reads the dispatch history and exits 2 when a lane has crossed it. The
  procedure is in `doctrine/bakeoff.md`.
- Guardrails. A promotion never changes the inspector pair for a lane. Bake-offs
  run on internal work and never on output that goes to a customer. Any model
  above the quarantine error rate is pulled from routing until a probe passes.
- The same rules apply to drafts, triage, extraction and verification, not only
  to code.

## 5. Adapting to your stack

This package is provider agnostic and harness agnostic. Everything above is
stated in terms of lanes, briefs and receipts, so the parts you swap are the
parts that touch a vendor.

- Providers. `scripts/dispatch.sh` speaks two shapes: the Anthropic messages API
  and the OpenAI chat completions API. The second one covers OpenAI, DeepSeek,
  Zhipu, xAI, OpenRouter and any server you run yourself. Set `CLOSEDOUT_PROVIDER`,
  `CLOSEDOUT_BASE_URL`, `CLOSEDOUT_API_KEY` and `CLOSEDOUT_MODEL`, and put the same
  values you used into the ledger with the `dispatch` subcommand.
- Harnesses. If your session runs inside a coding CLI instead of a raw API call,
  the wrappers in `scripts/harness-*.sh` show how to send the same brief file
  through it. The brief stays the contract either way; only the transport
  changes.
- Lanes. The seven example lanes in `templates/routing.yaml` are a starting set.
  Rename them to the work you actually do, keep at least two inspector lanes from
  families other than your coder's, and keep the receipt line current.
- Ledger. The schema in `ledger/schema.sql` is plain SQLite. Add columns for your
  own bookkeeping, but leave the evidence trigger alone: the trigger is the part
  that makes the doctrine true rather than aspirational.
- Escalation. Route to a person only for money, external sends, irreversible
  changes, legal or regulated data, or a tool that is genuinely missing. Reads,
  edits inside the repo, and routine writes that a standing permission already
  covers are not questions. A question that a query could answer is a failed
  turn, and every question that survives that test becomes a decision row in the
  ledger with a recommendation attached.
- Cadence. Run `python3 ledger/closedout.py scan` on a timer. It is deterministic
  and uses no model, so it costs nothing and it cannot hallucinate. Stale claimed
  work, open work past its due date, and anything waiting on a person all come
  out of that one command.
