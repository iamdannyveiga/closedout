<!-- Brief template: the worker contract. Copy this file, fill every section, then dispatch it. -->

# Brief: <title>

The brief is the contract. The worker reads this file and nothing else. It never
reads the conversation that produced it, and it never asks a question in return.
Every section below is filled in before dispatch. An empty section is a broken
contract and the worker should say so and stop.

## Owner

<lane or person who answers for this work, and the model that will run it>

## Sources to read

<exact file paths, URLs or commands the worker must read before writing
anything. Nothing else is in scope. If a file is not listed here, the worker does
not open it.>

## Hard exclusions

<what must not appear in the output. Names, paths, hosts, secrets, customers,
vendors, and any file outside the deliverable list. Include the check the worker
should run on its own output before finishing.>

## Deliverables

<one line per artifact, each with the exact path it must be written to. A
deliverable with no path is not a deliverable.>

- <path> : <what it is, in one line>

## Acceptance criteria

<numbered, checkable statements. Each one is something an inspector can run or
read and answer yes or no. "Works well" is not a criterion. "sqlite3 :memory: <
ledger/schema.sql exits 0" is.>

1. <criterion>
2. <criterion>

## What to print when you finish

<the exact lines the worker prints on success, so the closedout can collect them
without reading the whole transcript. Include the file count and the command
outputs that prove the acceptance criteria.>

## What to do when blocked

<the worker does not ask a question and does not guess. State the shape: stop,
write the reason and the exact command that failed to <path>, print BLOCKED:
<item>: <reason>, and exit nonzero. A blocked report is a complete turn. A
question is not.>
