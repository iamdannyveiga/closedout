# foreman

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

foreman is a small package you drop next to a codebase so that an agent session
cannot call work finished when it is not.

It is plain files: a doctrine, a brief template, an inspector rubric, a routing
table, a SQLite ledger and three shell scripts that talk to a model provider over
a plain API key. Nothing here is tied to one vendor, one harness or one account.
It works in Claude Code, Codex CLI, Gemini CLI, OpenCode, or a shell loop you
wrote yourself.

## The problem

An agent session says "done" and hands you a summary. The summary is written by
the same model that did the work, on the same context, with the same blind spots.
If the work is wrong, the summary is confidently wrong in exactly the same way,
and the only way to find out is to read the diff yourself.

foreman replaces the summary with evidence. A session that runs under the
doctrine writes a brief instead of code, sends it to a worker, sends the result
to two inspectors from other model families, runs a verification, and files all
of it in a ledger. The ledger refuses to close the item until the evidence is
there, and the refusal comes from a database trigger, not from a polite request
in a prompt.

## Install

Copy the package into your repository, or clone it and work inside it:

    git clone <your fork> foreman-skill
    cd foreman-skill
    python3 ledger/foreman.py init

There is nothing to build and nothing to install. `ledger/foreman.py` uses only
the Python standard library and expects python3 on the path. The scripts are
POSIX `sh` and use `curl` and `python3`.

## Quickstarts

Both walk through the same loop end to end in about five minutes and need one
API key from at least two providers.

- [Anthropic, with a Claude coder and two inspectors from other providers](quickstart-anthropic.md)
- [Any OpenAI-compatible endpoint, with a DeepSeek coder](quickstart-openai-compatible.md)

## The loop

1. Write a brief from `templates/brief.md`. The brief is the contract, and the
   worker reads the brief and nothing else.
2. Dispatch it. `scripts/dispatch.sh` sends it to a worker model and writes the
   reply to a file.
3. Send the reply to two inspectors from model families other than the coder's,
   with `scripts/inspect.sh` and `templates/inspector-rubric.md`. Each returns
   PASS or FAIL plus `severity: file:line: issue` lines.
4. Run a verification: a command, a query or a read-back, with its raw output
   saved next to it.
5. File every artifact as a receipt and close the loop. The ledger refuses to
   close it if the inspection or the verification is missing.

## What is different

**The refusal is in the database, not in the prompt.** `ledger/schema.sql` has a
trigger that rejects a loop moving to done unless it carries an inspection
receipt with verdict PASS and a verification receipt. Prompts are advice. A
trigger is a rule.

**Inspectors are picked by family, not by preference.** The coder, the two
inspectors and the state inspector all come from different families, and a
bake-off is not allowed to change an inspector. A model scored by its relatives
has not been scored.

**Routing changes on evidence.** Every dispatch records the lane, the model, the
latency, the tokens, the quota pool, the blockers and the retries. Three
blockers for one model in one lane inside seven days triggers a bake-off, run on
a real brief, scored on blockers then retries then quota share, with the result
written back into the routing table as a receipt line.

**Nothing runs in the render path.** The scanner that finds stale and overdue
work is deterministic, uses no model, and costs nothing to run every five
minutes.

**The foreman writes no code.** The session that orchestrates is not the session
that implements. That single split is what makes the rest of it checkable,
because the orchestrator has no work of its own to defend.

## Layout

| Path | What it is |
| --- | --- |
| `doctrine/FOREMAN.md` | The rule in full: four sections plus how to adapt it |
| `doctrine/bakeoff.md` | How a lane's model gets replaced by evidence |
| `SKILL.md` | The doctrine as instructions for a Claude Code session |
| `AGENTS.md` | The same instructions for Codex CLI, Gemini CLI and OpenCode |
| `.claude/commands/foreman.md` | The `/foreman` slash command |
| `templates/brief.md` | The worker contract |
| `templates/inspector-rubric.md` | The PASS or FAIL rubric the inspectors follow |
| `templates/routing.yaml` | Lane to model, with the bake-off thresholds |
| `ledger/schema.sql` | Tables, indexes, the ready view and the evidence trigger |
| `ledger/foreman.py` | The CLI: add, claim, block, ask, decide, receipt, verify, done, kill, list, show, dispatch, scan, bakeoff-check |
| `scripts/dispatch.sh` | Send a brief to a worker on an API key |
| `scripts/inspect.sh` | Run one inspector over one file |
| `scripts/harness-*.sh` | Examples for driving a coding CLI instead of a raw API call |
| `examples/README.md` | Where real transcripts from the first build go |

