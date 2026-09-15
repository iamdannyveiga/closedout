# Bake-off: how a lane's model gets replaced by evidence

A bake-off is the only way a lane changes its model. It is not a review of how a
model feels to work with. It is a race between two models on the same brief, run
through the same inspectors, scored on numbers the ledger already records.

## The trigger

Three inspector blockers, charged to one model, in one lane, inside seven days.
Not three blockers across the team, and not three blockers in a week of mixed
work: one model, one lane, one window.

The check is mechanical:

    python3 ledger/foreman.py bakeoff-check --class coder
    python3 ledger/foreman.py bakeoff-check --class coder --window-days 7

It reads the `dispatches` table, sums the blockers per model in that lane inside
the window, and prints every model at or above three. Exit code 2 means at least
one model has crossed the line. Exit code 0 means the lane is inside its budget.

Run it on a timer, next to the scanner. A trigger that depends on somebody
remembering to look is not a trigger.

## The run

1. Take the next brief in that lane. Not a synthetic benchmark: the next real
   piece of work, so the result is about the work you actually do.
2. Run the incumbent and one challenger on it in parallel, from the same brief
   file, with the same effort setting.
3. Send both results through the same inspector pair, with the same rubric. The
   inspectors are not told which model produced which result.
4. File both runs in the ledger as dispatches in that lane, with the model, the
   effort, the latency, the token counts, the quota pool, the blockers and the
   retries to pass.
5. Score the two runs in this order: fewest blockers, then fewest retries to
   pass, then lowest quota share. Stop at the first difference. A tie on all
   three keeps the incumbent, because switching costs something and the
   challenger has not earned it.

The decision is made on that next brief. Not on a benchmark, not on a later
brief you would rather have run: waiting for a second result turns a trigger into
a suggestion, and the trigger fires on the work you are already doing. If the
lane is important enough to race again, the next trigger will fire on its own and
the second race is a second race, not a condition on the first.

File the brief id in the dispatch rows so the receipt can name the brief the race
ran on.

## The promotion

Write a receipt line into the lane in `templates/routing.yaml`: the date, the
model that lost, the model that won, and the three numbers that decided it. The
receipt is the audit trail. A promotion with no receipt line is a rumour.

    receipt: "2026-09-22. Promoted glm-4.6 over gpt-5 in this lane: 0 blockers to
    2, 1 retry to 3, quota share 0.4 to 0.9 on the same brief."

Then make the edit: `primary` becomes the winner, and the loser becomes either
the `fallback` or nothing at all.

## The guardrails

- A bake-off never changes the inspector pair. If the challenger and the
  inspector share a family, the race is void: a model cannot be scored by its own
  relatives. This is the guardrail that is easiest to break by accident, because
  the obvious challenger is often the model already sitting in an inspector lane.
- Bake-offs run on internal work only. Never on a customer-facing draft, a send,
  or anything that leaves the building. The losing run is still a run you paid
  for, and it does not go out the door.
- Quarantine is separate from the bake-off and faster. Any model above the
  `quarantine_error_rate` in its lane is pulled from routing immediately, with no
  race, until a probe passes. A quarantined model cannot be a challenger and
  cannot be a fallback. The pull is an edit to the routing file with a receipt
  line, and the probe that lifts it is named in that same line.
- A promotion is one lane wide. A model that wins in the coder lane has won
  nothing in the inspector lanes, and its new record does not transfer.
- Cost is share of a subscription window, not raw tokens. Two models with the
  same price per token are not the same price when one of them is drawing on a
  pool that is nearly spent for the day.
