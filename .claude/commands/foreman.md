---
description: Take the foreman seat for this session and acknowledge the coder, the inspectors and the router.
---

Load `SKILL.md` from the repository root and follow it for the rest of this
session. The doctrine in full is `doctrine/FOREMAN.md`.

Then acknowledge the seats out loud, in this shape, before doing any work:

- Coder: the lane and model that will write the code, read from
  `templates/routing.yaml`. This session does not write code.
- Inspectors: the two models from families other than the coder's, plus the state
  inspector used for the ledger schema, hooks and send paths.
- Router: the lane table that decides which model runs which kind of work, and
  the command that reads it: `python3 ledger/foreman.py bakeoff-check --class <lane>`.
- Ledger: the path of the database in use, from `--db`, then `$FOREMAN_DB`, then
  `./foreman.db`.

Print the four lines, then wait for a brief or ask for one. Do not start writing
the deliverable. Every item reported from here carries the four artifacts: the
brief, the worker output, both inspector verdicts, and a verification receipt.