## Compared with neighbors

A field check on 2026-09-15 searched for projects that already do what the three
claims above describe. The table is what it found, project by project, against
the columns that matter here.

| Project | Hooks-enforced tracker | Receipts on items | Separate-family reviewer gate | Quota-share routing | Auto bake-off |
|---|---|---|---|---|---|
| Claude-Project-Tracker | yes | partial (docs, not evidence) | no | no | no |
| task-force (agent variants) | no | no | no | no | no |
| claude-task-manager (dimitritholen) | partial | partial (verify reports) | partial (same-family verifier agents) | no | no |
| agent-receipts (obsigna / inchwormz / webaesbyamin / Prajhan26) | no | yes | no | no | no |
| Agent Done Or Not | yes | yes | no | no | no |
| Tracefold | yes (pre-effect escrow) | yes | no | no | no |
| inspeximus | no (memory hooks only) | yes | no | no | no |
| *flow-next (closest non-listed neighbor)* | partial | yes | partial (advisory, one reviewer) | no | no |
| **foreman** | yes | yes | yes (two, enforced by DB trigger) | yes | yes |

### What is different

The field check found that the reviewer pair in claim A and all of claim C are
prior art. The self-filling task list whose "done" is blocked by a hook shipped
first in Claude-Project-Tracker, which refuses to close an issue until wiki
documentation exists, and in Agent Done Or Not, which blocks the turn until the
most recent check is fresh and passing. The two-reviewer idea itself is also not new:
claude-task-manager runs a separate verification pass that can refuse
completion, and flow-next states the rule that the model which wrote the diff
never reviews it. flow-next is the closest neighbor, and it routes review to a
different model family than the writer, records receipts per task, and gates
`flowctl done` on evidence JSON, but its own documentation says the family rule
is advice that never fails closed, it runs one reviewer rather than two, and its
default configuration reviews in-host with the same family. What the field check
did not find in flow-next, in the twenty-two `verify-*` agents of
claude-task-manager, in CodeRabbit or anywhere else scanned is the enforcement
half: a database trigger that structurally refuses a done transition without a
PASS inspection receipt plus a verification receipt, and a fixed
`severity: file:line` finding format. Quota-share routing exists in the wild only
as load balancing across pooled Claude accounts (teamclaude,
devasheeshG/claude-code-proxy), where it spreads rate limits rather than scoring
a model's quality against the share of a subscription window it spends, and no
mainstream router does that. Reviewer-triggered bake-offs, meaning head-to-head
trials fired by inspector blockers on a real brief instead of an offline
benchmark, were not found in any project, open source or commercial.

### Sources

- https://github.com/rpostulart/Claude-Project-Tracker
- https://github.com/PhlyMcPhlison/TaskForce-Agents
- https://github.com/Shivay00001/ai-agent-autonomous-task-force
- https://github.com/bobmitx/Nexus-Agentic-Task-Force-
- https://github.com/dimitritholen/claude-task-manager
- https://github.com/vibehat/claude-task-manager
- https://github.com/agent-receipts/obsigna
- https://agentreceipts.ai/
- https://github.com/inchwormz/agent-receipts
- https://github.com/webaesbyamin/agent-receipts
- https://github.com/Prajhan26/agent-receipts
- https://github.com/mohamedzhioua/agent-done-or-not
- https://github.com/marketplace/actions/agent-done-or-not
- https://github.com/kafidog/DoneAudit
- https://github.com/TraceFold/tracefold
- https://doi.org/10.5281/zenodo.22168558
- https://github.com/DanceNitra/inspeximus
- https://pypi.org/project/inspeximus/
- https://github.com/gmickel/flow-next
- https://github.com/gmickel/flow-next/blob/main/plugins/flow-next/docs/orchestration.md
- https://flow-next.dev/project/evidence/
- https://github.com/lm-sys/RouteLLM
- https://lmsys.org/blog/2024-07-01-routellm/
- https://docs.notdiamond.ai/docs/quickstart-routing
- https://openrouter.ai/docs/guides/routing/model-fallbacks
- https://docs.litellm.ai/docs/routing
- https://docs.litellm.ai/docs/proxy/load_balancing
- https://portkey.ai/docs/product/ai-gateway/conditional-routing
- https://github.com/portkey-ai/gateway
- https://aider.chat/docs/usage/modes.html
- https://aider.chat/2024/09/26/architect.html
- https://docs.coderabbit.ai/reference/glossary
- https://github.com/KarpelesLab/teamclaude
- https://github.com/devasheeshG/claude-code-proxy

## License

MIT. See [LICENSE](LICENSE).
